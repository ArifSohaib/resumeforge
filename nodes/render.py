"""
Markdown rendering of the resume and PDF page measurement.

The markdown is built deterministically from the facts plus the LLM-written bullets, so the
layout is stable between generation rounds and the page count is measured, not guessed.
"""
import calendar
import io
import logging
from dataclasses import dataclass, field, replace
from typing import List, Optional, Tuple

import pymupdf
from markdown_it import MarkdownIt

import config
from models import models
from nodes.matching import relevance

logger = logging.getLogger(__name__)

PDF_CSS = f"""
body {{ font-family: sans-serif; font-size: {config.BASE_FONT_PT}pt; line-height: 1.25; }}
h1 {{ font-size: 18pt; margin: 0 0 2pt 0; }}
h2 {{ font-size: 12pt; margin: 8pt 0 2pt 0; border-bottom: 1px solid #888; }}
h3 {{ font-size: {config.BASE_FONT_PT + 0.5}pt; margin: 5pt 0 0 0; }}
p {{ margin: 0 0 2pt 0; }}
ul {{ margin: 0 0 2pt 0; padding-left: 14pt; }}
li {{ margin: 0; }}
"""


@dataclass
class ResumeContent:
    summary: Optional[str] = None
    # Bullets per role, aligned with sort_roles(facts.profession)
    role_bullets: List[List[str]] = field(default_factory=list)
    # (project, bullets) for the projects that made the cut
    projects: List[Tuple[models.Project, List[str]]] = field(default_factory=list)
    max_skills: int = config.MAX_SKILLS
    include_awards: bool = True
    include_other: bool = True


def sort_roles(roles: List[models.ProfessionalExperience]) -> List[models.ProfessionalExperience]:
    """Most recent first: current roles, then by end date, then by start date."""
    def key(role):
        end = (9999, 12) if role.is_current else (role.end_year or 0, role.end_month or 0)
        return (end, role.start_year or 0, role.start_month or 0)
    return sorted(roles, key=key, reverse=True)


def _month_year(month: Optional[int], year: Optional[int]) -> str:
    if not year:
        return ""
    return f"{calendar.month_abbr[month]} {year}" if month else str(year)


def format_dates(role: models.ProfessionalExperience) -> str:
    start = _month_year(role.start_month, role.start_year)
    end = "Present" if role.is_current else _month_year(role.end_month, role.end_year)
    if start and end:
        return f"{start} – {end}"
    return start or end


def ordered_skills(facts: models.ResumeFacts, job: Optional[models.JobDescription], limit: int) -> List[str]:
    skills = list(dict.fromkeys(s.strip() for s in facts.skills if s and s.strip()))
    if job:
        # stable sort: skills the job asks for first, original order otherwise
        skills.sort(key=lambda s: -relevance(s, job))
    return skills[:limit]


def render_markdown(facts: models.ResumeFacts, content: ResumeContent,
                    job: Optional[models.JobDescription] = None) -> str:
    pd = facts.personal_details
    lines: List[str] = []

    name = " ".join(p for p in [pd.first_name, pd.last_name] if p) or "Your Name"
    lines.append(f"# {name}")
    if pd.headline:
        lines.append(f"**{pd.headline}**  ")
    contact = [c for c in [pd.city, pd.email, pd.phone_number, pd.linkedin, pd.github, pd.website] if c]
    if contact:
        lines.append(" · ".join(contact))
    lines.append("")

    if content.summary:
        lines += ["## Summary", "", content.summary.strip(), ""]

    skills = ordered_skills(facts, job, content.max_skills)
    if skills:
        lines += ["## Skills", "", " · ".join(skills), ""]

    roles = sort_roles(facts.profession)
    if roles:
        lines += ["## Experience", ""]
        for i, role in enumerate(roles):
            title = " — ".join(p for p in [role.position, role.company] if p)
            lines.append(f"### {title}")
            meta = " · ".join(p for p in [format_dates(role), role.location] if p)
            if meta:
                lines.append(f"*{meta}*")
            lines.append("")
            bullets = content.role_bullets[i] if i < len(content.role_bullets) else []
            lines += [f"- {b.strip()}" for b in bullets]
            lines.append("")

    if content.projects:
        lines += ["## Projects", ""]
        for project, bullets in content.projects:
            header = f"**{project.name}**" if project.name else ""
            if project.technologies:
                header += f" · {', '.join(project.technologies[:6])}"
            if project.url:
                header += f" · {project.url}"
            lines.append(header)
            lines.append("")
            lines += [f"- {b.strip()}" for b in bullets]
            lines.append("")

    if facts.education:
        lines += ["## Education", ""]
        for edu in sorted(facts.education, key=lambda e: e.year_graduated or 0, reverse=True):
            years = " – ".join(str(y) for y in [edu.year_started, edu.year_graduated] if y)
            text = ", ".join(p for p in [f"**{edu.degree}**" if edu.degree else None, edu.university] if p)
            if years:
                text += f" ({years})"
            if edu.additional_details:
                text += f" — {edu.additional_details}"
            lines += [f"- {text}"]
        lines.append("")

    if content.include_awards and facts.awards:
        lines += ["## Awards", ""]
        for award in facts.awards:
            text = f"**{award.name}**" if award.name else ""
            extra = ", ".join(str(p) for p in [award.source, award.year] if p)
            if extra:
                text += f", {extra}"
            if award.details:
                text += f" — {award.details}"
            lines.append(f"- {text}")
        lines.append("")

    if content.include_other and facts.other_details:
        lines += ["## Additional", ""]
        for other in facts.other_details:
            lines.append(f"- **{other.name}:** {other.details}" if other.name else f"- {other.details}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def markdown_to_html(markdown: str) -> str:
    """Standalone HTML page (same styles as the PDF) for previewing or printing from a browser."""
    body = MarkdownIt().render(markdown)
    page_css = f"@page {{ size: {config.PAPER_SIZE}; margin: {config.PAGE_MARGIN_PT}pt; }}"
    screen_css = "@media screen { body { max-width: 8.5in; margin: 24px auto; padding: 0 24px; } }"
    return (
        "<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\"><title>Resume</title>"
        f"<style>{PDF_CSS}{page_css}{screen_css}</style></head>\n<body>\n{body}</body></html>\n"
    )


def markdown_to_pdf(markdown: str, path: Optional[str] = None) -> int:
    """Lay the resume out as a PDF and return the page count. Writes the PDF to `path` if given."""
    html = MarkdownIt().render(markdown)
    story = pymupdf.Story(html=html, user_css=PDF_CSS)
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    page_rect = pymupdf.paper_rect(config.PAPER_SIZE)
    m = config.PAGE_MARGIN_PT
    content_rect = page_rect + (m, m, -m, -m)
    pages = 0
    more = True
    while more:
        device = writer.begin_page(page_rect)
        more, _ = story.place(content_rect)
        story.draw(device)
        writer.end_page()
        pages += 1
        if pages > 50:  # safety net against layout loops
            break
    writer.close()
    if path:
        with open(path, "wb") as f:
            f.write(buffer.getvalue())
    return pages


def _trim_steps(content: ResumeContent):
    """
    Yield progressively shorter versions of `content`, least valuable content first:
    extra sections, then projects, then bullets from the oldest roles (keeping at least one
    per role), then the skill list, then the remaining bullets of the oldest roles.
    """
    current = replace(content, role_bullets=[list(b) for b in content.role_bullets],
                      projects=[(p, list(b)) for p, b in content.projects])
    if current.include_other:
        current = replace(current, include_other=False)
        yield current
    while current.projects:
        current = replace(current, projects=current.projects[:-1])
        yield current
    for keep in (1, 0):
        changed = True
        while changed:
            changed = False
            for i in range(len(current.role_bullets) - 1, -1, -1):
                if len(current.role_bullets[i]) > max(keep, 1 if i == 0 else keep):
                    current.role_bullets[i] = current.role_bullets[i][:-1]
                    changed = True
                    yield current
                    break
        if keep == 1:
            while current.max_skills > 12:
                current = replace(current, max_skills=current.max_skills - 6)
                yield current
    if current.include_awards:
        current = replace(current, include_awards=False)
        yield current


def trim_to_fit(facts: models.ResumeFacts, content: ResumeContent,
                job: Optional[models.JobDescription], max_pages: int) -> Tuple[ResumeContent, str, int]:
    markdown = render_markdown(facts, content, job)
    pages = markdown_to_pdf(markdown)
    for candidate in _trim_steps(content):
        if pages <= max_pages:
            break
        content = candidate
        markdown = render_markdown(facts, content, job)
        pages = markdown_to_pdf(markdown)
    return content, markdown, pages
