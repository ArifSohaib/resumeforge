# Resume Vault

A local-first, LLM-powered system that converts natural conversation into a structured, queryable resume using LangGraph, DuckDB, and Parquet, and checks how well it fits a job description.

---

##  Overview

**Resume Vault** is not just a resume generator—it is a **structured memory system for your professional experience**.

Instead of manually editing resumes, you:

1. Chat naturally about your experience
2. Extract structured data using an LLM
3. Store it in a local database (DuckDB + Parquet)
4. Optionally paste a job description to see how well you match it and fill in the gaps
5. Generate an ATS-optimized resume (Markdown, HTML and PDF) that fits in 2 pages

Everything runs on your machine through Ollama; nothing is sent to a hosted LLM.

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

* **LLM:** Ollama (Gemma 4, `gemma4:e4b` by default)
* **Orchestration:** LangGraph
* **Schema Validation:** Pydantic
* **Database:** DuckDB
* **Storage Format:** Parquet
* **PDF rendering:** PyMuPDF + markdown-it-py
* **Backend/UI:** FastAPI (minimal chat interface)
* **Tests:** pytest (with a fake LLM)

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
resumeforge/
├── models/
│   └── models.py          # Pydantic schemas (ResumeFacts, JobDescription, MatchReport, ...)
├── prompts/
│   └── system_prompt.py   # Prompts for the interviewer, extractors, writer and assessment
├── nodes/
│   ├── nodes.py           # LangGraph nodes (chat, extractor, job, match, writer) + persistence
│   ├── merge.py           # Deterministic merge of newly extracted facts
│   ├── matching.py        # Deterministic resume ↔ job matching
│   └── render.py          # Markdown/HTML rendering and PDF page counting
├── tests/                 # pytest suite (uses a fake LLM, no Ollama needed)
├── config.py              # Model, context size, page limit and generation budgets
├── main.py                # Graph definition + CLI entry point
├── app.py                 # FastAPI chat UI
└── pyproject.toml         # Dependencies (managed with uv)
```

Files created when you use it (all git-ignored):

| File | What it is |
| --- | --- |
| `resume_draft.md` | Generated resume as editable Markdown |
| `resume_draft.html` | Same resume as a styled page for preview or printing |
| `resume_draft.pdf` | The PDF whose pages were counted; this is the one to send |
| `resume_vault.db` | DuckDB database with every saved version of your facts and every job match |
| `resume_backup.parquet` | Parquet copy of the saved facts |

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

Use `/facts` at any time to see what has been captured so far.

---

### 3. Storage Layer

Data is persisted locally using:

* DuckDB (analytical queries)
* Parquet (portable backup)

Facts are saved each time a resume is generated, and every job match is saved when it is run.
Facts are stored as JSON, so adding fields to the schema never breaks an existing database.
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
   then projects, then bullets from the oldest roles, then the skill list. Every role keeps its
   title and dates.

The PDF you download is the one that was measured, so it is guaranteed to fit.
Markdown stays as the editable plain-text version; HTML is for preview/printing.
Printing the HTML from a browser can lay out slightly differently, so send the PDF.

---

### 5. Job description matching

Paste a job posting (`/job` in the CLI, or the "Target job" box in the web UI):

* the posting is parsed into a `JobDescription` (required/preferred skills, years of experience, education, ...)
* skills are matched deterministically against your skills, role technologies and achievements
  (with aliases such as k8s → Kubernetes) and a score out of 100 is computed
* the LLM gives a verdict (strong / moderate / weak), strengths, gaps and questions to confirm
* the interviewer then asks about the missing requirements; `/match` re-checks after you answer
* `generate` tailors the resume to the job: relevant bullets and skills are ordered first

The score weighs required skills at 70%, preferred skills at 20% and years of experience at 10%,
counting only the parts the posting actually states. Nothing is added to your resume unless
you said it in the interview.

---

## 🖥️ Running the Project

### Requirements

* Python 3.13
* [uv](https://docs.astral.sh/uv/)
* [Ollama](https://ollama.com)

### 1. Install dependencies

```bash
uv sync
```

On Linux, `pyproject.toml` installs the ROCm builds of PyTorch from the PyTorch index. They are
large and not used by the resume pipeline itself.

Run the tests (no Ollama needed):

```bash
uv run pytest
```

---

### 2. Start Ollama

Make sure the Ollama app or `ollama serve` is running, then download the model:

```bash
ollama pull gemma4:e4b
```

---

### 3. Run CLI version

```bash
uv run python main.py
```

| Command | What it does |
| --- | --- |
| `generate` or `done` | Write `resume_draft.md`, `.html` and `.pdf` (max 2 pages) |
| `/job <file or text>` | Add a job description and show the match report |
| `/job` | Paste a multi-line job description, then a line with just `END` |
| `/match` | Re-check the match with the latest facts |
| `/facts` | Show the facts collected so far |
| `/import <conversation.txt>` | Rebuild facts from a saved transcript |
| `/load` | Load the last facts saved in `resume_vault.db` |
| `/help` | Show the command list |
| `/quit` | Exit |

Anything else you type is an answer to the interviewer. Only an exact `generate` or `done`
triggers the writer, so a sentence like "I was done with that project in 2020" is just an answer.

---

### 4. Run web UI (UI needs more polish)

```bash
uv run python app.py
```

Open:

```
http://127.0.0.1:8000
```

The page has the chat, a "Generate resume" button, links to preview the HTML and download the
PDF or Markdown, a "Save conversation" button, and a "Target job" box with "Analyze job" and
"Re-check match" buttons. The CLI commands above also work in the chat box.

`uv run python app.py` only listens on your own machine. `fastapi run app.py` also works, but it
listens on all network interfaces, so other devices on your network can reach it.

---

### Example workflow

```text
You: Hi, I'm Jane Doe, a data engineer in Toronto
AI:  Nice to meet you, Jane. Where do you work now, and since when?
...
You: /job job_posting.txt
AI:  Job: Senior Data Engineer at Initech
     Match score: 72/100
     Verdict: moderate - ...
     Required skills NOT found: Spark
     ...
     Please confirm:
       - The role needs Spark - have you used it? If so, where and at what scale?
You: Yes, at Acme I moved our batch jobs to Spark on EMR and cut runtime by 60%
You: /match
You: generate
```

---

## ⚙️ Configuration

Set these environment variables to override the defaults in `config.py`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `RESUMEFORGE_MODEL` | `gemma4:e4b` | Ollama model name |
| `RESUMEFORGE_NUM_CTX` | `16384` | Context window in tokens |
| `RESUMEFORGE_CHAT_TEMPERATURE` | `0.3` | Temperature for the interviewer (extraction, matching and writing use 0) |
| `RESUMEFORGE_MAX_PAGES` | `2` | Page limit for the generated resume |
| `RESUMEFORGE_PAPER` | `letter` | `letter` or `a4` |
| `RESUMEFORGE_DB` | `resume_vault.db` | DuckDB database path |
| `RESUMEFORGE_FACTS_PARQUET` | `resume_backup.parquet` | Parquet backup path |
| `RESUMEFORGE_OUTPUT` | `resume_draft.md` | Markdown output path |
| `RESUMEFORGE_HTML` | `resume_draft.html` | HTML output path |
| `RESUMEFORGE_PDF` | `resume_draft.pdf` | PDF output path |

Bullets per role, characters per bullet and projects for each generation round are set in
`GENERATION_BUDGETS` in `config.py`. Font size and margins are `BASE_FONT_PT` and
`PAGE_MARGIN_PT`.

---

## 🔄 Recovering from Saved Conversations
Save the conversation with the "Save conversation" button in the web UI. To rebuild the facts from
a saved `You: ... / AI: ...` transcript, use `/import conversation.txt`. It extracts one exchange
at a time, so long transcripts are not cut off by the context window. `/load` restores the
last facts saved in `resume_vault.db`.

Interview state is kept in memory while the app runs, so restarting it starts a new interview
unless you `/load` or `/import`.

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
