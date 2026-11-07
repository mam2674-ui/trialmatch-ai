"""Biomedical sentence embeddings for trial sections, stored in pgvector.

Trials are split into meaningful sections (title+conditions, summary, interventions, inclusion,
exclusion). Long sections are chunked. Embeddings are recomputed only when the section text or the
model changes (tracked by a SHA-256 text hash).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import threading

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import TrialEmbedding
from app.schemas.trial import NormalizedTrial

logger = logging.getLogger("trialmatch.embeddings")
MAX_CHUNK_CHARS = 1200


class EmbeddingModel:
    """Lazy, thread-safe wrapper around a SentenceTransformer."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer
                logger.info("loading embedding model %s", self.model_name)
                self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, get_settings().embedding_dim), dtype=np.float32)
        return self._load().encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)


_model: EmbeddingModel | None = None


def get_embedder() -> EmbeddingModel | None:
    global _model
    s = get_settings()
    if not s.embeddings_enabled:
        return None
    if _model is None:
        _model = EmbeddingModel(s.embedding_model)
    return _model


def set_embedder(model) -> None:
    global _model
    _model = model


def _chunks(text: str) -> list[str]:
    text = text.strip()
    if len(text) <= MAX_CHUNK_CHARS:
        return [text] if text else []
    out, buf = [], ""
    for para in text.split("\n"):
        if len(buf) + len(para) > MAX_CHUNK_CHARS and buf:
            out.append(buf.strip())
            buf = ""
        buf += para + "\n"
    if buf.strip():
        out.append(buf.strip())
    return [c[: MAX_CHUNK_CHARS * 2] for c in out][:6]


def trial_sections(t: NormalizedTrial) -> dict[str, list[str]]:
    head = f"{t.brief_title}. Conditions: {', '.join(t.conditions)}. Keywords: {', '.join(t.keywords)}."
    interventions = "; ".join(f"{i.type or ''} {i.name}: {i.description or ''}".strip() for i in t.interventions)
    inclusion = "\n".join(c.text for c in t.criteria if c.kind in ("inclusion", "unclassified"))
    exclusion = "\n".join(c.text for c in t.criteria if c.kind == "exclusion")
    return {
        "title_conditions": _chunks(head),
        "summary": _chunks(t.brief_summary or ""),
        "interventions": _chunks(interventions),
        "inclusion": _chunks(inclusion),
        "exclusion": _chunks(exclusion),
    }


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def ensure_embeddings(db: Session, trials: list[NormalizedTrial], embedder: EmbeddingModel) -> int:
    """Embed any trial sections that are missing or stale. Returns the number of chunks encoded."""
    existing = {(e.nct_id, e.section, e.chunk_index): e.text_hash for e in db.scalars(
        select(TrialEmbedding).where(TrialEmbedding.nct_id.in_([t.nct_id for t in trials]),
                                     TrialEmbedding.model_name == embedder.model_name))}
    # A trial is re-embedded as a whole whenever any of its chunks changed (or chunk counts differ),
    # so a partial update can never leave orphaned vectors behind.
    todo: list[tuple[str, str, int, str]] = []
    stale_trials: list[str] = []
    for t in trials:
        wanted = {(t.nct_id, s, i): _hash(c) for s, chunks in trial_sections(t).items() for i, c in enumerate(chunks)}
        have = {k: h for k, h in existing.items() if k[0] == t.nct_id}
        if wanted != have:
            stale_trials.append(t.nct_id)
            todo += [(t.nct_id, s, i, c) for s, chunks in trial_sections(t).items() for i, c in enumerate(chunks)]
    if not todo:
        return 0
    vectors = await asyncio.to_thread(embedder.encode, [c for *_, c in todo])
    db.execute(delete(TrialEmbedding).where(TrialEmbedding.nct_id.in_(stale_trials),
                                            TrialEmbedding.model_name == embedder.model_name))
    for (nct, section, i, chunk), vec in zip(todo, vectors):
        db.add(TrialEmbedding(nct_id=nct, section=section, chunk_index=i, text_hash=_hash(chunk),
                              model_name=embedder.model_name, embedding=vec.tolist()))
    db.flush()
    return len(todo)


def semantic_scores(db: Session, query_vec: np.ndarray, nct_ids: list[str], model_name: str) -> dict[str, dict]:
    """Cosine similarity per trial (pgvector `<=>`), best chunk overall and per section."""
    if not nct_ids:
        return {}
    dist = TrialEmbedding.embedding.cosine_distance(query_vec.tolist())
    rows = db.execute(
        select(TrialEmbedding.nct_id, TrialEmbedding.section, (1 - dist).label("sim"))
        .where(TrialEmbedding.nct_id.in_(nct_ids), TrialEmbedding.model_name == model_name)
        .order_by(dist)
    ).all()
    out: dict[str, dict] = {}
    for nct, section, sim in rows:
        d = out.setdefault(nct, {"best": float(sim), "best_section": section, "sections": {}})
        d["sections"].setdefault(section, float(sim))
    return out
