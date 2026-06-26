/**
 * Labor tab (design doc §5.5): the deal's staffing plan. Each position is a line item (like the
 * budget grid) with hours/week, full/part-time, seasonal/year-round, hourly rate, work-camper,
 * benefits-eligibility, and start/end dates. The plan rolls up to year-one labor, which feeds the
 * budget's Wages cluster (and, for work campers, extended-stay revenue + a campsite credit) → NOI
 * → pro forma → promote. Prior-year labor is pulled from the mapped P&L. Flat-lined for now
 * (hours × rate × active weeks); week-by-week tuning is a later refinement.
 */
import { useState } from "react";
import {
  useAddLaborPosition,
  useLabor,
  usePatchLaborPosition,
  useRemoveLaborPosition,
  useSeedLabor,
} from "../../api/hooks";
import type { Schemas } from "../../api/client";
import { fmtUsd } from "../../lib/format";

type LaborPositionRow = Schemas["LaborPositionRow"];
type LaborPositionPatch = Schemas["LaborPositionPatch"];
type Patch = ReturnType<typeof usePatchLaborPosition>;
type Remove = ReturnType<typeof useRemoveLaborPosition>;

const ROLES: { value: string; label: string }[] = [
  { value: "general_manager", label: "General Manager" },
  { value: "front_desk", label: "Front Desk" },
  { value: "housekeeper", label: "Housekeeper" },
  { value: "maintenance", label: "Maintenance" },
  { value: "events_coordinator", label: "Events Coordinator" },
];

export function LaborTab({ acquisitionId }: { acquisitionId: string }) {
  const { data, isLoading } = useLabor(acquisitionId);
  const seed = useSeedLabor(acquisitionId);
  const add = useAddLaborPosition(acquisitionId);
  const patch = usePatchLaborPosition(acquisitionId);
  const remove = useRemoveLaborPosition(acquisitionId);

  if (isLoading) return <p className="text-sm opacity-70">Loading…</p>;
  const positions = data?.positions ?? [];
  const totals = data?.totals;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium">Staffing plan</span>
        {totals && (
          <span className="text-xs opacity-70">
            Year-1 labor <span className="font-figure">{fmtUsd(totals.total_cash_labor)}</span> ·
            prior <span className="font-figure">{fmtUsd(totals.prior_labor)}</span>
          </span>
        )}
        {positions.length === 0 && (
          <button
            type="button"
            disabled={seed.isPending}
            onClick={() => seed.mutate()}
            className="ml-auto rounded bg-brand px-3 py-1.5 text-sm text-surface disabled:opacity-50"
          >
            {seed.isPending ? "Seeding…" : "Seed default staffing"}
          </button>
        )}
      </div>

      {positions.length === 0 ? (
        <p className="rounded border border-brand/20 p-3 text-sm opacity-80">
          No positions yet. “Seed default staffing” lays out the standard scenario (1 GM + 1 front
          desk + 1 maintenance, plus a part-time front desk + maintenance), or add positions below.
          Labor flows into the Budget’s wages lines, then the pro forma.
        </p>
      ) : (
        <div className="space-y-2">
          {positions.map((p) => (
            <PositionCard key={p.position_id} p={p} patch={patch} remove={remove} />
          ))}
        </div>
      )}

      <AddPosition add={add} />

      {totals && (
        <div className="rounded-lg border border-brand/20 p-3 text-sm">
          <Line label="Base wages → Payroll Expenses (600140)" value={totals.wages} />
          <Line label="Benefits → Employee Health Benefits (600130)" value={totals.benefits} />
          <Line label="Payroll tax → Payroll Tax Expense (600155)" value={totals.payroll_tax} />
          <div className="mt-1 flex justify-between border-t border-brand/20 pt-1 font-semibold">
            <span>Total year-one labor → Budget</span>
            <span className="font-figure">{fmtUsd(totals.total_cash_labor)}</span>
          </div>
          {(Number(totals.extended_stay_revenue) !== 0 ||
            Number(totals.work_camper_credit) !== 0) && (
            <div className="mt-2 border-t border-brand/10 pt-1 text-xs opacity-80">
              <Line
                label="Work-camper extended-stay revenue (400110)"
                value={totals.extended_stay_revenue}
              />
              <Line
                label="Work-camper campsite credit (421300, contra)"
                value={`(${fmtUsd(totals.work_camper_credit)})`}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Line({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="flex justify-between">
      <span className="opacity-70">{label}</span>
      <span className="font-figure">{typeof value === "string" ? value : fmtUsd(value)}</span>
    </div>
  );
}

function PositionCard({ p, patch, remove }: { p: LaborPositionRow; patch: Patch; remove: Remove }) {
  const set = (field: keyof LaborPositionPatch, value: unknown) =>
    patch.mutate({ position_id: p.position_id, [field]: value } as LaborPositionPatch);
  const onRemove = () => {
    if (window.confirm(`Remove “${p.name}”?`)) remove.mutate(p.position_id);
  };

  return (
    <div className="rounded-md border border-brand/15 p-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">{p.name}</span>
        <div className="flex items-center gap-3">
          <span className="font-figure text-sm">
            {p.is_work_camper ? "site comp" : fmtUsd(p.wages)}
          </span>
          <button
            type="button"
            aria-label={`Remove ${p.name}`}
            onClick={onRemove}
            className="rounded px-1 text-ink/40 hover:text-danger"
          >
            ×
          </button>
        </div>
      </div>

      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-4">
        <Select
          label="Type"
          value={p.employment_type}
          onChange={(v) => set("employment_type", v)}
          options={[
            ["full_time", "Full-time"],
            ["part_time", "Part-time"],
          ]}
        />
        <Select
          label="Season"
          value={p.season}
          onChange={(v) => set("season", v)}
          options={[
            ["year_round", "Year-round"],
            ["seasonal", "Seasonal"],
          ]}
        />
        <Num label="Hours/wk" value={p.hours_per_week} onCommit={(n) => set("hours_per_week", n)} />
        <Num label="Headcount" value={p.headcount} onCommit={(n) => set("headcount", n)} />
        {!p.is_work_camper && (
          <Num label="Rate $/hr" value={p.hourly_rate} onCommit={(n) => set("hourly_rate", n)} />
        )}
        <DateField label="Start" value={p.start_date} onChange={(v) => set("start_date", v)} />
        <DateField label="End" value={p.end_date} onChange={(v) => set("end_date", v)} />
        {p.is_work_camper && (
          <>
            <Num
              label="Site $/wk"
              value={p.site_weekly_rate}
              onCommit={(n) => set("site_weekly_rate", n)}
            />
            <Num
              label="Campsite credit $/wk"
              value={p.campsite_credit_weekly}
              onCommit={(n) => set("campsite_credit_weekly", n)}
            />
          </>
        )}
        <Check
          label="Work camper"
          checked={p.is_work_camper}
          onChange={(c) => set("is_work_camper", c)}
        />
        <Check
          label="Benefits"
          checked={p.benefits_eligible}
          onChange={(c) => set("benefits_eligible", c)}
        />
      </div>
    </div>
  );
}

function AddPosition({ add }: { add: ReturnType<typeof useAddLaborPosition> }) {
  const [role, setRole] = useState("");
  return (
    <div className="flex items-center gap-2">
      <select
        aria-label="Add a position"
        value={role}
        onChange={(e) => {
          const r = e.target.value;
          setRole("");
          if (r) add.mutate({ role: r });
        }}
        className="rounded border border-brand/30 bg-surface px-2 py-1.5 text-sm"
      >
        <option value="">+ Add position…</option>
        {ROLES.map((r) => (
          <option key={r.value} value={r.value}>
            {r.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
}) {
  return (
    <label className="flex flex-col gap-0.5 text-xs">
      <span className="opacity-60">{label}</span>
      <select
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded border border-brand/20 bg-surface px-2 py-1 text-sm"
      >
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </label>
  );
}

function Num({
  label,
  value,
  onCommit,
}: {
  label: string;
  value: number | string | null | undefined;
  onCommit: (n: number) => void;
}) {
  const current = value == null ? null : Number(value);
  return (
    <label className="flex flex-col gap-0.5 text-xs">
      <span className="opacity-60">{label}</span>
      <input
        type="number"
        aria-label={label}
        key={current ?? ""}
        defaultValue={current ?? ""}
        onBlur={(e) => {
          const raw = e.target.value;
          if (raw === "") return;
          const next = Number(raw);
          if (next !== current) onCommit(next);
        }}
        className="rounded border border-brand/20 bg-surface px-2 py-1 font-figure text-sm"
      />
    </label>
  );
}

function DateField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string | null | undefined;
  onChange: (v: string | null) => void;
}) {
  return (
    <label className="flex flex-col gap-0.5 text-xs">
      <span className="opacity-60">{label}</span>
      <input
        type="date"
        aria-label={label}
        defaultValue={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
        className="rounded border border-brand/20 bg-surface px-2 py-1 font-figure text-sm"
      />
    </label>
  );
}

function Check({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (c: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 self-end text-xs">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="opacity-70">{label}</span>
    </label>
  );
}
