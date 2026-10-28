from typing import List, Optional

from pydantic import BaseModel, Field


class Profile(BaseModel):
    name: str = Field(..., description="Candidate full name", examples=["Jane Doe"])
    skills: List[str] = Field(..., description="List of detected technical skills", examples=[["python", "fastapi", "docker"]])
    years_experience: int = Field(..., description="Estimated years of professional experience", examples=[5])


class MatchRequest(BaseModel):
    profile: dict = Field(
        ...,
        description="Extracted candidate profile containing skills",
        examples=[{"name": "Jane Doe", "skills": ["python", "fastapi"], "years_experience": 5}],
    )
    job_description: str = Field(
        ...,
        description="Target job description requirements",
        examples=["Looking for a Senior Python Developer with FastAPI and Docker experience."],
    )


class MatchResult(BaseModel):
    score: int = Field(..., description="Match score from 0 to 100", examples=[85])
    matched_skills: List[str] = Field(..., description="Skills present in both profile and job description", examples=[["python", "fastapi"]])
    missing_skills: Optional[List[str]] = Field(default=[], description="Skills required by job description but missing from profile", examples=[["docker"]])
    rationale: str = Field(..., description="Explanation of match calculation", examples=["Candidate matches 2/3 required skills."])


# async job response for POST /extract
class ExtractJobAccepted(BaseModel):
    id: str = Field(..., description="Unique job identifier", examples=["a1b2c3d4e5f6"])
    status: str = Field(default="pending", description="Current status of the extraction task", examples=["pending"])
    poll_url: str = Field(..., description="Endpoint URL to check task completion", examples=["/results/a1b2c3d4e5f6"])


class MatchResponse(MatchResult):
    id: str = Field(..., description="Unique result identifier", examples=["f6e5d4c3b2a1"])


# ticket 8: batch matching models
class BatchCandidate(BaseModel):
    candidate_id: str = Field(..., description="Client-side candidate identifier", examples=["cand_01"])
    name: str = Field(..., description="Candidate name", examples=["Jane Doe"])
    skills: List[str] = Field(..., description="Candidate skill list", examples=[["python", "fastapi", "docker"]])
    years_experience: int = Field(default=0, description="Years of experience", examples=[5])


class BatchMatchRequest(BaseModel):
    job_description: str = Field(
        ...,
        description="Job requirements against which candidates will be ranked",
        examples=["Senior Backend Engineer with Python, FastAPI, and Kubernetes experience."],
    )
    candidates: List[BatchCandidate] = Field(
        ...,
        description="List of candidate profiles to evaluate and rank",
    )


class RankedCandidate(BaseModel):
    rank: int = Field(..., description="Position in ranked shortlist (1 = best fit)", examples=[1])
    candidate_id: str = Field(..., description="Candidate ID", examples=["cand_01"])
    name: str = Field(..., description="Candidate name", examples=["Jane Doe"])
    score: int = Field(..., description="Calculated match score (0-100)", examples=[90])
    matched_skills: List[str] = Field(..., description="Matching skills", examples=[["python", "fastapi"]])
    missing_skills: List[str] = Field(..., description="Missing skills", examples=[["kubernetes"]])
    rationale: str = Field(..., description="Evaluation rationale")


class BatchMatchResponse(BaseModel):
    id: str = Field(..., description="Unique batch result ID", examples=["batch_98765"])
    total_candidates: int = Field(..., description="Total candidates evaluated", examples=[2])
    highest_score: int = Field(..., description="Highest score in batch", examples=[90])
    average_score: float = Field(..., description="Average match score across batch", examples=[65.5])
    rankings: List[RankedCandidate] = Field(..., description="Shortlist ranked descending by score")


# result polling response
class ResultResponse(BaseModel):
    id: str = Field(..., description="Result identifier")
    kind: str = Field(..., description="Result category: extract | match | batch_match")
    status: str = Field(..., description="Job status: pending | completed | failed")
    result: Optional[dict] = Field(default=None, description="Completed task output payload")
    error: Optional[str] = Field(default=None, description="Error message if task failed")


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Error message description")
