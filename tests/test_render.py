import os

import config
from models import models
from nodes import nodes, render


def big_facts(roles=10, highlights=8):
    return models.ResumeFacts.model_validate({
        "personal_details": {"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com", "city": "London"},
        "skills": [f"Skill{i}" for i in range(40)],
        "profession": [
            {
                "company": f"Company {i}", "position": "Senior Engineer",
                "start_month": 1, "start_year": 2024 - 2 * i - 2, "end_month": 12, "end_year": 2024 - 2 * i,
                "highlights": [
                    f"Designed and shipped a distributed data pipeline component number {j} that processed "
                    f"billions of events per day and reduced end-to-end latency by {j + 10}% for downstream teams"
                    for j in range(highlights)
                ],
            }
            for i in range(roles)
        ],
        "projects": [{"name": f"Project {i}", "highlights": ["Built a thing used by many people"] * 3} for i in range(4)],
        "education": [{"university": "Uni", "degree": "BSc CS", "year_graduated": 2010}],
        "other_details": [{"name": "Languages", "details": "English, French"}],
    })


def passthrough_bullets(messages):
    """Fake LLM that 'rewrites' by returning the role's highlights unchanged (worst case for length)."""
    import json
    import re
    role = json.loads(re.search(r"ROLE \(JSON\):\s*(\{.*\})", messages, re.S).group(1))
    limit = int(re.search(r"at most (\d+) resume bullets", messages).group(1))
    return models.RoleBullets(bullets=role.get("highlights", [])[:limit])


def test_long_history_is_cut_to_the_page_limit(fake_llm):
    llm = fake_llm(structured={"RoleBullets": passthrough_bullets,
                               "ResumeSummary": lambda m: models.ResumeSummary(summary="Engineer.")})
    markdown, pages, rounds = nodes.build_resume(big_facts(), llm)
    assert pages <= config.MAX_PAGES
    assert render.markdown_to_pdf(markdown) == pages
    assert "Company 0" in markdown  # most recent role always kept


def test_short_resume_fits_in_first_round(fake_llm):
    llm = fake_llm(structured={"RoleBullets": passthrough_bullets,
                               "ResumeSummary": lambda m: models.ResumeSummary(summary="Engineer.")})
    markdown, pages, rounds = nodes.build_resume(big_facts(roles=2, highlights=3), llm)
    assert (pages, rounds) == (1, 1)


def test_tighter_rounds_are_used_before_trimming(fake_llm):
    llm = fake_llm(structured={"RoleBullets": passthrough_bullets,
                               "ResumeSummary": lambda m: models.ResumeSummary(summary="Engineer.")})
    _, pages, rounds = nodes.build_resume(big_facts(roles=10, highlights=8), llm)
    assert pages <= config.MAX_PAGES
    assert 1 < rounds < len(config.GENERATION_BUDGETS)


def test_trimming_keeps_every_role_when_rounds_are_not_enough(fake_llm):
    llm = fake_llm(structured={"RoleBullets": passthrough_bullets,
                               "ResumeSummary": lambda m: models.ResumeSummary(summary="Engineer.")})
    markdown, pages, _ = nodes.build_resume(big_facts(roles=25, highlights=8), llm)
    assert pages <= config.MAX_PAGES
    assert "Company 0" in markdown and "Senior Engineer — Company 24" in markdown


def test_writer_saves_md_html_and_pdf(fake_llm, isolated_files):
    llm = fake_llm(structured={"RoleBullets": passthrough_bullets,
                               "ResumeSummary": lambda m: models.ResumeSummary(summary="Engineer.")})
    state = models.ResumeState(facts=big_facts(roles=3, highlights=3))
    update = nodes.writer_node(state, llm)
    assert update["resume_markdown"].startswith("# Ada Lovelace")
    for path in (config.RESUME_OUTPUT_PATH, config.RESUME_HTML_PATH, config.RESUME_PDF_PATH):
        assert os.path.getsize(path) > 0
    assert nodes.load_latest_facts() == state.facts


def test_dates_and_current_role_formatting():
    role = models.ProfessionalExperience(company="A", start_month=3, start_year=2021, is_current=True)
    assert render.format_dates(role) == "Mar 2021 – Present"
