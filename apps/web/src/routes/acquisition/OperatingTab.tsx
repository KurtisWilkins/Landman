/**
 * Operating Inputs tab (defaults engine, Part 1): the per-deal drivers the budget defaults depend
 * on — the billable unit mix (RV pads + cabins + glamping; tents excluded), the electric expense
 * (utility bill-back driver), and employee headcount (payroll-budget driver). Seeded from the OM
 * where present; a missing driver shows a "needs input" flag. Editing a driver recomputes the
 * dependent budget defaults automatically (manual edits on the budget are kept).
 */
import { useState } from "react";
import {
  useAddUnitGroup,
  useOperating,
  usePatchOperating,
  usePatchUnitGroup,
  useRemoveUnitGroup,
  useSeedOperating,
  type UnitGroupPatch,
  type UnitGroupRow,
} from "../../api/hooks";
import { fmtUsd } from "../../lib/format";

const CAT_LABELS: Record<string, string> = {
  rv_pad: "RV pads",
  cabin: "Cabins",
  glamping: "Glamping",
  tent: "Tents",
};
const catLabel = (c: string) => CAT_LABELS[c] ?? c;

export function OperatingTab({ acquisitionId }: { acquisitionId: string }) {
  const { data, isLoading } = useOperating(acquisitionId);
  const seed = useSeedOperating(acquisitionId);
  const patch = usePatchOperating(acquisitionId);
  const addGroup = useAddUnitGroup(acquisitionId);
  const patchGroup = usePatchUnitGroup(acquisitionId);
  const removeGroup = useRemoveUnitGroup(acquisitionId);

  if (isLoading) return <p className="text-sm opacity-70">Loading…</p>;
  const groups = data?.unit_groups ?? [];
  const empty = groups.length === 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium">Operating inputs</span>
        <span className="text-xs opacity-70">
          drives the budget defaults (R&amp;M · bill-back · payroll)
        </span>
        {empty && (
          <button
            type="button"
            disabled={seed.isPending}
            onClick={() => seed.mutate()}
            className="ml-auto rounded bg-brand px-3 py-1.5 text-sm text-surface disabled:opacity-50"
          >
            {seed.isPending ? "Seeding…" : "Seed from OM"}
          </button>
        )}
      </div>

      <div className="rounded-lg border border-brand/20 p-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-medium">Billable units</span>
          {data?.units_need_input && (
            <span className="rounded bg-accent/20 px-2 py-0.5 text-xs text-ink">⚠ needs input</span>
          )}
        </div>

        {empty ? (
          <p className="text-sm opacity-80">
            No unit mix yet. “Seed from OM” pulls the categories (RV pads, cabins, glamping; tents
            excluded), or add categories below.
          </p>
        ) : (
          <div className="space-y-1.5">
            {groups.map((g) => (
              <UnitGroupRowView
                key={g.unit_group_id}
                g={g}
                patch={patchGroup}
                remove={removeGroup}
              />
            ))}
          </div>
        )}

        <div className="mt-2 flex items-center justify-between border-t border-brand/15 pt-2">
          <AddUnitGroup add={addGroup} />
          <span className="text-sm">
            Total billable units:{" "}
            <span className="font-figure font-semibold">{data?.billable_unit_total ?? 0}</span>
          </span>
        </div>
        <p className="mt-1 text-[11px] opacity-60">RV pads + cabins + glamping; tents excluded.</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <DriverField
          label="Electric (annual)"
          hint={`source: ${data?.electric_source ?? "needs input"}`}
          needsInput={data?.electric_needs_input ?? true}
          value={data?.electric_annual ?? null}
          money
          onCommit={(n) => patch.mutate({ electric_annual: n })}
        />
        <div className="rounded-lg border border-brand/20 p-3">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-sm font-medium">Employee headcount</span>
            {data?.headcount_needs_input ? (
              <span className="rounded bg-accent/20 px-2 py-0.5 text-xs text-ink">
                ⚠ needs input
              </span>
            ) : null}
          </div>
          <div className="font-figure text-lg">{data?.employee_headcount ?? "—"}</div>
          <p className="mt-1 text-[11px] opacity-55">
            From the Labor roster (single source of truth) — add roles &amp; counts on the Labor
            tab.
          </p>
        </div>
      </div>

      <p className="text-xs opacity-70">
        Drives → Repairs &amp; maintenance (per unit) · Utility bill-back (% of electric) · Payroll
        budget (per employee). Editing a driver recomputes the dependent budget defaults
        automatically; manual edits on the budget are kept.
      </p>
    </div>
  );
}

function UnitGroupRowView({
  g,
  patch,
  remove,
}: {
  g: UnitGroupRow;
  patch: ReturnType<typeof usePatchUnitGroup>;
  remove: ReturnType<typeof useRemoveUnitGroup>;
}) {
  const set = (field: keyof UnitGroupPatch, value: unknown) =>
    patch.mutate({ unit_group_id: g.unit_group_id, [field]: value } as UnitGroupPatch);
  const onRemove = () => {
    const name = g.label ?? catLabel(g.category);
    if (window.confirm(`Remove “${name}”?`)) remove.mutate(g.unit_group_id);
  };
  const needs = g.billable && g.count == null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="min-w-[8rem] text-sm">
        {catLabel(g.category)}
        {g.label ? <span className="opacity-60"> · {g.label}</span> : null}
        {!g.billable ? <span className="opacity-50"> (excluded)</span> : null}
      </span>
      <input
        type="number"
        aria-label={`${catLabel(g.category)} count`}
        key={g.count ?? ""}
        defaultValue={g.count ?? ""}
        placeholder={needs ? "needs input" : ""}
        onBlur={(e) => {
          if (e.target.value === "") return;
          const n = Number(e.target.value);
          if (n !== g.count) set("count", n);
        }}
        className="w-24 rounded border border-brand/20 bg-surface px-2 py-1 font-figure text-sm"
      />
      <label className="flex items-center gap-1 text-xs opacity-70">
        <input
          type="checkbox"
          checked={g.billable}
          onChange={(e) => set("billable", e.target.checked)}
        />
        billable
      </label>
      <span className="text-[11px] opacity-50">{g.source}</span>
      <button
        type="button"
        aria-label={`Remove ${catLabel(g.category)}`}
        onClick={onRemove}
        className="ml-auto rounded px-1 text-ink/40 hover:text-danger"
      >
        ×
      </button>
    </div>
  );
}

function AddUnitGroup({ add }: { add: ReturnType<typeof useAddUnitGroup> }) {
  const [val, setVal] = useState("");
  const onPick = (v: string) => {
    setVal("");
    if (!v) return;
    if (v === "__custom__") {
      const name = window.prompt("Custom unit sub-type (e.g. RV pads — premium)");
      if (!name?.trim()) return;
      const trimmed = name.trim();
      add.mutate({
        category: trimmed.toLowerCase().replace(/\s+/g, "_"),
        label: trimmed,
      });
      return;
    }
    add.mutate({ category: v });
  };
  return (
    <select
      aria-label="Add a unit category"
      value={val}
      onChange={(e) => onPick(e.target.value)}
      className="rounded border border-brand/30 bg-surface px-2 py-1.5 text-sm"
    >
      <option value="">+ Add category…</option>
      <option value="rv_pad">RV pads</option>
      <option value="cabin">Cabins</option>
      <option value="glamping">Glamping</option>
      <option value="tent">Tents (excluded)</option>
      <option value="__custom__">Custom sub-type…</option>
    </select>
  );
}

function DriverField({
  label,
  hint,
  needsInput,
  value,
  money,
  onCommit,
}: {
  label: string;
  hint: string;
  needsInput: boolean;
  value: number | string | null;
  money?: boolean;
  onCommit: (n: number) => void;
}) {
  const current = value == null ? null : Number(value);
  return (
    <div className="rounded-lg border border-brand/20 p-3">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-sm font-medium">{label}</span>
        {needsInput ? (
          <span className="rounded bg-accent/20 px-2 py-0.5 text-xs text-ink">⚠ needs input</span>
        ) : null}
      </div>
      <div className="flex items-center gap-2">
        {money ? <span className="opacity-60">$</span> : null}
        <input
          type="number"
          aria-label={label}
          key={current ?? ""}
          defaultValue={current ?? ""}
          placeholder={needsInput ? "needs input" : ""}
          onBlur={(e) => {
            if (e.target.value === "") return;
            const n = Number(e.target.value);
            if (n !== current) onCommit(n);
          }}
          className="w-40 rounded border border-brand/20 bg-surface px-2 py-1 font-figure text-sm"
        />
        {money && current != null ? (
          <span className="text-xs opacity-60">{fmtUsd(current)}</span>
        ) : null}
      </div>
      <p className="mt-1 text-[11px] opacity-55">{hint}</p>
    </div>
  );
}
