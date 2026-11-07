import json
import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://trialmatch@localhost:5433/trialmatch_test")
os.environ["EMBEDDINGS_ENABLED"] = "false"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["ANTHROPIC_AUTH"] = "none"  # never use a developer's real `ant` login in tests
os.environ["GEOCODER"] = "none"
os.environ["RATE_LIMIT_PER_MINUTE"] = "0"

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import session_factory  # noqa: E402
from app.services import embedding_service, llm as llm_mod  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def db():
    s = session_factory()()
    s.execute(text("TRUNCATE clinical_trials, trial_data_refreshes, matching_sessions RESTART IDENTITY CASCADE"))
    s.commit()
    yield s
    s.close()


class FakeLLM:
    """Scripted LLM. `responses` maps output model name -> object, list (consumed in order) or callable(user)."""

    name = "fake"

    def __init__(self, responses: dict | None = None, error: Exception | None = None):
        self.responses = responses or {}
        self.error = error
        self.calls: list[tuple[str, str]] = []
        self.usage = llm_mod.UsageLog()

    async def structured(self, *, system, user, output, max_tokens=8000):
        self.calls.append((output.__name__, user))
        if self.error:
            raise self.error
        r = self.responses[output.__name__]
        if isinstance(r, list):
            r = r.pop(0)
        if callable(r):
            r = r(user)
        if isinstance(r, Exception):
            raise r
        return output.model_validate(r) if isinstance(r, dict) else r


class FakeEmbedder:
    """Deterministic bag-of-words hashing embedder (768-d) so pgvector code paths run without the real model."""

    model_name = "fake-hash-embedder"

    def encode(self, texts):
        out = np.zeros((len(texts), 768), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in t.lower().split():
                out[i, hash(w.strip(".,;:()")) % 768] += 1.0
            n = np.linalg.norm(out[i])
            if n:
                out[i] /= n
        return out


@pytest.fixture
def fake_embedder(monkeypatch):
    emb = FakeEmbedder()
    monkeypatch.setattr(embedding_service, "get_embedder", lambda: emb)
    from app.services import retrieval_service
    monkeypatch.setattr(retrieval_service, "get_embedder", lambda: emb)
    return emb


@pytest.fixture(autouse=True)
def _reset_llm():
    llm_mod.set_llm(None)
    get_settings.cache_clear()
    yield
    llm_mod.set_llm(None)
