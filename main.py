import logging
import os
import sys

from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START, END

import config
from models import models
from nodes import nodes
from nodes.nodes import chat_node, extractor_node, job_node, match_node, writer_node, route_start

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Conversational model for the interview, deterministic one for extraction/matching/writing.
chat_llm = ChatOllama(model=config.MODEL_NAME, temperature=config.CHAT_TEMPERATURE, num_ctx=config.NUM_CTX)
llm = ChatOllama(model=config.MODEL_NAME, temperature=0, num_ctx=config.NUM_CTX)

HELP = """Commands:
  generate | done        write resume_draft.md/.html/.pdf (max {pages} pages)
  /job <file or text>    add a job description (/job alone lets you paste it, end with a line 'END')
  /match                 re-check suitability against the job with the latest facts
  /facts                 show the facts collected so far
  /import <file.txt>     rebuild facts from a saved 'You: / AI:' transcript
  /load                  load the last facts saved in the local database
  /help                  show this help
  /quit                  exit
""".format(pages=config.MAX_PAGES)


def define_graph(chat_model=None, model=None, checkpointer=None):
    chat_model = chat_model or chat_llm
    model = model or llm

    # Initialize graph with your state schema
    builder = StateGraph(models.ResumeState)

    # --- Add nodes ---
    builder.add_node("chat", lambda state: chat_node(state, chat_model))
    builder.add_node("extractor", lambda state: extractor_node(state, model))
    builder.add_node("writer", lambda state: writer_node(state, model))
    builder.add_node("job", lambda state: job_node(state, model))
    builder.add_node("match", lambda state: match_node(state, model))

    # --- Define flow ---
    # START → chat (interview turn), writer (generate), job (parse posting) or match (re-check fit)
    builder.add_conditional_edges(START, route_start, {"chat": "chat", "writer": "writer", "job": "job", "match": "match"})

    # chat → extractor (always extract facts after chatting)
    builder.add_edge("chat", "extractor")
    builder.add_edge("extractor", END)

    # a new job description is matched straight away
    builder.add_edge("job", "match")
    builder.add_edge("match", END)

    builder.add_edge("writer", END)

    # Compile graph with memory (checkpointer)
    return builder.compile(checkpointer=checkpointer or InMemorySaver())


class ResumeSession:
    """Thin wrapper around the graph used by both the CLI and the web UI."""

    def __init__(self, graph=None, thread_id: str = "resume-session", model=None):
        self.graph = graph or define_graph()
        self.model = model or llm
        self.config = {"configurable": {"thread_id": thread_id}}

    def state(self) -> models.ResumeState:
        values = self.graph.get_state(self.config).values
        return models.ResumeState(**values) if values else models.ResumeState()

    def chat(self, text: str) -> str:
        result = self.graph.invoke({"messages": [HumanMessage(content=text)], "command": "chat"}, config=self.config)
        return result["messages"][-1].content

    def load_job(self, text: str) -> str:
        result = self.graph.invoke({"command": "job", "job_text": text}, config=self.config)
        if not result.get("job"):
            return "Sorry, I could not read that job description. Try pasting the plain text of the posting."
        return self.report()

    def match(self) -> str:
        if not self.state().job:
            return "No job description loaded yet. Use /job first."
        self.graph.invoke({"command": "match"}, config=self.config)
        return self.report()

    def report(self) -> str:
        state = self.state()
        if not (state.job and state.match):
            return "No job match yet."
        return nodes.format_match_report(state.job, state.match, state.assessment)

    def generate(self) -> str:
        result = self.graph.invoke({"command": "generate"}, config=self.config)
        markdown = result.get("resume_markdown") or ""
        return (
            f"{markdown}\n---\nSaved {config.RESUME_OUTPUT_PATH}, {config.RESUME_HTML_PATH} "
            f"and {config.RESUME_PDF_PATH} ({config.MAX_PAGES} page limit)."
        )

    def set_facts(self, facts: models.ResumeFacts):
        self.graph.update_state(self.config, {"facts": facts}, as_node="extractor")

    def import_transcript(self, path: str) -> str:
        facts = nodes.extract_from_file(path, self.model)
        self.set_facts(nodes.merge_facts(self.state().facts, facts))
        return f"Imported {path}.\n{self.state().facts.model_dump_json(indent=2, exclude_defaults=True)}"

    def load_saved_facts(self) -> str:
        facts = nodes.load_latest_facts()
        if not facts:
            return f"No saved facts found in {config.DB_PATH}."
        self.set_facts(facts)
        return "Loaded the last saved facts."

    def handle(self, text: str) -> str:
        """Dispatch one line of user input (commands or a normal interview answer)."""
        stripped = text.strip()
        command, _, rest = stripped.partition(" ")
        command = command.lower()
        if nodes.is_generate_command(stripped):
            return self.generate()
        if command in ("/job", "/jd"):
            rest = rest.strip()
            if rest and os.path.isfile(rest):
                with open(rest) as f:
                    rest = f.read()
            return self.load_job(rest) if rest else "Paste the job description after /job."
        if command == "/match":
            return self.match()
        if command == "/facts":
            return self.state().facts.model_dump_json(indent=2, exclude_defaults=True)
        if command == "/import":
            return self.import_transcript(rest.strip()) if os.path.isfile(rest.strip()) else f"File not found: {rest}"
        if command == "/load":
            return self.load_saved_facts()
        if command == "/help":
            return HELP
        return self.chat(stripped)


def read_multiline(prompt: str) -> str:
    print(prompt)
    lines = []
    for line in sys.stdin:
        if line.strip() == "END":
            break
        lines.append(line)
    return "".join(lines)


if __name__ == "__main__":
    session = ResumeSession()

    print("Resume Assistant\n" + HELP)

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input:
            continue
        if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
            break
        if user_input.lower() in ("/job", "/jd"):
            user_input = "/job " + read_multiline("Paste the job description, then a line with just END:")

        print(f"\nAI: {session.handle(user_input)}\n")
