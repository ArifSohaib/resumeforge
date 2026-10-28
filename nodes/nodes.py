
import datetime
import json
import logging
from typing import List, Literal, Optional

import duckdb
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama.chat_models import ChatOllama

import config
from models import models
from nodes import render
from nodes.matching import compute_match, relevance
from nodes.merge import is_empty, merge_facts
from prompts import system_prompt

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

GENERATE_COMMANDS = {"generate", "done", "/generate", "/done"}


def is_generate_command(text: str) -> bool:
    """Only an explicit command triggers the writer, not 'I was done with that project in 2020'."""
    return text.strip().lower().rstrip(".!") in GENERATE_COMMANDS


def route_start(state: models.ResumeState) -> Literal["chat", "writer", "job", "match"]:
    if state.command == "generate":
        return "writer"
    if state.command == "job":
        return "job"
    if state.command == "match":
        return "match"
    if state.messages and isinstance(state.messages[-1], HumanMessage) and is_generate_command(state.messages[-1].content):
        return "writer"
    return "chat"


# ---------------------------------------------------------------------------
# Interview
# ---------------------------------------------------------------------------

def find_gaps(facts: models.ResumeFacts) -> List[str]:
    """Concrete things the interviewer should ask about next."""
    gaps = []
    pd = facts.personal_details
    if not (pd.first_name and pd.last_name):
        gaps.append("full name")
    if not pd.email:
        gaps.append("email address")
    if not pd.city:
        gaps.append("city / location")
    if not facts.profession:
        gaps.append("work experience (company, title, dates)")
    for role in facts.profession:
        label = " at ".join(p for p in [role.position, role.company] if p) or "a role"
        if not role.position:
            gaps.append(f"job title for {label}")
        if not (role.start_month and role.start_year):
            gaps.append(f"start month and year for {label}")
        if not role.is_current and not (role.end_month and role.end_year):
            gaps.append(f"end month and year (or whether it is current) for {label}")
        if len(role.highlights) < 2:
            gaps.append(f"achievements with metrics for {label}")
        if not role.technologies:
            gaps.append(f"tools/technologies used for {label}")
    if not facts.education:
        gaps.append("education")
    if not facts.skills:
        gaps.append("technical skills")
    return gaps


def chat_node(state: models.ResumeState, llm: ChatOllama):
    # Prepare the context: What do we already know and what is still missing?
    context = [
        f"FACTS (JSON): {state.facts.model_dump_json(exclude_defaults=True)}",
        "GAPS: " + ("; ".join(find_gaps(state.facts)) or "none - ask about impact, metrics or projects"),
    ]
    if state.job:
        context.append(f"TARGET JOB: {state.job.title or ''} at {state.job.company or ''}")
        if state.match:
            missing = state.match.missing_required + state.match.missing_preferred
            if missing:
                context.append("JOB REQUIREMENTS NOT YET SHOWN IN FACTS (ask if the user has them): " + ", ".join(missing))

    # Construct the message list
    messages = [
        SystemMessage(content=system_prompt.SYSTEM_PROMPT),
        SystemMessage(content="\n".join(context)),
    ] + state.messages

    response = llm.invoke(messages)

    return {"messages": [response]}


def latest_exchange(messages: list) -> List:
    """The last user message plus the AI question it answers (the answer is often meaningless alone)."""
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            if i > 0 and isinstance(messages[i - 1], AIMessage):
                return [messages[i - 1], messages[i]]
            return [messages[i]]
    return []


def format_exchange(exchange: List) -> str:
    lines = []
    for message in exchange:
        speaker = "User" if isinstance(message, HumanMessage) else "AI"
        lines.append(f"{speaker}: {message.content}")
    return "\n".join(lines)


def extract_delta(facts: models.ResumeFacts, exchange: List, llm: ChatOllama) -> Optional[models.ResumeFacts]:
    if not exchange:
        return None
    structured_llm = llm.with_structured_output(models.ResumeFacts, method="json_schema")
    prompt = system_prompt.EXTRACTOR_PROMPT.format(known_facts=facts.model_dump_json(exclude_defaults=True))
    try:
        raw = structured_llm.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content="EXCHANGE:\n" + format_exchange(exchange)),
        ])
        return models.ResumeFacts.model_validate(raw)
    except Exception as e:
        logger.warning("Extraction failed for this exchange, keeping previous facts: %s", e)
        return None


def extractor_node(state: models.ResumeState, llm: ChatOllama):
    delta = extract_delta(state.facts, latest_exchange(state.messages), llm)
    if delta is None or is_empty(delta):
        return {}
    facts = merge_facts(state.facts, delta)
    update = {"facts": facts}
    if state.job:
        update["match"] = compute_match(facts, state.job)
    return update


# ---------------------------------------------------------------------------
# Job description
# ---------------------------------------------------------------------------

def job_node(state: models.ResumeState, llm: ChatOllama):
    if not state.job_text or not state.job_text.strip():
        return {}
    structured_llm = llm.with_structured_output(models.JobDescription, method="json_schema")
    try:
        raw = structured_llm.invoke([
            SystemMessage(content=system_prompt.JOB_EXTRACTOR_PROMPT),
            HumanMessage(content="JOB POSTING:\n" + state.job_text),
        ])
        job = models.JobDescription.model_validate(raw)
    except Exception as e:
        logger.warning("Could not parse the job description: %s", e)
        return {}
    return {"job": job, "job_text": None, "match": None, "assessment": None}


def match_node(state: models.ResumeState, llm: ChatOllama):
    if not state.job:
        return {}
    match = compute_match(state.facts, state.job)
    structured_llm = llm.with_structured_output(models.SuitabilityAssessment, method="json_schema")
    prompt = system_prompt.SUITABILITY_PROMPT.format(
        job=state.job.model_dump_json(exclude_defaults=True),
        match=match.model_dump_json(),
        facts=state.facts.model_dump_json(exclude_defaults=True),
    )
    try:
        assessment = models.SuitabilityAssessment.model_validate(
            structured_llm.invoke([SystemMessage(content=prompt), HumanMessage(content="Assess the fit.")])
        )
    except Exception as e:
        logger.warning("Suitability assessment failed, returning the deterministic match only: %s", e)
        assessment = None
    save_job_match(state.job, match, assessment)
    return {"match": match, "assessment": assessment}


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def _job_clause(job: Optional[models.JobDescription]) -> str:
    if not job:
        return ""
    terms = ", ".join((job.required_skills + job.preferred_skills + job.keywords)[:25])
    return f", putting experience relevant to this target job first (only where the facts support it): {job.title or ''} - {terms}"


def write_role_bullets(llm: ChatOllama, role, max_bullets: int,
                       max_chars: int, job: Optional[models.JobDescription]) -> List[str]:
    """Rewrite a role's (or project's) highlights into at most `max_bullets` bullets."""
    if max_bullets <= 0:
        return []
    fallback = sorted(role.highlights, key=lambda h: -relevance(h, job))[:max_bullets]
    if not role.highlights:
        return []
    structured_llm = llm.with_structured_output(models.RoleBullets, method="json_schema")
    prompt = system_prompt.ROLE_BULLETS_PROMPT.format(
        max_bullets=max_bullets,
        max_chars=max_chars,
        job_clause=_job_clause(job),
        role=role.model_dump_json(exclude_defaults=True),
    )
    try:
        result = models.RoleBullets.model_validate(structured_llm.invoke(prompt))
        bullets = [b.strip().lstrip("-•* ").strip() for b in result.bullets if b and b.strip()]
        return bullets[:max_bullets] or fallback
    except Exception as e:
        logger.warning("Bullet rewrite failed for %s, using raw highlights: %s",
                       getattr(role, "company", None) or getattr(role, "name", None), e)
        return fallback


def write_summary(llm: ChatOllama, facts: models.ResumeFacts, job: Optional[models.JobDescription]) -> Optional[str]:
    structured_llm = llm.with_structured_output(models.ResumeSummary, method="json_schema")
    prompt = system_prompt.SUMMARY_PROMPT.format(
        job_clause=_job_clause(job), facts=facts.model_dump_json(exclude_defaults=True),
    )
    try:
        return models.ResumeSummary.model_validate(structured_llm.invoke(prompt)).summary.strip()
    except Exception as e:
        logger.warning("Summary generation failed, leaving it out: %s", e)
        return None


def _bullets_for(budget: dict, index: int) -> int:
    allowed = budget["bullets_per_role"]
    return allowed[index] if index < len(allowed) else allowed[-1]


def build_resume(facts: models.ResumeFacts, llm: ChatOllama, job: Optional[models.JobDescription] = None,
                 max_pages: Optional[int] = None):
    """
    Generate the resume in rounds. Each round writes bullets under a tighter budget, renders the
    result to PDF and counts the pages; the first round that fits wins. If none does, content is
    trimmed deterministically (oldest/least relevant first) until it fits.
    Returns (markdown, pages, rounds).
    """
    max_pages = max_pages or config.MAX_PAGES
    roles = render.sort_roles(facts.profession)
    projects = sorted(facts.projects, key=lambda p: -relevance(" ".join([p.name or ""] + p.highlights + p.technologies), job))
    summary = write_summary(llm, facts, job)
    cache = {}  # (kind, index, max_bullets, max_chars) -> bullets, so unchanged limits are not regenerated

    def bullets(kind, index, item, max_bullets, max_chars):
        key = (kind, index, max_bullets, max_chars)
        if key not in cache:
            cache[key] = write_role_bullets(llm, item, max_bullets, max_chars, job)
        return cache[key]

    content = None
    pages = 0
    for round_number, budget in enumerate(config.GENERATION_BUDGETS, start=1):
        content = render.ResumeContent(
            summary=summary,
            role_bullets=[
                bullets("role", i, role, _bullets_for(budget, i), budget["max_chars"]) for i, role in enumerate(roles)
            ],
            projects=[
                (project, bullets("project", i, project, budget["bullets_per_project"], budget["max_chars"]))
                for i, project in enumerate(projects[:budget["max_projects"]])
            ],
        )
        markdown = render.render_markdown(facts, content, job)
        pages = render.markdown_to_pdf(markdown)
        logger.info("Generation round %d: %d page(s)", round_number, pages)
        if pages <= max_pages:
            return markdown, pages, round_number

    content, markdown, pages = render.trim_to_fit(facts, content, job, max_pages)
    logger.info("Trimmed to %d page(s) after %d generation rounds", pages, len(config.GENERATION_BUDGETS))
    return markdown, pages, len(config.GENERATION_BUDGETS)


def writer_node(state: models.ResumeState, llm: ChatOllama):
    markdown, pages, rounds = build_resume(state.facts, llm, state.job)
    with open(config.RESUME_OUTPUT_PATH, "w") as f:
        f.write(markdown)
    with open(config.RESUME_HTML_PATH, "w") as f:
        f.write(render.markdown_to_html(markdown))
    render.markdown_to_pdf(markdown, config.RESUME_PDF_PATH)
    logger.info("Resume written (%d page(s), %d round(s))", pages, rounds)
    save_to_local_db(state.facts)
    return {"resume_markdown": markdown}


# ---------------------------------------------------------------------------
# Transcript recovery
# ---------------------------------------------------------------------------

def load_txt_conversation(path: str):
    """Parse a saved 'You: ... / AI: ...' transcript. Lines without a prefix continue the previous message."""
    messages = []
    with open(path, "r") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            lowered = stripped.lower()
            if lowered.startswith("you:"):
                messages.append(HumanMessage(content=stripped[4:].strip()))
            elif lowered.startswith("ai:"):
                messages.append(AIMessage(content=stripped[3:].strip()))
            elif messages:
                messages[-1] = type(messages[-1])(content=messages[-1].content + "\n" + stripped)
    return messages


def extract_from_messages(messages: list, llm: ChatOllama,
                          facts: Optional[models.ResumeFacts] = None) -> models.ResumeFacts:
    """Rebuild facts from a whole transcript, one exchange at a time, so nothing is lost to context limits."""
    facts = facts or models.ResumeFacts()
    for i, message in enumerate(messages):
        if not isinstance(message, HumanMessage):
            continue
        delta = extract_delta(facts, latest_exchange(messages[: i + 1]), llm)
        if delta is not None:
            facts = merge_facts(facts, delta)
    return facts


def extract_from_file(path: str, llm: ChatOllama) -> models.ResumeFacts:
    return extract_from_messages(load_txt_conversation(path), llm)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_to_local_db(facts: models.ResumeFacts, db_path: Optional[str] = None,
                     parquet_path: Optional[str] = None):
    db_path = db_path or config.DB_PATH
    parquet_path = parquet_path or config.FACTS_PARQUET_PATH
    # Facts are stored as JSON so schema changes never break the table
    con = duckdb.connect(db_path)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS resume_facts (saved_at TIMESTAMP, facts_json JSON)")
        con.execute("INSERT INTO resume_facts VALUES (?, ?)", [datetime.datetime.now(), facts.model_dump_json()])
        # Also save a snapshot as Parquet for long-term backup
        con.execute(f"COPY resume_facts TO '{parquet_path}' (FORMAT PARQUET)")
    finally:
        con.close()
    logger.info("Resume facts vaulted successfully.")


def load_latest_facts(db_path: Optional[str] = None) -> Optional[models.ResumeFacts]:
    try:
        con = duckdb.connect(db_path or config.DB_PATH, read_only=True)
    except Exception:
        return None
    try:
        row = con.execute("SELECT facts_json FROM resume_facts ORDER BY saved_at DESC LIMIT 1").fetchone()
    except duckdb.Error:
        return None
    finally:
        con.close()
    return models.ResumeFacts.model_validate_json(row[0]) if row else None


def save_job_match(job: models.JobDescription, match: models.MatchReport,
                   assessment: Optional[models.SuitabilityAssessment], db_path: Optional[str] = None):
    con = duckdb.connect(db_path or config.DB_PATH)
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS job_matches (
                saved_at TIMESTAMP, job_title VARCHAR, company VARCHAR, score INTEGER,
                job_json JSON, match_json JSON, assessment_json JSON
            )
        """)
        con.execute(
            "INSERT INTO job_matches VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                datetime.datetime.now(), job.title, job.company, match.score,
                job.model_dump_json(), match.model_dump_json(),
                assessment.model_dump_json() if assessment else None,
            ],
        )
    finally:
        con.close()


def format_match_report(job: models.JobDescription, match: models.MatchReport,
                        assessment: Optional[models.SuitabilityAssessment]) -> str:
    lines = [f"Job: {job.title or 'Unknown title'}" + (f" at {job.company}" if job.company else ""),
             f"Match score: {match.score}/100"]
    if assessment:
        lines.append(f"Verdict: {assessment.verdict} - {assessment.summary}")
    lines.append("Required skills found: " + (", ".join(match.matched_required) or "none"))
    lines.append("Required skills NOT found: " + (", ".join(match.missing_required) or "none"))
    if match.matched_preferred or match.missing_preferred:
        lines.append("Preferred skills found: " + (", ".join(match.matched_preferred) or "none"))
        lines.append("Preferred skills NOT found: " + (", ".join(match.missing_preferred) or "none"))
    if match.required_years_experience is not None:
        status = "meets" if match.meets_experience else "below"
        lines.append(f"Experience: {match.candidate_years_experience} yrs vs {match.required_years_experience}+ required ({status})")
    if assessment and assessment.strengths:
        lines.append("Strengths:\n" + "\n".join(f"  - {s}" for s in assessment.strengths))
    if assessment and assessment.gaps:
        lines.append("Gaps:\n" + "\n".join(f"  - {g}" for g in assessment.gaps))
    if assessment and assessment.questions_to_confirm:
        lines.append("Please confirm:\n" + "\n".join(f"  - {q}" for q in assessment.questions_to_confirm))
    return "\n".join(lines)
