from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import llm_dep
from app.core.ratelimit import rate_limit
from app.data.demo_profiles import DEMOS
from app.schemas.match import FollowUpQuestion
from app.schemas.patient import ParseRequest, ParseResponse, PatientProfile
from app.services.followup_service import apply_answer
from app.services.llm import LLMClient
from app.services.profile_parser import parse_narrative

router = APIRouter(prefix="/api", tags=["patients"])


@router.post("/patients/parse", response_model=ParseResponse, dependencies=[Depends(rate_limit)],
             summary="Convert a natural-language description into a validated structured profile")
async def parse_patient(req: ParseRequest, llm: LLMClient = Depends(llm_dep)) -> ParseResponse:
    """The narrative is processed in memory only and never stored or logged. Every extracted value is
    labeled with its provenance and the verbatim phrase it came from; the user should review and correct
    the profile before matching."""
    res = await parse_narrative(req.narrative, llm)
    res.profile.is_demo = req.demo
    return res


class AnswerRequest(BaseModel):
    profile: PatientProfile
    question: FollowUpQuestion
    answer: str
    value: str | int | None = None


@router.post("/patients/answer", response_model=PatientProfile, summary="Apply a follow-up answer to the profile")
async def answer_question(req: AnswerRequest) -> PatientProfile:
    return apply_answer(req.profile, req.question, req.answer, req.value)


class DemoProfile(BaseModel):
    id: str
    title: str
    challenge: str
    narrative: str
    profile: PatientProfile


@router.get("/demo/profiles", response_model=list[DemoProfile], tags=["demo"],
            summary="Fictional demo patients (no real patient data)")
async def demo_profiles() -> list[DemoProfile]:
    return [DemoProfile(**d) for d in DEMOS]
