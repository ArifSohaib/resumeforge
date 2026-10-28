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
Extractor (LLM → facts from the latest exchange only)
        ↓
Deterministic merge into ResumeFacts (nothing already known is lost)
        ↓                                   Job description (/job)
        ↓                                           ↓
        ↓                                 JobDescription (LLM extraction)
        ↓                                           ↓
        ├──────────────→  Match report (deterministic) + suitability assessment (LLM)
        ↓
Writer: LLM rewrites bullets → Markdown → HTML → PDF → count pages
        ↺ regenerate with a tighter budget while pages > 2, then trim if still needed
        ↓
resume_draft.md / .html / .pdf  +  DuckDB (resume_vault.db) + Parquet backup
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
* 📄 Markdown, HTML and PDF resume generation, guaranteed to fit in 2 pages
* 🎯 Job description parsing, skill matching, suitability verdict and questions to confirm gaps
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
│   ├── nodes.py           # LangGraph nodes (chat, extractor, job, match, writer) + persistence
│   ├── merge.py           # Deterministic merge of newly extracted facts
│   ├── matching.py        # Deterministic resume ↔ job matching
│   └── render.py          # Markdown/HTML rendering and PDF page counting
├── tests/                 # pytest suite (uses a fake LLM, no Ollama needed)
├── config.py              # Model, context size, page limit and generation budgets
├── main.py                # Graph definition + CLI entry point
├── app.py                 # FastAPI chat UI
├── resume_vault.db        # DuckDB database (will be generated after interview)
├── resume_backup.parquet  # Parquet backup (will be generated after interview)
├── resume_draft.md        # Generated resume (also .html and .pdf)
```

---

##  How It Works

### 1. Chat Loop

The system interacts with the user using a structured interview strategy:

* asks one question at a time
* is given an explicit list of gaps (missing dates, roles without achievements or tools, ...)
* when a job description is loaded, asks about its requirements that the facts don't show yet

---

### 2. Extraction Layer

After every answer the LLM extracts only what is new in that exchange (the AI question plus
the user's answer), and the result is merged into the existing facts in Python. Facts already
collected are never overwritten by a forgetful model, partial answers ("I started in March")
are attached to the right role, and a failed extraction leaves the previous facts untouched.

```python
class ResumeFacts(BaseModel):
    personal_details: PersonalDetails
    skills: List[str]
    education: List[Education]
    profession: List[ProfessionalExperience]   # includes highlights and technologies per role
    projects: List[Project]
    awards: List[Awards]
    other_details: List[OtherDetails]
```

Ollama's context window is raised to 16k tokens (`RESUMEFORGE_NUM_CTX`) because the default
silently drops the beginning of long conversations.

---

### 3. Storage Layer

Data is persisted locally using:

* DuckDB (analytical queries)
* Parquet (portable backup)
To check what is stored use:
```python
import duckdb

con = duckdb.connect("resume_vault.db")
con.sql("select saved_at, facts_json from resume_facts order by saved_at desc").show()
con.sql("select saved_at, job_title, company, score from job_matches").show()
```

---

### 4. Resume Generation

Structured data is converted into an ATS-friendly, single-column resume:

1. The LLM writes a short summary and rewrites each role's highlights into a limited number of bullets
   (more for recent roles, fewer for older ones), using only the facts collected.
2. The resume is rendered to Markdown → HTML → PDF and the pages are counted.
3. If it is longer than `MAX_PAGES` (2), it is regenerated with the next, tighter budget in
   `config.GENERATION_BUDGETS` (fewer and shorter bullets, fewer projects).
4. If every budget is still too long, content is trimmed deterministically: extra sections,
   then projects, then bullets from the oldest roles, then the skill list.

The PDF you download is the one that was measured, so it is guaranteed to fit.
Markdown stays as the editable plain-text version; HTML is for preview/printing.

### 5. Job description matching

Paste a job posting (`/job` in the CLI, or the "Target job" box in the web UI):

* the posting is parsed into a `JobDescription` (required/preferred skills, years of experience, education, ...)
* skills are matched deterministically against your skills, role technologies and achievements
  (with aliases such as k8s → Kubernetes) and a score out of 100 is computed
* the LLM gives a verdict (strong / moderate / weak), strengths, gaps and questions to confirm
* the interviewer then asks about the missing requirements; `/match` re-checks after you answer
* `generate` tailors the resume to the job: relevant bullets and skills are ordered first

---

## 🖥️ Running the Project

### 1. Install dependencies

```bash
uv sync
```

Run the tests (no Ollama needed):

```bash
uv run pytest
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

Commands: `generate` (or `done`), `/job <file or text>`, `/match`, `/facts`,
`/import <conversation.txt>`, `/load` (last saved facts), `/help`, `/quit`.

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
Save the conversation with the "Save conversation" button in the web UI. To rebuild the facts from
a saved `You: ... / AI: ...` transcript, use `/import conversation.txt`. It extracts one exchange
at a time, so long transcripts are not cut off by the context window. `/load` restores the
last facts saved in `resume_vault.db`.

---

## 📊 Future Improvements

* [x] Add project schema (structured portfolio section)
* [x] Resume tailoring for specific job descriptions
* [ ] DuckDB query interface (filter by skills, roles, etc.)
* [ ] Persistent LangGraph checkpointing in database
* [ ] Multi-resume support (resume_id)
* [ ] Streaming responses in UI

---




## 👤 Author

Muhammad Sohaib Arif

---
