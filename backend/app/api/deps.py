from fastapi import HTTPException, Request

from app.services.clinicaltrials_client import ClinicalTrialsClient, CTGovError, CTGovUnavailable, InvalidNCTId, StudyNotFound
from app.services.llm import LLMClient, get_llm


def get_ctgov(request: Request) -> ClinicalTrialsClient:
    return request.app.state.ctgov


def llm_dep() -> LLMClient:
    return get_llm()


def ctgov_http_error(exc: CTGovError) -> HTTPException:
    if isinstance(exc, InvalidNCTId):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, StudyNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, CTGovUnavailable):
        return HTTPException(status_code=503, detail={
            "error": "live_data_unavailable",
            "message": "Live clinical trial data could not be retrieved from ClinicalTrials.gov right now. "
                       "No results are shown rather than outdated or simulated ones. Please try again shortly.",
        })
    return HTTPException(status_code=502, detail=str(exc))
