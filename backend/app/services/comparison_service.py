"""Side-by-side comparison of study characteristics and preliminary eligibility. No effectiveness ranking."""

from __future__ import annotations

from app.schemas.match import CompareResponse, CompareRow, MatchResult
from app.schemas.trial import NormalizedTrial


def _sites(t: NormalizedTrial, limit: int = 4) -> list[str]:
    out = []
    for s in t.locations[:limit]:
        place = ", ".join(x for x in [s.city, s.state, s.country] if x)
        out.append(f"{s.facility or 'Site'} — {place}{' (' + s.status.replace('_', ' ').lower() + ')' if s.status else ''}")
    if len(t.locations) > limit:
        out.append(f"+{len(t.locations) - limit} more sites")
    return out or ["No locations listed"]


def compare(trials: list[NormalizedTrial], matches: dict[str, MatchResult]) -> CompareResponse:
    ids = [t.nct_id for t in trials]

    def row(field: str, fn) -> CompareRow:
        return CompareRow(field=field, values={t.nct_id: fn(t, matches.get(t.nct_id)) for t in trials})

    rows = [
        row("Study title", lambda t, m: t.brief_title),
        row("Medical condition", lambda t, m: t.conditions or ["Not listed"]),
        row("Study phase", lambda t, m: ", ".join(p.replace("PHASE", "Phase ").replace("EARLY_", "Early ") for p in t.phases) or "Not applicable"),
        row("Recruitment status", lambda t, m: (t.overall_status or "Unknown").replace("_", " ").title()),
        row("Treatments being investigated", lambda t, m: [f"{i.name} ({(i.type or '').lower()})" for i in t.interventions] or ["Not listed"]),
        row("Preliminary eligibility", lambda t, m: f"{m.eligibility.label} — {m.eligibility.headline}" if m else "Not assessed (run a match first)"),
        row("Relevant criteria that appear met", lambda t, m: [f"[{c.criterion_id}] {c.criterion_text[:140]}" for c in m.criteria
                                                                if c.assessment == "MET" and not c.is_blocker and c.kind != "structured"][:5] if m else None),
        row("Possible exclusion concerns", lambda t, m: [f"[{c.criterion_id}] {c.explanation}" for c in m.criteria if c.is_blocker][:5] or ["None identified"] if m else None),
        row("Important unanswered questions", lambda t, m: [c.question or f"[{c.criterion_id}] {c.criterion_text[:120]}" for c in m.criteria
                                                             if c.assessment == "UNKNOWN" and c.impact == "high"][:5] or ["None identified"] if m else None),
        row("Study locations", lambda t, m: _sites(t)),
        row("Travel considerations", lambda t, m: (f"Nearest site ≈{m.distance_miles:.0f} miles" if m and m.distance_miles is not None
                                                   else "Distance unavailable") + f"; {len(t.locations)} site(s) total"),
        row("Sponsor", lambda t, m: t.sponsor or "Not listed"),
        row("Last updated on ClinicalTrials.gov", lambda t, m: t.last_update_post_date or "Unknown"),
        row("Official study link", lambda t, m: t.url),
    ]
    return CompareResponse(nct_ids=ids, rows=rows)
