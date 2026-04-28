

from pydantic import BaseModel, Field
from typing import Annotated, List, Optional, Literal
from langgraph.graph.message import add_messages

class PersonalDetails(BaseModel):
    """
    Personal details of the candidate
    """

    first_name: Optional[str] = Field(default=None, description="first_name of the candidate")
    last_name: Optional[str] = Field(default=None, description="last_name of the candidate")
    city: Optional[str] = Field(default=None, description="city or metro area")
    email: Optional[str] = Field(default=None, description='email of the candidate')
    phone_number: Optional[str] = Field(default=None, description="phone number")

class Education(BaseModel):
    """
    education of the candidate
    """

    university: str = Field(alias="university", description='which university was this completed at')
    degree: str = Field(alias="degree", description="what was the degree")
    year_started: int = Field(alias = "year", description="what year did you start this degree")
    year_graduated: int = Field(alias = "year_graduated", description="what year did you graduate from this degree")
    additional_details: str = Field(alias="additional_details", description="any other details about the time here")

class ProfessionalExperience(BaseModel):
    """
    professional experience of the candidate
    """

    company: str = Field(alias="company", description="the company you worked for or contracted under")
    position: str = Field(alias="position", description="what was the job title or position")
    start_year: int = Field(alias="start_year", description="which month did the position start")
    end_year: int = Field(alias="end_year", description="when did the position end")
    start_month: int = Field(alias="start_month", description="which month did the position start")
    end_month: int = Field(alias="end_month", description="which month did the position end")

class Awards(BaseModel):
    """
    The awardds won by the candidate and the details of the awards
    """
    name: str = Field(alias='name', description='name of the award')
    source: str = Field(alias='source', description='source of the award: ARM, AMD, Hack Harvard, etc') 
    details: str = Field(alias='details', description='details about what the award was for or other information about the award')

class OtherDetails(BaseModel):
    """
    Any details that can't be directly classified needly into the other fields
    """
    name: str = Field(alias='name', description='name for detail not captured by other fields')
    details: str = Field(alias='details', description='more free form details not captured by other categories')



class ResumeFacts(BaseModel):
    """
    Details about the resume from raw text including personal details,
      skills, education, awards and any other detils that can't be directly categorized
    """

    personal_details: PersonalDetails = Field(default_factory=PersonalDetails)
    skills: List[str] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
    profession: List[ProfessionalExperience] = Field(default_factory=list)
    awards: List[Awards] = Field(default_factory=list)
    other_details: List[OtherDetails] = Field(default_factory=list) 

class ResumeState(BaseModel):
    # 'add_messages' is the reducer that appends new AI/Human messages
    messages: Annotated[list, add_messages] = Field(default_factory=list)
    # The 'Hard Memory' for resume content
    facts: ResumeFacts = Field(default_factory=ResumeFacts)