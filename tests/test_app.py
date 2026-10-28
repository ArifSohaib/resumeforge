from fastapi.testclient import TestClient

import app as web
from main import ResumeSession, define_graph
from models import models


def test_job_and_generate_endpoints(fake_llm, monkeypatch):
    llm = fake_llm(structured={
        "JobDescription": [models.JobDescription(title="Engineer", required_skills=["Python"])],
        "SuitabilityAssessment": [models.SuitabilityAssessment(verdict="weak", summary="No evidence yet.")],
        "ResumeSummary": lambda m: models.ResumeSummary(summary="Engineer."),
    })
    monkeypatch.setattr(web, "session", ResumeSession(graph=define_graph(chat_model=llm, model=llm), model=llm))
    client = TestClient(web.app)

    assert client.get("/").status_code == 200
    assert client.get("/resume.pdf").status_code == 404

    response = client.post("/job", json={"text": "Python engineer wanted"}).json()["response"]
    assert "Required skills NOT found: Python" in response

    client.post("/generate")
    pdf = client.get("/resume.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
