import datetime

from models import models
from nodes.matching import compute_match, years_of_experience


def test_skills_match_through_aliases_and_free_text():
    facts = models.ResumeFacts.model_validate({
        "skills": ["Python", "Postgres"],
        "profession": [{
            "company": "Acme", "position": "ML Engineer",
            "technologies": ["k8s"],
            "highlights": ["Served PyTorch models behind a FastAPI service"],
        }],
    })
    job = models.JobDescription(
        required_skills=["Python", "PostgreSQL", "Kubernetes", "PyTorch", "Rust"],
        preferred_skills=["FastAPI", "Terraform"],
    )
    report = compute_match(facts, job)
    assert report.matched_required == ["Python", "PostgreSQL", "Kubernetes", "PyTorch"]
    assert report.missing_required == ["Rust"]
    assert report.matched_preferred == ["FastAPI"]
    assert report.missing_preferred == ["Terraform"]
    assert 0 < report.score < 100


def test_short_skill_names_need_whole_words():
    facts = models.ResumeFacts.model_validate({"profession": [{"company": "A", "highlights": ["Managed a Rgo team"]}]})
    report = compute_match(facts, models.JobDescription(required_skills=["R", "Go"]))
    assert report.missing_required == ["R", "Go"]


def test_years_of_experience_counts_overlap_once():
    roles = [
        models.ProfessionalExperience(company="A", start_month=1, start_year=2018, end_month=12, end_year=2020),
        models.ProfessionalExperience(company="B", start_month=1, start_year=2020, end_month=12, end_year=2021),
        models.ProfessionalExperience(company="C", start_month=1, start_year=2024, is_current=True),
    ]
    assert years_of_experience(roles, today=datetime.date(2024, 12, 1)) == 5.0


def test_experience_requirement():
    facts = models.ResumeFacts.model_validate({"profession": [{"company": "A", "start_year": 2022, "start_month": 1, "is_current": True}]})
    report = compute_match(facts, models.JobDescription(min_years_experience=5), today=datetime.date(2024, 1, 1))
    assert report.meets_experience is False
    assert report.candidate_years_experience == 2.1  # Jan 2022 through Jan 2024 inclusive
