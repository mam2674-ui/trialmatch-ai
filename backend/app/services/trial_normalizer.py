"""Convert raw ClinicalTrials.gov v2 study JSON into NormalizedTrial.

Rules: only copy what the API provides. Missing fields stay None/empty. Eligibility criteria are split
into individual items while preserving the original wording exactly (apart from un-escaping the
markdown backslashes the API adds, e.g. "\\>=").
"""

from __future__ import annotations

import re

from app.schemas.trial import Contact, Criterion, Intervention, NormalizedTrial, TrialSite

_AGE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(year|month|week|day|hour|minute)s?\s*$", re.I)
_AGE_FACTORS = {"year": 1.0, "month": 1 / 12, "week": 1 / 52.1775, "day": 1 / 365.25,
                "hour": 1 / 8766, "minute": 1 / 525960}


def parse_age_years(text: str | None) -> float | None:
    if not text:
        return None
    m = _AGE_RE.match(text)
    if not m:
        return None
    return round(float(m.group(1)) * _AGE_FACTORS[m.group(2).lower()], 4)


# A heading may stand alone ("Inclusion Criteria:"), be written as a bullet ("* Exclusion Criteria:"),
# or be fused with the first criterion ("Inclusion Criteria:The subjects must ...").
_HEADING_RE = re.compile(
    r"^\s*(?:[*\-•]\s+)?(?:#+\s*)?(?:\*\*)?\s*(?:key\s+|main\s+|general\s+|additional\s+)?"
    r"(inclusion|exclusion|eligibility)(?:\s+criteria)\b\s*(?:\*\*)?\s*:?\s*(?:\*\*)?\s*(.*)$",
    re.I,
)
_SHORT_HEADING_RE = re.compile(r"^\s*(?:\*\*)?(inclusion|exclusion)s?\s*:?\s*(?:\*\*)?\s*$", re.I)
_BULLET_RE = re.compile(r"^(\s*)(?:[*\-•·]|\d{1,3}[.)]|[a-zA-Z][.)]|\(\w{1,3}\))\s+(.*)$")
_UNESCAPE_RE = re.compile(r"\\([^\w\s])")


def clean_text(text: str) -> str:
    return _UNESCAPE_RE.sub(r"\1", text).replace("\r\n", "\n")


def split_criteria(eligibility_text: str | None) -> list[Criterion]:
    """Split free-text eligibility into criteria with stable ids I1.., E1.., U1.. (unclassified)."""
    if not eligibility_text or not eligibility_text.strip():
        return []
    text = clean_text(eligibility_text)
    kind = "unclassified"
    items: list[tuple[str, list[str]]] = []  # (kind, lines)
    current: list[str] | None = None
    current_indent = 0
    prev_blank = True

    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        if not line.strip():
            prev_blank = True
            continue
        short = _SHORT_HEADING_RE.match(line)
        heading = _HEADING_RE.match(line)
        if short or heading:
            word = (short or heading).group(1).lower()
            if word in ("inclusion", "exclusion"):
                kind = word
            current = None
            prev_blank = True
            rest = heading.group(2).strip() if heading and not short else ""
            if len(rest) < 4:
                continue
            line = rest  # fused heading: the remainder is the first criterion
        bullet = _BULLET_RE.match(line)
        if bullet:
            indent = len(bullet.group(1).expandtabs(4))
            body = bullet.group(2).strip()
            if current is not None and indent > current_indent:
                current.append("  - " + body)  # nested sub-item stays with its parent criterion
            else:
                current = [body]
                current_indent = indent
                items.append((kind, current))
        else:
            stripped = line.strip()
            continuation = (current is not None and not prev_blank) or (
                current is not None and stripped[:1].islower()
            )
            if continuation:
                current.append(stripped)
            else:
                current = [stripped]
                current_indent = len(line) - len(line.lstrip())
                items.append((kind, current))
        prev_blank = False

    counters = {"inclusion": 0, "exclusion": 0, "unclassified": 0}
    prefix = {"inclusion": "I", "exclusion": "E", "unclassified": "U"}
    out: list[Criterion] = []
    for k, lines in items:
        body = "\n".join(lines).strip()
        if len(body) < 3:
            continue
        counters[k] += 1
        out.append(Criterion(criterion_id=f"{prefix[k]}{counters[k]}", kind=k, text=body))
    return out


def _contacts(raw: list[dict] | None) -> list[Contact]:
    return [Contact(name=c.get("name"), role=c.get("role"), phone=c.get("phone"),
                    phone_ext=c.get("phoneExt"), email=c.get("email")) for c in (raw or [])]


def normalize_study(study: dict) -> NormalizedTrial:
    ps = study.get("protocolSection", {})
    ident = ps.get("identificationModule", {})
    status = ps.get("statusModule", {})
    desc = ps.get("descriptionModule", {})
    cond = ps.get("conditionsModule", {})
    design = ps.get("designModule", {})
    arms = ps.get("armsInterventionsModule", {})
    elig = ps.get("eligibilityModule", {})
    contacts = ps.get("contactsLocationsModule", {})
    sponsor = ps.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {})

    nct_id = ident.get("nctId")
    if not nct_id:
        raise ValueError("Study record has no NCT identifier")

    eligibility_text = elig.get("eligibilityCriteria")
    enrollment = design.get("enrollmentInfo", {})
    hv = elig.get("healthyVolunteers")

    locations = []
    for loc in contacts.get("locations", []) or []:
        gp = loc.get("geoPoint") or {}
        locations.append(TrialSite(
            facility=loc.get("facility"), city=loc.get("city"), state=loc.get("state"), zip=loc.get("zip"),
            country=loc.get("country"), status=loc.get("status"),
            lat=gp.get("lat"), lon=gp.get("lon"), contacts=_contacts(loc.get("contacts")),
        ))

    return NormalizedTrial(
        nct_id=nct_id,
        brief_title=ident.get("briefTitle") or nct_id,
        official_title=ident.get("officialTitle"),
        overall_status=status.get("overallStatus"),
        study_type=design.get("studyType"),
        phases=design.get("phases") or [],
        conditions=cond.get("conditions") or [],
        keywords=cond.get("keywords") or [],
        brief_summary=clean_text(desc["briefSummary"]) if desc.get("briefSummary") else None,
        detailed_description=clean_text(desc["detailedDescription"]) if desc.get("detailedDescription") else None,
        interventions=[
            Intervention(type=i.get("type"), name=i.get("name") or "Unnamed intervention",
                         description=i.get("description"), other_names=i.get("otherNames") or [])
            for i in arms.get("interventions", []) or []
        ],
        sponsor=sponsor.get("name"),
        eligibility_text=clean_text(eligibility_text) if eligibility_text else None,
        criteria=split_criteria(eligibility_text),
        sex=elig.get("sex"),
        minimum_age=elig.get("minimumAge"),
        maximum_age=elig.get("maximumAge"),
        min_age_years=parse_age_years(elig.get("minimumAge")),
        max_age_years=parse_age_years(elig.get("maximumAge")),
        healthy_volunteers=hv if isinstance(hv, bool) else None,
        enrollment_count=enrollment.get("count"),
        enrollment_type=enrollment.get("type"),
        central_contacts=_contacts(contacts.get("centralContacts")),
        locations=locations,
        last_update_post_date=(status.get("lastUpdatePostDateStruct") or {}).get("date"),
        status_verified_date=status.get("statusVerifiedDate"),
    )
