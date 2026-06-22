/**
 * Budget tab (design doc §5.5): underwriting laid out like a budget — each canonical GL's
 * prior-year actuals (read-only, computed from the mapped P&L) beside the editable year-one
 * projection, with $ and % variance and a provenance badge (actuals / default / to review /
 * edited). Collapsed to annual; expand a row for the month-by-month view (last June beside this
 * June). Year-one edits flip the cell to an override; the budget rolls up to the stabilized NOI.
 */
import { useState } from "react";
import { useBudget, usePatchBudgetCell, useSeedBudget } from "../../api/hooks";
import type { Schemas } from "../../api/client";
import { fmtPct, fmtUsd } from "../../lib/format";

type BudgetRow = Schemas["BudgetRow"];
type Patch = ReturnType<typeof usePatchBudgetCell>;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function badge(source: string, overridden: boolean): { label: string; cls: string } {
  if (overridden) return { label: "edited", cls: "bg-ink/10 text-ink/70" };
  if (source === "actuals") return { label: "actuals", cls: "bg-success/15 text-success" };
  if (source === "default") return { label: "default", cls: "bg-brand/10 text-brand" };
  if (source === "placeholder") return { label: "to review", cls: "bg-accent/15 text-accent-ink" };
  return { label: source, cls: "bg-ink/10 text-ink/70" };
}

export function BudgetTab({ acquisitionId }: { acquisitionId: string }) {
  const { data, isLoading } = useBudget(acquisitionId);
  const seed = useSeedBudget(acquisitionId);
  const patch = usePatchBudgetCell(acquisitionId);

  if (isLoading) return <p className="text-sm opacity-70">Loading…</p>;
  const rows = data?.rows ?? [];
  const totals = data?.totals;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium">Year-one budget</span>
        {data?.status && (
          <span className="rounded bg-ink/10 px-2 py-0.5 text-xs text-ink/70">{data.status}</span>
        )}
        {totals && (
          <span className="text-xs opacity-70">
            Year-1 NOI <span className="font-figure">{fmtUsd(totals.year1_noi)}</span> · prior{" "}
            <span className="font-figure">{fmtUsd(totals.prior_noi)}</span>
          </span>
        )}
        <button
          type="button"
          disabled={seed.isPending}
          onClick={() => seed.mutate()}
          className="ml-auto rounded border border-brand/30 px-3 py-1.5 text-sm disabled:opacity-50"
        >
          {seed.isPending ? "Seeding…" : rows.length === 0 ? "Seed from actuals" : "Re-seed gaps"}
        </button>
      </div>

      {rows.length === 0 ? (
        <p className="rounded border border-brand/20 p-3 text-sm opacity-80">
          No budget yet. Map the uploaded P&amp;L on the GL / Docs tab, then “Seed from actuals” to
          prefill year-one from the prior year — then edit and review the overs and unders here.
        </p>
      ) : (
        <>
          <Section title="Income" rows={rows.filter((r) => r.section === "Income")} patch={patch} />
          <Section
            title="Expense"
            rows={rows.filter((r) => r.section === "Expense")}
            patch={patch}
          />
          <Section
            title="Other"
            rows={rows.filter((r) => r.section !== "Income" && r.section !== "Expense")}
            patch={patch}
          />
          {totals && (
            <div className="grid grid-cols-[1fr_repeat(4,minmax(72px,1fr))] gap-2 border-t border-brand/20 px-2 pt-2 text-sm font-medium">
              <span>Stabilized NOI</span>
              <span className="text-right font-figure">{fmtUsd(totals.prior_noi)}</span>
              <span className="text-right font-figure">{fmtUsd(totals.year1_noi)}</span>
              <span className="text-right font-figure">
                {fmtUsd(Number(totals.year1_noi) - Number(totals.prior_noi))}
              </span>
              <span />
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Section({ title, rows, patch }: { title: string; rows: BudgetRow[]; patch: Patch }) {
  if (rows.length === 0) return null;
  return (
    <div>
      <div className="grid grid-cols-[1fr_repeat(4,minmax(72px,1fr))] gap-2 px-2 pb-1 text-xs uppercase tracking-wide opacity-60">
        <span>{title}</span>
        <span className="text-right">Prior yr</span>
        <span className="text-right">Year 1</span>
        <span className="text-right">$ var</span>
        <span className="text-right">% var</span>
      </div>
      <div className="space-y-1">
        {rows.map((r) => (
          <Row key={r.account_code} row={r} patch={patch} />
        ))}
      </div>
    </div>
  );
}

function Row({ row, patch }: { row: BudgetRow; patch: Patch }) {
  const [open, setOpen] = useState(false);
  const b = badge(row.source, row.is_overridden);
  return (
    <div className="rounded-md border border-brand/10">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="grid w-full grid-cols-[1fr_repeat(4,minmax(72px,1fr))] items-center gap-2 px-2 py-1.5 text-left text-sm hover:bg-surface"
      >
        <span className="flex items-center gap-2">
          <span className={`rounded px-1.5 py-0.5 text-[10px] ${b.cls}`}>{b.label}</span>
          <span>{row.name}</span>
        </span>
        <span className="text-right font-figure opacity-70">{fmtUsd(row.prior_annual)}</span>
        <span className="text-right font-figure">{fmtUsd(row.year1_annual)}</span>
        <span className="text-right font-figure opacity-70">{fmtUsd(row.var_abs)}</span>
        <span className="text-right font-figure opacity-70">
          {row.var_pct == null ? "—" : fmtPct(row.var_pct)}
        </span>
      </button>
      {open && (
        <div className="grid grid-cols-2 gap-2 border-t border-brand/10 p-2 sm:grid-cols-3">
          {MONTHS.map((label, i) => (
            <MonthCell
              key={i}
              label={label}
              prior={(row.prior_months ?? [])[i] ?? null}
              year1={(row.year1_months ?? [])[i] ?? null}
              onCommit={(amount) =>
                patch.mutate({
                  account_code: row.account_code,
                  month_index: i + 1,
                  year1_amount: amount,
                })
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}

function MonthCell({
  label,
  prior,
  year1,
  onCommit,
}: {
  label: string;
  prior: number | string | null;
  year1: number | string | null;
  onCommit: (amount: number | null) => void;
}) {
  const current = year1 == null ? null : Number(year1);
  return (
    <label className="flex flex-col gap-0.5 text-xs">
      <span className="opacity-60">{label}</span>
      <span className="font-figure opacity-50">last {prior == null ? "—" : fmtUsd(prior)}</span>
      <input
        type="number"
        aria-label={`${label} year one`}
        key={`${label}-${current ?? ""}`}
        defaultValue={current ?? ""}
        onBlur={(e) => {
          const raw = e.target.value;
          const next = raw === "" ? null : Number(raw);
          if (next !== current) onCommit(next);
        }}
        className="w-full rounded border border-brand/20 bg-surface px-2 py-1 font-figure text-sm focus:outline-none focus:ring-2 focus:ring-accent"
      />
    </label>
  );
}
