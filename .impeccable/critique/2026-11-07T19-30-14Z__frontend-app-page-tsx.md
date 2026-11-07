---
target: the homepage
total_score: 23
max_score: 36
na_heuristics: 7
p0_count: 1
p1_count: 2
target_identity: "file:/Users/marcelomoraruiz/Coding/trialmatch-ai/frontend/app/page.tsx"
target_fingerprint: "sha256:5a9b86fb133b93a530cb8623bd5b2439e578bdadde0b09491051d6a6b14332fb"
target_path: /Users/marcelomoraruiz/Coding/trialmatch-ai/frontend/app/page.tsx
timestamp: 2026-11-07T19-30-14Z
slug: frontend-app-page-tsx
---
Method: dual-agent (A: design review, B: detector + browser overlay)

## Design Health Score
| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 2 | Grey CTA with no reason; demos load/fail silently |
| 2 | Match system / real world | 2 | "semantic and keyword ranking", "validator", "[I1]", QA-note demo copy |
| 3 | User control and freedom | 3 | Doesn't say you review the profile before searching |
| 4 | Consistency and standards | 3 | Title Case CTA; ledger specimen status without icons |
| 5 | Error prevention | 3 | 10-character minimum invisible |
| 6 | Recognition over recall | 3 | Example placeholder vanishes on typing |
| 7 | Flexibility and efficiency | n/a | Single-entry landing page |
| 8 | Aesthetic and minimalist | 2 | 3 value props + 5 demos + 4-step strip around one textbox |
| 9 | Error recovery | 2 | Silent demo failure; no help for "I don't know my stage" |
| 10 | Help and documentation | 3 | Methodology page and specimen help |
| Total | | 23/36 | Acceptable (64%) |

## Design specificity verdict
Reads as generated: stock split hero, three left-bordered value props, "How a match is built" step strip, feature explainer. Formula H1 "Clinical research, matched to you." (also contradicts "never a verdict"), filler subhead, mechanical Source Serif 4 + Public Sans pairing, demo descriptions that are QA notes. Specific assets: semantic status palette, "never a verdict" stance, criteria-ledger specimen (buried at the bottom).
Detector: 0 CLI findings; browser overlay 7 width-dependent stragglers (3 desktop, 4 mobile), cosmetic, fix with text-wrap: pretty.

## Priority issues
- [P0] Primary textarea below the fold on mobile (starts ~850px at 375x812; two-row nav 129px). Fix: input right after short headline; value props below; one-row nav. /impeccable adapt
- [P1] Developer/evaluator copy shown to patients (demo challenge lines; steps 3-4). Fix: patient-voice demo lines; outcome-language steps; pipeline detail to /about. /impeccable clarify
- [P1] Template composition is the AI-generated look. Fix: ledger as hero visual, specific headline, value props folded into ledger annotations. /impeccable bolder then typeset
- [P2] Too many choices, too little reassurance at input (1 CTA + 5 demos + 5 nav links incl. empty Results/Compare/Saved; amber warning icon; unexplained disabled button). /impeccable onboard
- [P2] Small type/targets: 12px secondary text, textarea 14px on desktop via shadcn md:text-sm override, 32px nav targets. /impeccable harden

## Persona red flags
Jordan: empty Results/Compare pages; placeholder looks pre-filled; grey button unexplained.
Casey: a full screen of scrolling before any input; small demo targets.
Maria (60, caregiver): "matched to you" not about her; thinks she knows too little; amber icon reads as alarm; QA-note demo copy alienating; nothing promises questions to bring to the oncologist.

## Minor observations
Grey "AI" suffix; ledger caption assumes Methodology was read; Title Case CTA; duplicated demo tooltips; 7 stragglers.

## Questions
Why is the ledger last? Caregiver vs portfolio reviewer audience? Guided start vs blank box?
