
from models import models 
from langchain_core.messages import SystemMessage
from prompts import system_prompt
from typing import Literal 
from langchain_ollama.chat_models import ChatOllama
from langchain_core.messages import HumanMessage, AIMessage
import pandas as pd 
import duckdb 
import logging 

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def chat_node(state: models.ResumeState, llm:ChatOllama):
    # Prepare the context: What do we already know?
    current_facts_summary = f"Current Resume Data: {state.facts.model_dump_json()}"
    
    # Construct the message list
    messages = [
        SystemMessage(content=system_prompt.SYSTEM_PROMPT),
        SystemMessage(content=current_facts_summary)
    ] + state.messages
    
    # Call Gemma 4
    response = llm.invoke(messages)
    
    return {"messages": [response]}


def extractor_node(state: models.ResumeState, llm):
    structured_llm = llm.with_structured_output(models.ResumeFacts)

    raw = structured_llm.invoke(state.messages)

    try:
        validated = models.ResumeFacts.model_validate(raw)
    except Exception as e:
        print("Validation failed, falling back:", e)
        validated = state.facts  # keep previous good state

    return {"facts": validated}


def writer_node(state: models.ResumeState, llm:ChatOllama):
    content = llm.invoke(
        f"Generate an ATS-friendly markdown resume using these facts: {state.facts}"
    )
    # Here you would trigger your file-saving tool
    with open("resume_draft.md", "w") as f:
        f.write(content.content)
    save_to_local_db(state.facts)
    return {"messages": [content]}


def should_continue(state: models.ResumeState) -> Literal["writer", "chat"]:
    # Simple logic: If the user says "generate" or "done", go to writer
    last_message = state.messages[-1].content.lower()
    if "generate" in last_message or "done" in last_message:
        return "writer"
    return "chat"

def load_txt_conversation(path: str):
    messages = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            if line.lower().startswith("you:"):
                messages.append(HumanMessage(content=line[4:].strip()))
            elif line.lower().startswith("ai:"):
                messages.append(AIMessage(content=line[3:].strip()))
    return messages

def extract_from_file(graph, path: str):
    messages = load_txt_conversation(path)

    result = graph.invoke(
        {"messages": messages},
        config={"configurable": {"thread_id": "recovered-session"}}
    )

    return result["facts"]

def save_to_local_db(facts: models.ResumeFacts):
    # Convert Pydantic to a flat dictionary or DataFrame
    df = pd.DataFrame([facts.model_dump()])
    
    # Connect to local file and write
    con = duckdb.connect("resume_vault.db")
    con.execute("""
        CREATE TABLE IF NOT EXISTS history AS 
        SELECT * FROM df LIMIT 0
        """)
    con.execute("INSERT INTO history SELECT * FROM df")
    con.execute("INSERT INTO history SELECT * FROM df")
    
    # Also save a snapshot as Parquet for long-term backup
    con.execute("COPY history TO 'resume_backup.parquet' (FORMAT PARQUET)")
    logger.info("Resume facts vaulted successfully.")