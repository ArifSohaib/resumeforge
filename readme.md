Resume Vault

A local-first, LLM-powered system that converts natural conversation into a structured, queryable resume using LangGraph, DuckDB, and Parquet.

---

##  Overview

**Resume Vault** is not just a resume generator—it is a **structured memory system for your professional experience**.

Instead of manually editing resumes, you:

1. Chat naturally about your experience
2. Extract structured data using an LLM
3. Store it in a local database (DuckDB + Parquet)
4. Generate high-quality, ATS-optimized resumes

---

##  Architecture

```text
User Conversation
        ↓
LangGraph (state machine)
        ↓
Extractor (LLM → structured data)
        ↓
ResumeFacts (Pydantic schema)
        ↓
DuckDB (resume_vault.db)
        ↓
Parquet backup (resume_backup.parquet)
        ↓
Resume Generator (Markdown output)
```

---

##  Tech Stack

* **LLM:** Ollama (Gemma 4)
* **Orchestration:** LangGraph
* **Schema Validation:** Pydantic
* **Database:** DuckDB
* **Storage Format:** Parquet
* **Backend/UI:** FastAPI (minimal chat interface)

---

## Features

* 🧠 Conversational resume building
* 📊 Structured data extraction (Pydantic schema)
* 💾 Local-first storage (DuckDB + Parquet)
* 🔁 Incremental updates via chat
* 📄 Markdown resume generation
* 🔍 Foundation for querying and filtering experience

---

##  Project Structure

```bash
resume-vault/
├── models/
│   └── models.py          # Pydantic schemas (ResumeFacts, etc.)
├── prompts/
│   └── system_prompt.py   # System prompt for LLM behavior
├── nodes/
│   └── nodes.py           # LangGraph nodes (chat, extractor, writer)
├── main.py                # Graph definition + CLI entry point
├── app.py                 # FastAPI chat UI
├── resume_vault.db        # DuckDB database (will be generated after interview)
├── resume_backup.parquet  # Parquet backup (will be generated after interview)
├── resume_draft.md        # Generated resume
```

---

##  How It Works

### 1. Chat Loop

The system interacts with the user using a structured interview strategy:

* asks one question at a time
* focuses on missing or weak resume sections

---

### 2. Extraction Layer

The LLM converts conversation into structured data:

```python
class ResumeFacts(BaseModel):
    personal_details: PersonalDetails
    skills: List[str]
    education: List[Education]
    profession: List[ProfessionalExperience]
    awards: List[Awards]
    other_details: List[OtherDetails]
```

---

### 3. Storage Layer

Data is persisted locally using:

* DuckDB (analytical queries)
* Parquet (portable backup)
To check what is stored use:
```python
import duckdb

filepath = "resume_vault.parquet"
saved_candidate_data = duckdb.query(f"select * from '{filepath}'").db()

```

---

### 4. Resume Generation

Structured data is converted into an ATS-friendly Markdown resume.

---

## 🖥️ Running the Project

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

---

### 2. Start Ollama

```bash
ollama run gemma4:e4b
```



---

### 3. Run CLI version (UI needs more polish)

```bash
python main.py
```

---

### 4. Run web UI (UI needs more polish)

```bash
fastapi run app.py
```

Open:

```
http://127.0.0.1:8000
```

---

## 🔄 Recovering from Saved Conversations
For now it is a good idea to save the conversation to a txt file for later reference. The web ui is designed to allow this.

---

## 📊 Future Improvements

* [ ] Add project schema (structured portfolio section)
* [ ] Resume tailoring for specific job descriptions
* [ ] DuckDB query interface (filter by skills, roles, etc.)
* [ ] Persistent LangGraph checkpointing in database
* [ ] Multi-resume support (resume_id)
* [ ] Streaming responses in UI

---




## 👤 Author

Muhammad Sohaib Arif

---
