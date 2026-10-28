from langchain_core.messages import AIMessage, HumanMessage

from main import ResumeSession, define_graph
from models import models
from nodes import nodes


def make_session(fake_llm, structured, replies=None):
    llm = fake_llm(structured=structured, replies=replies)
    return ResumeSession(graph=define_graph(chat_model=llm, model=llm), model=llm), llm


def test_facts_accumulate_across_turns(fake_llm):
    session, llm = make_session(fake_llm, {"ResumeFacts": [
        models.ResumeFacts.model_validate({"profession": [{"company": "Acme", "position": "Engineer"}]}),
        models.ResumeFacts.model_validate({"profession": [{"company": "Acme", "start_month": 3, "start_year": 2021}]}),
    ]}, replies=["When did you start at Acme?", "Great, what did you achieve?"])

    session.handle("I'm an engineer at Acme")
    session.handle("March 2021")

    role = session.state().facts.profession[0]
    assert (role.company, role.position, role.start_month, role.start_year) == ("Acme", "Engineer", 3, 2021)

    # the extractor only sees the latest exchange: the AI question and the answer to it
    _, extractor_messages = [c for c in llm.calls if c[0] == "ResumeFacts"][-1]
    exchange = extractor_messages[-1].content
    assert "AI: When did you start at Acme?" in exchange and "User: March 2021" in exchange
    assert "I'm an engineer at Acme" not in exchange


def test_failed_extraction_keeps_previous_facts(fake_llm):
    def boom(_):
        raise ValueError("model returned junk")
    session, _ = make_session(fake_llm, {"ResumeFacts": [
        models.ResumeFacts.model_validate({"skills": ["Python"]}),
    ]})
    session.handle("I know Python")
    session.model.structured["ResumeFacts"] = boom
    session.handle("blah")
    assert session.state().facts.skills == ["Python"]


def test_done_inside_a_sentence_does_not_generate():
    assert not nodes.is_generate_command("I was done with that project in 2020")
    assert nodes.is_generate_command(" Generate! ")


def test_job_description_is_parsed_matched_and_reported(fake_llm):
    session, llm = make_session(fake_llm, {
        "ResumeFacts": [models.ResumeFacts.model_validate({"skills": ["Python", "SQL"]})],
        "JobDescription": [models.JobDescription(title="Data Engineer", company="Initech",
                                                 required_skills=["Python", "Spark"], preferred_skills=["SQL"])],
        "SuitabilityAssessment": [models.SuitabilityAssessment(
            verdict="moderate", summary="Solid Python, Spark unproven.",
            questions_to_confirm=["Have you used Spark?"])],
    })
    session.handle("I use Python and SQL")
    report = session.handle("/job We need Python and Spark. SQL is a plus.")

    state = session.state()
    assert state.match.matched_required == ["Python"]
    assert state.match.missing_required == ["Spark"]
    assert "Spark" in report and "Have you used Spark?" in report

    # the interviewer is told to probe the missing requirement
    session.handle("ok")
    chat_messages = [c for c in llm.calls if c[0] == "chat"][-1][1]
    assert "Spark" in chat_messages[1].content


def test_transcript_import_handles_multiline_messages(tmp_path, fake_llm):
    path = tmp_path / "conversation.txt"
    path.write_text("AI: Where do you work?\nYou: At Acme.\nI lead the data team.\nAI: Since when?\nYou: 2021\n")
    messages = nodes.load_txt_conversation(str(path))
    assert [type(m) for m in messages] == [AIMessage, HumanMessage, AIMessage, HumanMessage]
    assert messages[1].content == "At Acme.\nI lead the data team."

    llm = fake_llm(structured={"ResumeFacts": [
        models.ResumeFacts.model_validate({"profession": [{"company": "Acme", "highlights": ["Leads the data team"]}]}),
        models.ResumeFacts.model_validate({"profession": [{"company": "Acme", "start_year": 2021}]}),
    ]})
    facts = nodes.extract_from_messages(messages, llm)
    assert facts.profession[0].start_year == 2021
    assert facts.profession[0].highlights == ["Leads the data team"]
