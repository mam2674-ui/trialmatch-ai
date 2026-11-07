import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import meta, patients, trials
from app.core.config import get_settings
from app.core.db import session_factory
from app.core.logging import AccessLogMiddleware, configure_logging
from app.services import session_service
from app.services.clinicaltrials_client import ClinicalTrialsClient

logger = logging.getLogger("trialmatch")


async def _purge_loop() -> None:
    while True:
        try:
            with session_factory()() as db:
                n = session_service.purge_expired(db)
                if n:
                    logger.info("purged %d expired matching sessions", n)
        except Exception as exc:  # never crash the app over housekeeping
            logger.warning("session purge failed: %s", type(exc).__name__)
        await asyncio.sleep(300)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    app.state.ctgov = ClinicalTrialsClient()
    purge = asyncio.create_task(_purge_loop())
    yield
    purge.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await purge
    await app.state.ctgov.aclose()


settings = get_settings()
app = FastAPI(
    title="TrialMatch AI API",
    version="0.1.0",
    description=(
        "Find clinical trials that fit a medical profile. Retrieves live records from ClinicalTrials.gov, ranks them "
        "with hybrid semantic + keyword retrieval, and produces preliminary, evidence-grounded eligibility screening.\n\n"
        "**Not medical advice. Assessments are preliminary and never determine eligibility; final eligibility is "
        "established by each study's research team.** Do not submit identifying information."
    ),
    lifespan=lifespan,
)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST", "DELETE"],
                   allow_headers=["Content-Type"], allow_credentials=False)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    # Do not echo submitted values back (they may contain medical details); report locations and messages only.
    errors = [{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store"
    return resp


app.include_router(meta.router)
app.include_router(patients.router)
app.include_router(trials.router)
