

from pydantic import BaseModel, Field, field_validator
from typing import Annotated, List, Optional, Literal
from langgraph.graph.message import add_messages

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def coerce_month(value):
    """Accept 3, "3", "March", "mar" -> 3. Anything unusable becomes None."""
    if value is None:
        return None
    if isinstance(value, int):
        return value if 1 <= value <= 12 else None
    text = str(value).strip().lower()
    if text.isdigit():
        number = int(text)
        return number if 1 <= number <= 12 else None
    return MONTHS.get(text[:3])


def coerce_year(value):
    """Accept 2021 or "2021". "present", "current", "" etc. become None."""
    if value is None:
        return None
    if isinstance(value, int):
        return value if 1900 <= value <= 2100 else None
    text = str(value).strip()
    if text.isdigit() and 1900 <= int(text) <= 2100:
        return int(text)
    return None


class PersonalDetails(BaseModel):
    """
    Personal details of the candidate
    """

    first_name: Optional[str] = Field(default=None, description="first_name of the candidate")
    last_name: Optional[str] = Field(default=None, description="last_name of the candidate")
    headline: Optional[str] = Field(default=None, description="professional title the candidate goes by, e.g. 'Senior ML Engineer'")
    city: Optional[str] = Field(default=None, description="city or metro area")
    email: Optional[str] = Field(default=None, description='email of the candidate')
    phone_number: Optional[str] = Field(default=None, description="phone number")
    linkedin: Optional[str] = Field(default=None, description="LinkedIn profile URL")
    github: Optional[str] = Field(default=None, description="GitHub profile URL")
    website: Optional[str] = Field(default=None, description="personal website or portfolio URL")


class Education(BaseModel):
    """
    education of the candidate
    """

    university: Optional[str] = Field(default=None, description='which university was this completed at')
    degree: Optional[str] = Field(default=None, description="what was the degree, e.g. 'BSc Computer Science'")
    year_started: Optional[int] = Field(default=None, description="what year did you start this degree")
    year_graduated: Optional[int] = Field(default=None, description="what year did you graduate from this degree")
    additional_details: Optional[str] = Field(default=None, description="GPA, honours, thesis or other details about the time here")

    @field_validator("year_started", "year_graduated", mode="before")
    @classmethod
    def _years(cls, value):
        return coerce_year(value)


class ProfessionalExperience(BaseModel):
    """
    professional experience of the candidate
    """

    company: Optional[str] = Field(default=None, description="the company you worked for or contracted under")
    position: Optional[str] = Field(default=None, description="what was the job title or position")
    location: Optional[str] = Field(default=None, description="city or 'Remote'")
    start_month: Optional[int] = Field(default=None, description="month the position started, 1-12")
    start_year: Optional[int] = Field(default=None, description="year the position started")
    end_month: Optional[int] = Field(default=None, description="month the position ended, 1-12; null if current")
    end_year: Optional[int] = Field(default=None, description="year the position ended; null if current")
    is_current: Optional[bool] = Field(default=None, description="true if the candidate still holds this position")
    highlights: List[str] = Field(default_factory=list, description="achievements and responsibilities in this role, one per item, with tools and metrics where given")
    technologies: List[str] = Field(default_factory=list, description="tools, languages, frameworks and platforms used in this role")

    @field_validator("start_month", "end_month", mode="before")
    @classmethod
    def _months(cls, value):
        return coerce_month(value)

    @field_validator("start_year", "end_year", mode="before")
    @classmethod
    def _years(cls, value):
        return coerce_year(value)


class Project(BaseModel):
    """
    A personal, open-source, academic or side project
    """

    name: Optional[str] = Field(default=None, description="name of the project")
    description: Optional[str] = Field(default=None, description="one sentence on what the project is")
    highlights: List[str] = Field(default_factory=list, description="what the candidate built or achieved, with metrics where given")
    technologies: List[str] = Field(default_factory=list, description="tools and languages used")
    url: Optional[str] = Field(default=None, description="link to the project, if any")


class Awards(BaseModel):
    """
    The awards won by the candidate and the details of the awards
    """
    name: Optional[str] = Field(default=None, description='name of the award')
    source: Optional[str] = Field(default=None, description='source of the award: ARM, AMD, Hack Harvard, etc')
    year: Optional[int] = Field(default=None, description="year the award was received")
    details: Optional[str] = Field(default=None, description='details about what the award was for or other information about the award')

    @field_validator("year", mode="before")
    @classmethod
    def _year(cls, value):
        return coerce_year(value)


class OtherDetails(BaseModel):
    """
    Any details that can't be directly classified neatly into the other fields
    """
    name: Optional[str] = Field(default=None, description='name for detail not captured by other fields, e.g. Certification, Language, Publication')
    details: Optional[str] = Field(default=None, description='more free form details not captured by other categories')


class ResumeFacts(BaseModel):
    """
    Details about the resume from raw text including personal details,
      skills, education, experience, projects, awards and any other details that can't be directly categorized
    """

    personal_details: PersonalDetails = Field(default_factory=PersonalDetails)
    skills: List[str] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
    profession: List[ProfessionalExperience] = Field(default_factory=list)
    projects: List[Project] = Field(default_factory=list)
    awards: List[Awards] = Field(default_factory=list)
    other_details: List[OtherDetails] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Job description + suitability
# ---------------------------------------------------------------------------

class JobDescription(BaseModel):
    """
    Structured details extracted from a job posting
    """

    title: Optional[str] = Field(default=None, description="job title")
    company: Optional[str] = Field(default=None, description="hiring company")
    location: Optional[str] = Field(default=None, description="location or 'Remote'")
    seniority: Optional[str] = Field(default=None, description="e.g. Junior, Mid, Senior, Staff, Lead")
    employment_type: Optional[str] = Field(default=None, description="e.g. Full-time, Contract")
    min_years_experience: Optional[int] = Field(default=None, description="minimum years of experience required, if stated")
    required_skills: List[str] = Field(default_factory=list, description="must-have skills, tools and technologies, one short name each, e.g. 'Python', 'Kubernetes'")
    preferred_skills: List[str] = Field(default_factory=list, description="nice-to-have skills, one short name each")
    responsibilities: List[str] = Field(default_factory=list, description="main duties of the role, one per item")
    education_requirements: List[str] = Field(default_factory=list, description="required or preferred degrees")
    certifications: List[str] = Field(default_factory=list, description="required or preferred certifications")
    keywords: List[str] = Field(default_factory=list, description="other important domain keywords an ATS would scan for")

    @field_validator("min_years_experience", mode="before")
    @classmethod
    def _years(cls, value):
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None


class MatchReport(BaseModel):
    """
    Deterministic comparison of the resume facts against a job description
    """

    score: int = 0  # 0-100
    matched_required: List[str] = Field(default_factory=list)
    missing_required: List[str] = Field(default_factory=list)
    matched_preferred: List[str] = Field(default_factory=list)
    missing_preferred: List[str] = Field(default_factory=list)
    candidate_years_experience: float = 0.0
    required_years_experience: Optional[int] = None
    meets_experience: Optional[bool] = None


class SuitabilityAssessment(BaseModel):
    """
    LLM judgement of how well the candidate fits the job, grounded in the match report
    """

    verdict: Literal["strong", "moderate", "weak"] = Field(description="overall fit")
    summary: str = Field(description="two or three sentences explaining the verdict")
    strengths: List[str] = Field(default_factory=list, description="requirements the candidate clearly meets, with evidence from the facts")
    gaps: List[str] = Field(default_factory=list, description="requirements the facts do not show")
    questions_to_confirm: List[str] = Field(default_factory=list, description="questions to ask the candidate to confirm whether they actually have the missing experience")


# ---------------------------------------------------------------------------
# Writer helpers
# ---------------------------------------------------------------------------

class RoleBullets(BaseModel):
    """Rewritten resume bullets for one role"""
    bullets: List[str] = Field(default_factory=list, description="resume bullets, most relevant first")


class ResumeSummary(BaseModel):
    """Professional summary at the top of the resume"""
    summary: str = Field(description="two or three sentence professional summary")


Command = Literal["chat", "generate", "job", "match"]


class ResumeState(BaseModel):
    # 'add_messages' is the reducer that appends new AI/Human messages
    messages: Annotated[list, add_messages] = Field(default_factory=list)
    # The 'Hard Memory' for resume content
    facts: ResumeFacts = Field(default_factory=ResumeFacts)
    # What the graph should do on this invocation
    command: Command = "chat"
    # Raw job posting text supplied with command="job"
    job_text: Optional[str] = None
    job: Optional[JobDescription] = None
    match: Optional[MatchReport] = None
    assessment: Optional[SuitabilityAssessment] = None
    resume_markdown: Optional[str] = None
