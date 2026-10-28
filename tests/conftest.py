import os
import sys

import pytest
from langchain_core.messages import AIMessage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402


class FakeStructured:
    def __init__(self, llm, schema):
        self.llm = llm
        self.schema = schema

    def invoke(self, messages):
        self.llm.calls.append((self.schema.__name__, messages))
        queue = self.llm.structured.get(self.schema.__name__, [])
        if callable(queue):
            return queue(messages)
        if not queue:
            return self.schema() if self.schema.__name__ != "SuitabilityAssessment" else None
        return queue.pop(0)


class FakeLLM:
    """Stands in for ChatOllama: queued structured outputs per schema name, canned chat replies."""

    def __init__(self, structured=None, replies=None):
        self.structured = structured or {}
        self.replies = list(replies or [])
        self.calls = []

    def with_structured_output(self, schema, method=None, **kwargs):
        return FakeStructured(self, schema)

    def invoke(self, messages):
        self.calls.append(("chat", messages))
        return AIMessage(content=self.replies.pop(0) if self.replies else "Tell me more.")


@pytest.fixture
def fake_llm():
    return FakeLLM


@pytest.fixture(autouse=True)
def isolated_files(tmp_path, monkeypatch):
    """Keep generated resumes and the database out of the repo."""
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "vault.db"))
    monkeypatch.setattr(config, "FACTS_PARQUET_PATH", str(tmp_path / "backup.parquet"))
    monkeypatch.setattr(config, "RESUME_OUTPUT_PATH", str(tmp_path / "resume.md"))
    monkeypatch.setattr(config, "RESUME_HTML_PATH", str(tmp_path / "resume.html"))
    monkeypatch.setattr(config, "RESUME_PDF_PATH", str(tmp_path / "resume.pdf"))
    return tmp_path
