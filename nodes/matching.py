"""
Deterministic matching of resume facts against a structured job description.

Kept free of LLM calls so the score is reproducible; the LLM only explains it (see nodes.match_node).
"""
import datetime
import re
from typing import Iterable, List, Optional, Set

from models import models

# Common spellings that should count as the same skill.
ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "k8s": "kubernetes",
    "postgres": "postgresql",
    "psql": "postgresql",
    "golang": "go",
    "react js": "react",
    "reactjs": "react",
    "node js": "node",
    "nodejs": "node",
    "node.js": "node",
    "amazon web services": "aws",
    "google cloud": "gcp",
    "google cloud platform": "gcp",
    "microsoft azure": "azure",
    "ml": "machine learning",
    "dl": "deep learning",
    "nlp": "natural language processing",
    "cv": "computer vision",
    "llm": "large language models",
    "llms": "large language models",
    "gen ai": "generative ai",
    "genai": "generative ai",
    "ci cd": "ci/cd",
    "cicd": "ci/cd",
    "sklearn": "scikit-learn",
    "scikit learn": "scikit-learn",
    "tf": "tensorflow",
}


def canonical(skill: str) -> str:
    text = skill.lower().strip()
    text = re.sub(r"\s+", " ", re.sub(r"[_\-]", " ", text))
    text = ALIASES.get(text, text)
    return ALIASES.get(text.replace(".", " ").strip(), text)


def _contains(corpus: str, term: str) -> bool:
    """Whole-word search that copes with terms like 'c++', 'c#', '.net', 'ci/cd'."""
    pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
    return re.search(pattern, corpus) is not None


def candidate_skills(facts: models.ResumeFacts) -> Set[str]:
    skills = list(facts.skills)
    for role in facts.profession:
        skills += role.technologies
    for project in facts.projects:
        skills += project.technologies
    return {canonical(s) for s in skills if s}


def candidate_corpus(facts: models.ResumeFacts) -> str:
    parts: List[str] = []
    for role in facts.profession:
        parts += [role.position or ""] + role.highlights
    for project in facts.projects:
        parts += [project.name or "", project.description or ""] + project.highlights
    for edu in facts.education:
        parts += [edu.degree or "", edu.additional_details or ""]
    for other in facts.other_details:
        parts += [other.name or "", other.details or ""]
    for award in facts.awards:
        parts += [award.name or "", award.details or ""]
    return " ".join(parts).lower()


def has_skill(skill: str, skills: Set[str], corpus: str) -> bool:
    target = canonical(skill)
    if target in skills:
        return True
    # reverse alias lookup so 'kubernetes' also finds 'k8s' in free text
    spellings = {target, skill.lower().strip()} | {k for k, v in ALIASES.items() if v == target}
    return any(_contains(corpus, s) for s in spellings if s)


def years_of_experience(roles: Iterable[models.ProfessionalExperience], today: Optional[datetime.date] = None) -> float:
    """Total years across roles, counting overlapping periods once. Missing months default to Jan/Dec."""
    today = today or datetime.date.today()
    now = today.year * 12 + today.month - 1
    intervals = []
    for role in roles:
        if not role.start_year:
            continue
        start = role.start_year * 12 + (role.start_month or 1) - 1
        if role.is_current or not role.end_year:
            end = now
        else:
            end = role.end_year * 12 + (role.end_month or 12) - 1
        if end >= start:
            intervals.append([start, end + 1])
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    total = sum(end - start for start, end in merged)
    return round(total / 12, 1)


def compute_match(facts: models.ResumeFacts, job: models.JobDescription,
                  today: Optional[datetime.date] = None) -> models.MatchReport:
    skills = candidate_skills(facts)
    corpus = candidate_corpus(facts)

    def split(items: List[str]):
        found, missing = [], []
        for item in dict.fromkeys(i.strip() for i in items if i and i.strip()):
            (found if has_skill(item, skills, corpus) else missing).append(item)
        return found, missing

    matched_required, missing_required = split(job.required_skills)
    matched_preferred, missing_preferred = split(job.preferred_skills)

    years = years_of_experience(facts.profession, today)
    meets_experience = None if job.min_years_experience is None else years >= job.min_years_experience

    # Weighted score: required skills dominate, preferred skills and experience refine it.
    parts = []
    if job.required_skills:
        parts.append((0.7, len(matched_required) / max(1, len(matched_required) + len(missing_required))))
    if job.preferred_skills:
        parts.append((0.2, len(matched_preferred) / max(1, len(matched_preferred) + len(missing_preferred))))
    if job.min_years_experience:
        parts.append((0.1, min(1.0, years / job.min_years_experience)))
    weight = sum(w for w, _ in parts)
    score = round(100 * sum(w * v for w, v in parts) / weight) if weight else 0

    return models.MatchReport(
        score=score,
        matched_required=matched_required,
        missing_required=missing_required,
        matched_preferred=matched_preferred,
        missing_preferred=missing_preferred,
        candidate_years_experience=years,
        required_years_experience=job.min_years_experience,
        meets_experience=meets_experience,
    )


def relevance(text: str, job: Optional[models.JobDescription]) -> int:
    """How many job terms a piece of resume text mentions; used to order bullets and skills."""
    if not job:
        return 0
    lowered = text.lower()
    terms = [t for t in job.required_skills * 2 + job.preferred_skills + job.keywords if t and t.strip()]
    return sum(1 for term in terms if _contains(lowered, canonical(term)) or _contains(lowered, term.lower().strip()))
