/**
 * Budget tab (design doc §5.5): the two-column underwriting grid. Each line item shows its
 * prior-year value (from the mapped P&L) beside the editable year-one projection — BOTH columns
 * are editable (correct an upload, move an expense). Lines are grouped into Revenue and Expense;
 * "+ Add line item" inserts a canonical GL or a custom (flagged) line; the × removes a row
 * (custom → deleted; a mapped line → dropped from year-one, prior kept as reference). Live section
 * totals + NOI recompute on every edit; NOI flows downstream to the pro forma / cash flow /
 * waterfall. Provenance (actuals / default / to review / custom / edited) stays visible.
 */
import { useMemo, useState } from "react";
import {
  useAddBudgetLine,
  useBudget,
  useGlAccounts,
  useLockBudget,
  usePatchBudgetLine,
  useRemoveBudgetLine,
  useSeedBudget,
  useUnlockBudget,
} from "../../api/hooks";
import type { Schemas } from "../../api/client";
import { fmtUsd } from "../../lib/format";

type BudgetRow = Schemas["BudgetRow"];
type GlAccount = Schemas["GlAccountOption"];
type Patch = ReturnType<typeof usePatchBudgetLine>;
type Add = ReturnType<typeof useAddBudgetLine>;
type Remove = ReturnType<typeof useRemoveBudgetLine>;

const VARIANCE_BAND = 0.15; // |% var| over this = an over/under to review

function isOverUnder(row: BudgetRow): boolean {
  return row.var_pct != null && Math.abs(Number(row.var_pct)) > VARIANCE_BAND;
}
function needsReview(row: BudgetRow): boolean {
  return row.source === "placeholder" || isOverUnder(row);
}

function badge(row: BudgetRow): { label: string; cls: string } {
  if (row.source === "custom") return { label: "custom", cls: "bg-accent/15 text-accent-ink" };
  if (row.is_overridden) return { label: "edited", cls: "bg-ink/10 text-ink/70" };
  if (row.source === "actuals") return { label: "actuals", cls: "bg-success/15 text-success" };
  if (row.source === "default") return { label: "default", cls: "bg-brand/10 text-brand" };
  if (row.source === "placeholder")
    return { label: "to review", cls: "bg-accent/15 text-accent-ink" };
  return { label: row.source, cls: "bg-ink/10 text-ink/70" };
}

/** Identify a row for a PATCH: prefer its stored line_id, else its GL account (un-seeded row). */
function lineRef(row: BudgetRow): { line_id?: string; account_code?: string } {
  if (row.line_id) return { line_id: row.line_id };
  if (row.account_code) return { account_code: row.account_code };
  return {};
}

export function BudgetTab({ acquisitionId }: { acquisitionId: string }) {
  const { data, isLoading } = useBudget(acquisitionId);
  const { data: accounts } = useGlAccounts();
  const seed = useSeedBudget(acquisitionId);
  const patch = usePatchBudgetLine(acquisitionId);
  const add = useAddBudgetLine(acquisitionId);
  const remove = useRemoveBudgetLine(acquisitionId);
  const lock = useLockBudget(acquisitionId);
  const unlock = useUnlockBudget(acquisitionId);
  const [onlyFlagged, setOnlyFlagged] = useState(false);

  const rows = useMemo(() => data?.rows ?? [], [data]);
  if (isLoading) return <p className="text-sm opacity-70">Loading…</p>;
  const totals = data?.totals;
  const locked = data?.status === "locked";
  const placeholders = data?.placeholder_count ?? 0;
  const unmapped = data?.unmapped_count ?? 0;
  const ready = placeholders === 0 && unmapped === 0;
  const flaggedCount = rows.filter(needsReview).length;
  const accountOptions = accounts ?? [];

  const revenue = rows.filter((r) => r.section === "Income");
  const expense = rows.filter((r) => r.section === "Expense");
  const other = rows.filter((r) => r.section !== "Income" && r.section !== "Expense");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium">Underwriting — prior year → year one</span>
        {data?.status && (
          <span className="rounded bg-ink/10 px-2 py-0.5 text-xs text-ink/70">{data.status}</span>
        )}
        {totals && (
          <span className="text-xs opacity-70">
            Year-1 NOI <span className="font-figure">{fmtUsd(totals.year1_noi)}</span> · prior{" "}
            <span className="font-figure">{fmtUsd(totals.prior_noi)}</span>
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          {!locked && rows.length > 0 && !ready && (
            <span className="text-xs text-accent-ink">
              {placeholders} to review · {unmapped} unmapped
            </span>
          )}
          {rows.length > 0 && (
            <button
              type="button"
              onClick={() => setOnlyFlagged((v) => !v)}
              className={`rounded border px-3 py-1.5 text-sm ${
                onlyFlagged ? "border-accent bg-accent/15 text-accent-ink" : "border-brand/30"
              }`}
            >
              {onlyFlagged
                ? "Show all"
                : `Overs & unders${flaggedCount ? ` (${flaggedCount})` : ""}`}
            </button>
          )}
          <button
            type="button"
            disabled={seed.isPending}
            onClick={() => seed.mutate()}
            className="rounded border border-brand/30 px-3 py-1.5 text-sm disabled:opacity-50"
          >
            {seed.isPending ? "Seeding…" : rows.length === 0 ? "Seed from actuals" : "Re-seed gaps"}
          </button>
          {rows.length > 0 &&
            (locked ? (
              <button
                type="button"
                disabled={unlock.isPending}
                onClick={() => unlock.mutate()}
                className="rounded border border-brand/30 px-3 py-1.5 text-sm disabled:opacity-50"
              >
                {unlock.isPending ? "Unlocking…" : "Unlock"}
              </button>
            ) : (
              <button
                type="button"
                disabled={!ready || lock.isPending}
                onClick={() => lock.mutate()}
                className="rounded bg-brand px-3 py-1.5 text-sm text-surface disabled:opacity-50"
              >
                {lock.isPending ? "Locking…" : "Lock budget"}
              </button>
            ))}
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="rounded border border-brand/20 p-3 text-sm opacity-80">
          No budget yet. Map the uploaded P&amp;L on the GL / Docs tab, then “Seed from actuals” to
          prefill prior-year and year-one — then edit either column, add or remove lines, and review
          the overs and unders here.
        </p>
      ) : (
        <>
          <Section
            title="Revenue"
            section="Income"
            rows={revenue}
            onlyFlagged={onlyFlagged}
            accounts={accountOptions}
            patch={patch}
            add={add}
            remove={remove}
          />
          <Section
            title="Expense"
            section="Expense"
            rows={expense}
            onlyFlagged={onlyFlagged}
            accounts={accountOptions}
            patch={patch}
            add={add}
            remove={remove}
          />
          {other.length > 0 && (
            <Section
              title="Other (excluded from NOI)"
              section={null}
              rows={other}
              onlyFlagged={onlyFlagged}
              accounts={accountOptions}
              patch={patch}
              add={add}
              remove={remove}
            />
          )}
          {totals && (
            <div className="grid grid-cols-[1fr_repeat(3,minmax(96px,1fr))_2rem] gap-2 border-t-2 border-brand/30 px-2 pt-2 text-sm font-semibold">
              <span>Net Operating Income</span>
              <span className="text-right font-figure">{fmtUsd(totals.prior_noi)}</span>
              <span className="text-right font-figure">{fmtUsd(totals.year1_noi)}</span>
              <span className="text-right font-figure opacity-70">
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

function Section({
  title,
  section,
  rows,
  onlyFlagged,
  accounts,
  patch,
  add,
  remove,
}: {
  title: string;
  section: string | null;
  rows: BudgetRow[];
  onlyFlagged: boolean;
  accounts: GlAccount[];
  patch: Patch;
  add: Add;
  remove: Remove;
}) {
  const shown = onlyFlagged ? rows.filter(needsReview) : rows;
  const priorTotal = rows.reduce((s, r) => s + Number(r.prior_annual || 0), 0);
  const yearTotal = rows.reduce((s, r) => s + (r.removed ? 0 : Number(r.year1_annual || 0)), 0);
  return (
    <div>
      <div className="grid grid-cols-[1fr_repeat(3,minmax(96px,1fr))_2rem] gap-2 px-2 pb-1 text-xs uppercase tracking-wide opacity-60">
        <span>{title}</span>
        <span className="text-right">Prior year</span>
        <span className="text-right">Year one</span>
        <span className="text-right">$ var</span>
        <span />
      </div>
      <div className="space-y-1">
        {shown.map((r) => (
          <Row key={r.line_id ?? r.account_code ?? r.name} row={r} patch={patch} remove={remove} />
        ))}
      </div>
      {section && <AddLineForm section={section} accounts={accounts} add={add} />}
      <div className="grid grid-cols-[1fr_repeat(3,minmax(96px,1fr))_2rem] gap-2 border-t border-brand/20 px-2 pt-1 text-sm font-medium">
        <span>Total {title.toLowerCase()}</span>
        <span className="text-right font-figure">{fmtUsd(priorTotal)}</span>
        <span className="text-right font-figure">{fmtUsd(yearTotal)}</span>
        <span />
        <span />
      </div>
    </div>
  );
}

function Row({ row, patch, remove }: { row: BudgetRow; patch: Patch; remove: Remove }) {
  const b = badge(row);
  const over = isOverUnder(row);
  const flagged = needsReview(row);
  const v_abs = Number(row.var_abs ?? 0);

  const commit = (field: "prior_amount" | "year1_amount", n: number) =>
    patch.mutate({ ...lineRef(row), [field]: n });

  const onRemove = () => {
    if (!row.line_id) return; // un-seeded row: nothing stored to remove
    const hasData = Number(row.year1_annual || 0) !== 0 || Number(row.prior_annual || 0) !== 0;
    if (hasData && !window.confirm(`Remove “${row.name}” from the year-one projection?`)) return;
    remove.mutate(row.line_id);
  };

  return (
    <div
      className={`group grid grid-cols-[1fr_repeat(3,minmax(96px,1fr))_2rem] items-center gap-2 rounded-md border px-2 py-1 text-sm ${
        flagged ? "border-accent/60" : "border-brand/10"
      } ${row.removed ? "opacity-50" : ""}`}
    >
      <span className="flex items-center gap-2">
        <span className={`rounded px-1.5 py-0.5 text-[10px] ${b.cls}`}>{b.label}</span>
        <span className={row.removed ? "line-through" : ""}>{row.name}</span>
        {row.flagged_for_promotion && (
          <span title="Custom line — promote to the GL chart later" className="text-accent-ink">
            ⚑
          </span>
        )}
      </span>
      <AmountCell
        value={row.prior_annual}
        edited={row.prior_overridden}
        onCommit={(n) => commit("prior_amount", n)}
      />
      {row.removed ? (
        <span className="text-right font-figure opacity-60">removed</span>
      ) : (
        <AmountCell
          value={row.year1_annual}
          edited={row.is_overridden}
          onCommit={(n) => commit("year1_amount", n)}
        />
      )}
      <span className={`text-right font-figure ${over ? "text-accent-ink" : "opacity-70"}`}>
        {row.removed ? "—" : fmtUsd(v_abs)}
      </span>
      <button
        type="button"
        aria-label={`Remove ${row.name}`}
        onClick={onRemove}
        disabled={!row.line_id || row.removed}
        className="justify-self-end rounded px-1 text-ink/40 opacity-0 hover:text-danger group-hover:opacity-100 disabled:hidden"
      >
        ×
      </button>
    </div>
  );
}

function AmountCell({
  value,
  edited,
  onCommit,
}: {
  value: number | string | null;
  edited?: boolean;
  onCommit: (n: number) => void;
}) {
  const current = value == null ? null : Number(value);
  return (
    <input
      type="number"
      aria-label="amount"
      key={current ?? ""}
      defaultValue={current ?? ""}
      onBlur={(e) => {
        const raw = e.target.value;
        if (raw === "") return; // empty = no change (type a number to edit)
        const next = Number(raw);
        if (next !== current) onCommit(next);
      }}
      className={`w-full rounded border bg-surface px-2 py-1 text-right font-figure text-sm focus:outline-none focus:ring-2 focus:ring-accent ${
        edited ? "border-ink/40" : "border-brand/20"
      }`}
    />
  );
}

/** "+ Add line item": pick a canonical GL for this section, or type a custom label + value. */
function AddLineForm({
  section,
  accounts,
  add,
}: {
  section: string;
  accounts: GlAccount[];
  add: Add;
}) {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const [label, setLabel] = useState("");
  const [amount, setAmount] = useState("");
  const sectionAccounts = accounts.filter((a) => a.section === section);

  const reset = () => {
    setCode("");
    setLabel("");
    setAmount("");
    setOpen(false);
  };
  const submit = () => {
    const year1_amount = amount === "" ? null : Number(amount);
    if (code) {
      add.mutate({ account_code: code, section, year1_amount }, { onSuccess: reset });
    } else if (label.trim()) {
      add.mutate({ custom_label: label.trim(), section, year1_amount }, { onSuccess: reset });
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="px-2 py-1 text-left text-xs text-brand hover:underline"
      >
        + Add line item
      </button>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-2 rounded border border-brand/20 bg-surface p-2">
      <select
        aria-label="GL account"
        value={code}
        onChange={(e) => {
          setCode(e.target.value);
          if (e.target.value) setLabel("");
        }}
        className="min-w-[200px] rounded border border-brand/20 bg-surface px-2 py-1 text-sm"
      >
        <option value="">Custom line…</option>
        {sectionAccounts.map((a) => (
          <option key={a.account_code} value={a.account_code}>
            {a.account_code} · {a.name}
          </option>
        ))}
      </select>
      {!code && (
        <input
          aria-label="Custom line name"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Custom name"
          className="min-w-[160px] rounded border border-brand/20 bg-surface px-2 py-1 text-sm"
        />
      )}
      <input
        type="number"
        aria-label="Amount"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        placeholder="Year-one $"
        className="w-32 rounded border border-brand/20 bg-surface px-2 py-1 text-right font-figure text-sm"
      />
      <button
        type="button"
        disabled={(!code && !label.trim()) || add.isPending}
        onClick={submit}
        className="rounded bg-brand px-3 py-1 text-sm text-surface disabled:opacity-50"
      >
        Add
      </button>
      <button type="button" onClick={reset} className="px-2 py-1 text-xs opacity-60">
        Cancel
      </button>
    </div>
  );
}
