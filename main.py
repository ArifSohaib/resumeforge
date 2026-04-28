from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.runnables import RunnableWithMessageHistory
from langgraph.checkpoint.memory import InMemorySaver
import pandas as pd 
from langgraph.graph import StateGraph, START, END
import duckdb 
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
from models import models 
from nodes.nodes import chat_node, extractor_node, writer_node, should_continue
llm = ChatOllama(model="gemma4:e4b", temperature=0.2)


def route_after_extractor(state):
    last_message = state.messages[-1].content.lower()
    if "generate" in last_message or "done" in last_message:
        return "writer"
    return END

def define_graph():
    # Initialize graph with your state schema
    builder = StateGraph(models.ResumeState)

    # --- Add nodes ---
    builder.add_node("chat", lambda state: chat_node(state, llm))
    builder.add_node("extractor", lambda state: extractor_node(state, llm))
    builder.add_node("writer", lambda state: writer_node(state, llm))

    # --- Define flow ---
    # Start → chat
    builder.add_edge(START, "chat")

    # chat → extractor (always extract facts after chatting)
    builder.add_edge("chat", "extractor")

    # extractor → conditional branch
    builder.add_conditional_edges(
    "extractor",
    route_after_extractor,
        {
            "writer": "writer",
            END: END,
        },
    )
    

    # writer → END
    builder.add_edge("writer", END)

    # --- Add memory (checkpointer) ---
    checkpointer = InMemorySaver()

    # Compile graph
    graph = builder.compile(checkpointer=checkpointer)

    return graph


if __name__ == "__main__":
    graph = define_graph()

    config = {"configurable": {"thread_id": "resume-session"}}

    state = {"messages": []}

    print("Resume Assistant (type 'done' or 'generate' to finish)\n")

    while True:
        user_input = input("You: ")

        state["messages"].append(HumanMessage(content=user_input))

        result = graph.invoke(state, config=config)

        ai_message = result["messages"][-1]
        print(f"\nAI: {ai_message.content}\n")

        state = result

        if "generate" in user_input.lower() or "done" in user_input.lower():
            # Save to DuckDB + parquet after finalization
            save_to_local_db(result["facts"])
            break