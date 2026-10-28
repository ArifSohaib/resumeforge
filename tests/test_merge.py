from models import models
from nodes.merge import merge_facts


def facts(**kwargs):
    return models.ResumeFacts.model_validate(kwargs)


def test_new_facts_are_added_and_old_ones_kept():
    current = facts(personal_details={"first_name": "Ada"}, skills=["Python"])
    delta = facts(personal_details={"email": "ada@example.com"}, skills=["python", "SQL"])
    merged = merge_facts(current, delta)
    assert merged.personal_details.first_name == "Ada"
    assert merged.personal_details.email == "ada@example.com"
    assert merged.skills == ["Python", "SQL"]


def test_details_for_a_known_role_merge_into_it():
    current = facts(profession=[{"company": "Acme Inc.", "position": "Data Engineer", "highlights": ["Built ETL"]}])
    delta = facts(profession=[{"company": "acme", "start_month": "March", "start_year": "2021",
                               "highlights": ["Cut costs 30%"], "technologies": ["Airflow"]}])
    merged = merge_facts(current, delta)
    assert len(merged.profession) == 1
    role = merged.profession[0]
    assert (role.start_month, role.start_year) == (3, 2021)
    assert role.highlights == ["Built ETL", "Cut costs 30%"]
    assert "Airflow" in merged.skills


def test_new_position_at_same_company_is_a_new_role():
    current = facts(profession=[{"company": "Acme", "position": "Engineer"}])
    delta = facts(profession=[{"company": "Acme", "position": "Senior Engineer"}])
    assert len(merge_facts(current, delta).profession) == 2


def test_corrections_overwrite_and_current_role_clears_end_date():
    current = facts(profession=[{"company": "Acme", "position": "Engineer", "end_month": 5, "end_year": 2023}])
    delta = facts(profession=[{"company": "Acme", "is_current": True}])
    role = merge_facts(current, delta).profession[0]
    assert role.is_current and role.end_year is None


def test_unnamed_role_attaches_to_the_only_role():
    current = facts(profession=[{"company": "Acme", "position": "Engineer"}])
    delta = facts(profession=[{"highlights": ["Led migration to AWS"]}])
    merged = merge_facts(current, delta)
    assert merged.profession[0].highlights == ["Led migration to AWS"]


def test_empty_delta_entries_are_ignored():
    current = facts(profession=[{"company": "A"}, {"company": "B"}])
    delta = facts(profession=[{}, {"highlights": ["ambiguous"]}])
    merged = merge_facts(current, delta)
    assert len(merged.profession) == 2
    assert all(not r.highlights for r in merged.profession)


def test_partial_data_validates_instead_of_being_thrown_away():
    # previously every date field was a required int, so one missing month discarded the whole extraction
    role = models.ProfessionalExperience.model_validate({"company": "Acme", "end_year": "present", "start_month": "sept"})
    assert role.end_year is None and role.start_month == 9
