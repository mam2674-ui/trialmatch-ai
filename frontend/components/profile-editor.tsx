"use client";

/*
  Structured profile editor. Every value shows its provenance; any edit makes it "patient_provided".
  Clearing a field makes it unknown (never treated as evidence of eligibility).
*/

import { Plus, Trash2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import type { Biomarker, BiomarkerStatus, Fact, PatientProfile, Source, Treatment } from "@/lib/types";
import { cn } from "@/lib/utils";

const SOURCE_LABEL: Record<Source, string> = {
  patient_provided: "You provided",
  model_extracted: "Extracted by Claude",
  rule_extracted: "Extracted by rules",
  unknown: "Unknown",
};

export function SourceTag({ source, evidence }: { source: Source; evidence?: string | null }) {
  const cls = {
    patient_provided: "text-teal",
    model_extracted: "text-link",
    rule_extracted: "text-violet",
    unknown: "text-ink-soft",
  }[source];
  return (
    <span className={cn("text-xs", cls)}>
      {SOURCE_LABEL[source]}
      {evidence && source !== "patient_provided" && (
        <span className="text-ink-soft"> from &ldquo;{evidence.length > 90 ? evidence.slice(0, 90) + "…" : evidence}&rdquo;</span>
      )}
    </span>
  );
}

type Setter = (p: PatientProfile) => void;

function clone(p: PatientProfile): PatientProfile {
  return structuredClone(p);
}

function userFact<T>(value: T | null): Fact<T> {
  return value === null || value === "" ? { value: null, source: "unknown" } : { value, source: "patient_provided" };
}

function Field({ label, id, fact, children, hint }: {
  label: string; id: string; fact?: { source: Source; evidence?: string | null }; children: React.ReactNode; hint?: string;
}) {
  return (
    <div className="grid gap-1">
      <label htmlFor={id} className="text-sm font-medium text-ink">{label}</label>
      {children}
      <div className="min-h-4">
        {fact ? <SourceTag source={fact.source} evidence={fact.evidence} /> : hint && <span className="text-xs text-ink-soft">{hint}</span>}
      </div>
    </div>
  );
}

const selectCls = "h-9 w-full rounded-md border border-input bg-white px-2 text-sm text-ink focus-visible:outline-2";

function TextFact({ id, label, fact, onChange, placeholder }: {
  id: string; label: string; fact: Fact<string>; onChange: (f: Fact<string>) => void; placeholder?: string;
}) {
  return (
    <Field label={label} id={id} fact={fact}>
      <Input id={id} value={fact.value ?? ""} placeholder={placeholder ?? "Unknown"} className="bg-white"
        onChange={(e) => onChange(userFact(e.target.value || null))} />
    </Field>
  );
}

function NumberFact({ id, label, fact, onChange, min, max, suffix }: {
  id: string; label: string; fact: Fact<number>; onChange: (f: Fact<number>) => void; min: number; max: number; suffix?: string;
}) {
  return (
    <Field label={label} id={id} fact={fact}>
      <div className="flex items-center gap-2">
        <Input id={id} type="number" inputMode="numeric" min={min} max={max} value={fact.value ?? ""} placeholder="Unknown"
          className="bg-white"
          onChange={(e) => {
            const n = e.target.value === "" ? null : Number(e.target.value);
            onChange(userFact(n !== null && Number.isFinite(n) ? Math.min(max, Math.max(min, Math.round(n))) : null));
          }} />
        {suffix && <span className="text-sm text-ink-soft">{suffix}</span>}
      </div>
    </Field>
  );
}

function TriState({ id, label, fact, onChange, yes = "Yes", no = "No" }: {
  id: string; label: string; fact: Fact<boolean>; onChange: (f: Fact<boolean>) => void; yes?: string; no?: string;
}) {
  return (
    <Field label={label} id={id} fact={fact}>
      <select id={id} className={selectCls} value={fact.value === null ? "" : fact.value ? "y" : "n"}
        onChange={(e) => onChange(userFact(e.target.value === "" ? null : e.target.value === "y"))}>
        <option value="">Unknown</option>
        <option value="y">{yes}</option>
        <option value="n">{no}</option>
      </select>
    </Field>
  );
}

function Section({ title, children, note }: { title: string; children: React.ReactNode; note?: string }) {
  return (
    <fieldset className="border-t border-rule pt-5">
      <legend className="float-left mb-4 w-full font-serif text-lg font-semibold text-ink">{title}</legend>
      {note && <p className="clear-left mb-4 text-sm text-ink-soft">{note}</p>}
      <div className="clear-left grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{children}</div>
    </fieldset>
  );
}

const STATUSES: BiomarkerStatus[] = ["positive", "negative", "mutated", "wild_type", "amplified", "not_detected", "other"];

export function ProfileEditor({ profile, onChange }: { profile: PatientProfile; onChange: Setter }) {
  const p = profile;
  const up = (fn: (d: PatientProfile) => void) => {
    const d = clone(p);
    fn(d);
    onChange(d);
  };
  const loc = p.demographics.location;

  return (
    <div className="grid gap-8">
      <Section title="About the patient">
        <NumberFact id="age" label="Age" suffix="years" min={0} max={120} fact={p.demographics.age_years}
          onChange={(f) => up((d) => { d.demographics.age_years = f; })} />
        <Field label="Sex (as relevant to study eligibility)" id="sex" fact={p.demographics.sex}>
          <select id="sex" className={selectCls} value={p.demographics.sex.value ?? ""}
            onChange={(e) => up((d) => { d.demographics.sex = userFact((e.target.value || null) as "female" | "male" | null); })}>
            <option value="">Unknown</option>
            <option value="female">Female</option>
            <option value="male">Male</option>
          </select>
        </Field>
        <TriState id="preg" label="Currently pregnant or breastfeeding" fact={p.history.pregnant_or_breastfeeding}
          onChange={(f) => up((d) => { d.history.pregnant_or_breastfeeding = f; })} />
      </Section>

      <Section title="Location and travel" note="Only the city or postal code is used to estimate distances to study sites.">
        <Field label="City" id="city" fact={loc.source !== "unknown" ? loc : undefined}>
          <Input id="city" value={loc.city ?? ""} placeholder="Unknown" className="bg-white"
            onChange={(e) => up((d) => { Object.assign(d.demographics.location, { city: e.target.value || null, source: "patient_provided", lat: null, lon: null }); })} />
        </Field>
        <Field label="State or region" id="state">
          <Input id="state" value={loc.state ?? ""} placeholder="Optional" className="bg-white"
            onChange={(e) => up((d) => { Object.assign(d.demographics.location, { state: e.target.value || null, source: "patient_provided", lat: null, lon: null }); })} />
        </Field>
        <Field label="Postal code" id="zip">
          <Input id="zip" value={loc.postal_code ?? ""} placeholder="Optional" className="bg-white"
            onChange={(e) => up((d) => { Object.assign(d.demographics.location, { postal_code: e.target.value || null, source: "patient_provided", lat: null, lon: null }); })} />
        </Field>
        <Field label="Country" id="country">
          <Input id="country" value={loc.country ?? ""} placeholder="Optional" className="bg-white"
            onChange={(e) => up((d) => { Object.assign(d.demographics.location, { country: e.target.value || null, source: "patient_provided", lat: null, lon: null }); })} />
        </Field>
        <NumberFact id="radius" label="Maximum travel distance" suffix="miles" min={1} max={5000}
          fact={p.demographics.travel_radius_miles} onChange={(f) => up((d) => { d.demographics.travel_radius_miles = f; })} />
        <Field label="Willing to travel farther if needed" id="travel">
          <select id="travel" className={selectCls} value={p.preferences.willing_to_travel === null ? "" : p.preferences.willing_to_travel ? "y" : "n"}
            onChange={(e) => up((d) => { d.preferences.willing_to_travel = e.target.value === "" ? null : e.target.value === "y"; })}>
            <option value="">Not specified</option><option value="y">Yes</option><option value="n">No</option>
          </select>
        </Field>
      </Section>

      <Section title="Diagnosis">
        <TextFact id="cond" label="Primary condition (required)" fact={p.diagnosis.primary_condition} placeholder="e.g. breast cancer"
          onChange={(f) => up((d) => { d.diagnosis.primary_condition = f; })} />
        <TextFact id="subtype" label="Subtype" fact={p.diagnosis.subtype} onChange={(f) => up((d) => { d.diagnosis.subtype = f; })} />
        <TextFact id="stage" label="Stage" fact={p.diagnosis.stage} placeholder="e.g. Stage IIB"
          onChange={(f) => up((d) => { d.diagnosis.stage = f; })} />
        <TextFact id="histology" label="Histology" fact={p.diagnosis.histology} onChange={(f) => up((d) => { d.diagnosis.histology = f; })} />
        <TriState id="met" label="Spread to distant sites (metastatic)" fact={p.diagnosis.metastatic}
          onChange={(f) => up((d) => { d.diagnosis.metastatic = f; })} />
        <NumberFact id="ecog" label="ECOG performance status" min={0} max={5} fact={p.history.ecog_performance_status}
          onChange={(f) => up((d) => { d.history.ecog_performance_status = f; })} />
      </Section>

      <ListSection title="Biomarkers and genetic test results" empty="No biomarker results entered."
        onAdd={() => up((d) => { d.diagnosis.biomarkers.push({ name: "", status: "positive", source: "patient_provided" }); })}>
        {p.diagnosis.biomarkers.map((b, i) => (
          <BiomarkerRow key={i} b={b} i={i}
            onChange={(nb) => up((d) => { d.diagnosis.biomarkers[i] = nb; })}
            onRemove={() => up((d) => { d.diagnosis.biomarkers.splice(i, 1); })} />
        ))}
      </ListSection>

      <ListSection title="Treatments received" empty="No prior treatments entered."
        onAdd={() => up((d) => { d.history.prior_treatments.push({ name: "", status: "completed", progression: "unknown", source: "patient_provided" }); })}>
        {p.history.prior_treatments.map((t, i) => (
          <TreatmentRow key={i} t={t} i={i}
            onChange={(nt) => up((d) => { d.history.prior_treatments[i] = nt; })}
            onRemove={() => up((d) => { d.history.prior_treatments.splice(i, 1); })} />
        ))}
      </ListSection>

      <StringList title="Current medications" items={p.history.current_medications}
        onChange={(items) => up((d) => { d.history.current_medications = items; })} />
      <StringList title="Other medical conditions" items={p.history.comorbidities}
        onChange={(items) => up((d) => { d.history.comorbidities = items; })} />

      {p.history.labs.length > 0 && (
        <fieldset className="border-t border-rule pt-5">
          <legend className="mb-3 font-serif text-lg font-semibold text-ink">Laboratory values</legend>
          <ul className="grid gap-1 text-sm">
            {p.history.labs.map((l, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-2">
                <span className="text-ink">{l.name}: {l.value} {l.unit}</span>
                <SourceTag source={l.source} evidence={l.evidence} />
                <button className="text-xs text-brick underline" onClick={() => up((d) => { d.history.labs.splice(i, 1); })}>Remove</button>
              </li>
            ))}
          </ul>
        </fieldset>
      )}

      <fieldset className="border-t border-rule pt-5">
        <legend className="mb-3 font-serif text-lg font-semibold text-ink">Search preferences</legend>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" className="size-4 accent-[#13294B]" checked={p.preferences.recruiting_only}
            onChange={(e) => up((d) => { d.preferences.recruiting_only = e.target.checked; })} />
          Only show studies that are recruiting or about to start recruiting
        </label>
        <div className="mt-4 max-w-md">
          <label htmlFor="interests" className="text-sm font-medium text-ink">Treatment types of interest (optional)</label>
          <Input id="interests" className="mt-1 bg-white" placeholder="e.g. immunotherapy, antibody-drug conjugate"
            value={p.preferences.treatment_interests.join(", ")}
            onChange={(e) => up((d) => { d.preferences.treatment_interests = e.target.value.split(",").map((s) => s.trim()).filter(Boolean); })} />
        </div>
      </fieldset>
    </div>
  );
}

function ListSection({ title, children, onAdd, empty }: { title: string; children: React.ReactNode[]; onAdd: () => void; empty: string }) {
  return (
    <fieldset className="border-t border-rule pt-5">
      <legend className="mb-3 font-serif text-lg font-semibold text-ink">{title}</legend>
      <div className="grid gap-3">{children.length ? children : <p className="text-sm text-ink-soft">{empty}</p>}</div>
      <Button variant="outline" size="sm" className="mt-3" onClick={onAdd}><Plus aria-hidden="true" /> Add</Button>
    </fieldset>
  );
}

function BiomarkerRow({ b, i, onChange, onRemove }: { b: Biomarker; i: number; onChange: (b: Biomarker) => void; onRemove: () => void }) {
  const set = (patch: Partial<Biomarker>) => onChange({ ...b, ...patch, source: "patient_provided" });
  return (
    <div className="grid gap-2 rounded border border-rule bg-white p-3 sm:grid-cols-[1fr_1fr_1.4fr_auto] sm:items-end">
      <Field label="Marker" id={`bm-name-${i}`}>
        <Input id={`bm-name-${i}`} value={b.name} placeholder="e.g. HER2" onChange={(e) => set({ name: e.target.value })} />
      </Field>
      <Field label="Result" id={`bm-status-${i}`}>
        <select id={`bm-status-${i}`} className={selectCls} value={b.status} onChange={(e) => set({ status: e.target.value as BiomarkerStatus })}>
          {STATUSES.map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
        </select>
      </Field>
      <Field label="Detail" id={`bm-detail-${i}`} fact={{ source: b.source, evidence: b.evidence }}>
        <Input id={`bm-detail-${i}`} value={b.detail ?? ""} placeholder="e.g. exon 19 deletion, IHC 3+" onChange={(e) => set({ detail: e.target.value || null })} />
      </Field>
      <Button variant="ghost" size="icon" aria-label={`Remove ${b.name || "biomarker"}`} onClick={onRemove} className="mb-5"><Trash2 /></Button>
    </div>
  );
}

function TreatmentRow({ t, i, onChange, onRemove }: { t: Treatment; i: number; onChange: (t: Treatment) => void; onRemove: () => void }) {
  const set = (patch: Partial<Treatment>) => onChange({ ...t, ...patch, source: "patient_provided" });
  return (
    <div className="grid gap-2 rounded border border-rule bg-white p-3 sm:grid-cols-[1.4fr_1fr_1.2fr_auto] sm:items-end">
      <Field label="Treatment" id={`tx-name-${i}`} fact={{ source: t.source, evidence: t.evidence }}>
        <Input id={`tx-name-${i}`} value={t.name} placeholder="e.g. osimertinib" onChange={(e) => set({ name: e.target.value })} />
      </Field>
      <Field label="Status" id={`tx-status-${i}`}>
        <select id={`tx-status-${i}`} className={selectCls} value={t.status} onChange={(e) => set({ status: e.target.value as Treatment["status"] })}>
          <option value="completed">Completed</option><option value="ongoing">Ongoing</option>
          <option value="planned">Planned</option><option value="unknown">Unknown</option>
        </select>
      </Field>
      <Field label="Disease progressed on or after it?" id={`tx-prog-${i}`}>
        <select id={`tx-prog-${i}`} className={selectCls} value={t.progression} onChange={(e) => set({ progression: e.target.value as Treatment["progression"] })}>
          <option value="unknown">Not sure / not stated</option><option value="yes">Yes</option><option value="no">No</option>
        </select>
      </Field>
      <Button variant="ghost" size="icon" aria-label={`Remove ${t.name || "treatment"}`} onClick={onRemove} className="mb-5"><Trash2 /></Button>
    </div>
  );
}

function StringList({ title, items, onChange }: { title: string; items: Fact<string>[]; onChange: (f: Fact<string>[]) => void }) {
  return (
    <fieldset className="border-t border-rule pt-5">
      <legend className="mb-3 font-serif text-lg font-semibold text-ink">{title}</legend>
      <div className="grid gap-2">
        {items.map((f, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <Input aria-label={`${title} ${i + 1}`} className="max-w-sm bg-white" value={f.value ?? ""}
              onChange={(e) => { const n = [...items]; n[i] = userFact(e.target.value || null); onChange(n); }} />
            <SourceTag source={f.source} evidence={f.evidence} />
            <Button variant="ghost" size="icon-sm" aria-label="Remove" onClick={() => onChange(items.filter((_, j) => j !== i))}><Trash2 /></Button>
          </div>
        ))}
        {!items.length && <p className="text-sm text-ink-soft">None entered.</p>}
      </div>
      <Button variant="outline" size="sm" className="mt-3" onClick={() => onChange([...items, { value: null, source: "unknown" }])}>
        <Plus aria-hidden="true" /> Add
      </Button>
    </fieldset>
  );
}
