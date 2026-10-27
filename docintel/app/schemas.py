from typing import List, Optional

from pydantic import BaseModel


class Profile(BaseModel):
    name: str
    skills: List[str]
    years_experience: int


class MatchRequest(BaseModel):
    profile: dict
    job_description: str


class MatchResult(BaseModel):
    score: int
    matched_skills: List[str]
    missing_skills: Optional[List[str]] = None
    rationale: str


# async job response for POST /extract
class ExtractJobAccepted(BaseModel):
    id: str
    status: str = "pending"
    poll_url: str


class MatchResponse(MatchResult):
    id: str


# result polling response
class ResultResponse(BaseModel):
    id: str
    kind: str
    status: str
    result: Optional[dict] = None
    error: Optional[str] = None
