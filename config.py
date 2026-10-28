import os

# --- LLM ---
MODEL_NAME = os.getenv("RESUMEFORGE_MODEL", "gemma4:e4b")
# Ollama's default context window is only a few thousand tokens and it silently
# drops the start of the prompt when it overflows, which loses interview details.
NUM_CTX = int(os.getenv("RESUMEFORGE_NUM_CTX", "16384"))
CHAT_TEMPERATURE = float(os.getenv("RESUMEFORGE_CHAT_TEMPERATURE", "0.3"))

# --- Storage ---
DB_PATH = os.getenv("RESUMEFORGE_DB", "resume_vault.db")
FACTS_PARQUET_PATH = os.getenv("RESUMEFORGE_FACTS_PARQUET", "resume_backup.parquet")
RESUME_OUTPUT_PATH = os.getenv("RESUMEFORGE_OUTPUT", "resume_draft.md")
RESUME_HTML_PATH = os.getenv("RESUMEFORGE_HTML", "resume_draft.html")
RESUME_PDF_PATH = os.getenv("RESUMEFORGE_PDF", "resume_draft.pdf")

# --- Resume length ---
# The writer renders the markdown to PDF, counts the pages and regenerates with the next,
# tighter budget until it fits. If every budget is still too long it trims deterministically.
MAX_PAGES = int(os.getenv("RESUMEFORGE_MAX_PAGES", "2"))
PAPER_SIZE = os.getenv("RESUMEFORGE_PAPER", "letter")  # "letter" or "a4"
PAGE_MARGIN_PT = 40
BASE_FONT_PT = 10.5

# Each round: bullets per role (most recent role first; later roles reuse the last value),
# max characters per bullet, projects shown, bullets per project.
GENERATION_BUDGETS = [
    {"bullets_per_role": [5, 4, 3, 2], "max_chars": 190, "max_projects": 3, "bullets_per_project": 2},
    {"bullets_per_role": [4, 3, 2, 2], "max_chars": 170, "max_projects": 2, "bullets_per_project": 2},
    {"bullets_per_role": [4, 3, 2, 1], "max_chars": 150, "max_projects": 2, "bullets_per_project": 1},
    {"bullets_per_role": [3, 2, 2, 1], "max_chars": 140, "max_projects": 1, "bullets_per_project": 1},
]
MAX_SKILLS = 30
