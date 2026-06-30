/**
 * Budget tab (design doc §5.5): the two-column underwriting grid, rendered as the SAME collapsible
 * hierarchy as the source income statement — section → group → sub-group → detail line, with a
 * "Total" row closing every group and Net Operating Income at the bottom. Each group header has an
 * expand/collapse toggle (its Total stays visible when collapsed); collapse-all / expand-all and an
 * optional "hide rare lines" toggle manage density. Both amount columns are editable; contra lines
 * (Utility Recovery, Discounts …) render in parentheses and net within their parent. Group/section
 * subtotals + NOI come from the server's pure roll-up (no client-side math). Whole-dollar display.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  useAddBudgetLine,
  useBudget,
  useGlAccounts,
  useLockBudget,
  usePatchBudgetLine,
  useRemoveBudgetLine,
  useReorderBudget,
  useRevertBudgetLine,
  useSeedBudget,
  useUnlockBudget,
} from "../../api/hooks";
import type { Schemas } from "../../api/client";

// `revertible` is a new field not yet in the generated contract — augment locally.
type BudgetRow = Schemas["BudgetRow"] & { revertible?: boolean };
type BudgetGroup = Schemas["BudgetGroup"];
type GlAccount = Schemas["GlAccountOption"];
type Patch = ReturnType<typeof usePatchBudgetLine>;
type Add = ReturnType<typeof useAddBudgetLine>;
type Remove = ReturnType<typeof useRemoveBudgetLine>;
type Revert = ReturnType<typeof useRevertBudgetLine>;
type Reorder = ReturnType<typeof useReorderBudget>;

const VARIANCE_BAND = 0.15; // |% var| over this = an over/under to review
const GRID = "grid grid-cols-[1fr_repeat(3,minmax(84px,1fr))_2rem] items-center gap-2";

/** Whole dollars with parentheses for negatives (decision: Budget tab displays whole dollars; full
 * precision is still stored server-side). Read-only cells only — editable inputs keep their value. */
function money(value: number | string | null | undefined): string {
  const n = Math.round(Number(value ?? 0));
  const s = Math.abs(n).toLocaleString("en-US");
  return n < 0 ? `(${s})` : s;
}

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
function rowKey(row: BudgetRow): string {
  return row.line_id ?? row.account_code ?? row.name;
}

// ── Tree assembly ─────────────────────────────────────────────────────────────
// Sections are pseudo-roots; groups + leaf rows hang off a "bucket" = parent_code (or the section
// when there is no parent). The server already returns rows in display order and a subtotal for
// every ancestor group, so the client only nests + folds — it never re-derives a total.

const SECTION_ORDER = ["Income", "Expense"];
function sectionKey(section: string | null | undefined): string {
  return `__sec__:${section ?? "Other"}`;
}
function bucketOf(parent_code: string | null | undefined, section: string | null | undefined) {
  return parent_code ?? sectionKey(section);
}

type Tree = {
  childGroups: Map<string, BudgetGroup[]>;
  childRows: Map<string, BudgetRow[]>;
  sections: { key: string; label: string; section: string | null }[];
  leafBearing: Set<string>; // group codes with at least one direct detail row (default-collapsed)
};

function buildTree(rows: BudgetRow[], groups: BudgetGroup[]): Tree {
  const childGroups = new Map<string, BudgetGroup[]>();
  const childRows = new Map<string, BudgetRow[]>();
  const leafBearing = new Set<string>();
  const push = <T,>(m: Map<string, T[]>, k: string, v: T) => m.set(k, [...(m.get(k) ?? []), v]);

  for (const g of [...groups].sort((a, b) => a.code.localeCompare(b.code))) {
    push(childGroups, bucketOf(g.parent_code, g.section), g);
  }
  for (const r of rows) {
    const bucket = bucketOf(r.parent_code, r.section);
    push(childRows, bucket, r);
    if (r.parent_code) leafBearing.add(r.parent_code);
  }
  const present = new Set<string | null | undefined>([
    ...rows.map((r) => r.section),
    ...groups.map((g) => g.section),
  ]);
  const sections = [
    ...SECTION_ORDER.filter((s) => present.has(s)).map((s) => ({
      key: sectionKey(s),
      label: s === "Income" ? "Revenue" : s,
      section: s,
    })),
    ...(present.has(null) ||
    present.has("Other") ||
    [...present].some((s) => s && !SECTION_ORDER.includes(s))
      ? [
          {
            key: sectionKey("Other"),
            label: "Other (excluded from NOI)",
            section: null as string | null,
          },
        ]
      : []),
  ];
  return { childGroups, childRows, sections, leafBearing };
}

export function BudgetTab({ acquisitionId }: { acquisitionId: string }) {
  const { data, isLoading } = useBudget(acquisitionId);
  const { data: accounts } = useGlAccounts();
  const seed = useSeedBudget(acquisitionId);
  const patch = usePatchBudgetLine(acquisitionId);
  const add = useAddBudgetLine(acquisitionId);
  const remove = useRemoveBudgetLine(acquisitionId);
  const revert = useRevertBudgetLine(acquisitionId);
  const reorder = useReorderBudget(acquisitionId);
  const lock = useLockBudget(acquisitionId);
  const unlock = useUnlockBudget(acquisitionId);
  const [onlyFlagged, setOnlyFlagged] = useState(false);
  const [hideRare, setHideRare] = useState(false);

  const rows = useMemo(() => data?.rows ?? [], [data]);
  const groups = useMemo(() => data?.groups ?? [], [data]);
  const tree = useMemo(() => buildTree(rows, groups), [rows, groups]);

  // Collapse state: default collapsed to group level (leaf-bearing groups folded).
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const signature = useMemo(() => groups.map((g) => g.code).join(","), [groups]);
  const lastSig = useRef<string | null>(null);
  useEffect(() => {
    if (lastSig.current !== signature) {
      lastSig.current = signature;
      setCollapsed(new Set(tree.leafBearing));
    }
  }, [signature, tree.leafBearing]);

  if (isLoading) return <p className="text-sm opacity-70">Loading…</p>;
  const totals = data?.totals;
  const locked = data?.status === "locked";
  const placeholders = data?.placeholder_count ?? 0;
  const unmapped = data?.unmapped_count ?? 0;
  const ready = placeholders === 0 && unmapped === 0;
  const flaggedCount = rows.filter(needsReview).length;
  const accountOptions = accounts ?? [];

  const toggle = (key: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const allGroupCodes = groups.map((g) => g.code);
  const collapseAll = () => setCollapsed(new Set(allGroupCodes));
  const expandAll = () => setCollapsed(new Set());

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium">Underwriting — prior year → year one</span>
        {data?.status && (
          <span className="rounded bg-ink/10 px-2 py-0.5 text-xs text-ink/70">{data.status}</span>
        )}
        {totals && (
          <span className="text-xs opacity-70">
            Year-1 NOI <span className="font-figure">{money(totals.year1_noi)}</span> · prior{" "}
            <span className="font-figure">{money(totals.prior_noi)}</span>
          </span>
        )}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {rows.length > 0 && (
            <>
              <button
                type="button"
                onClick={expandAll}
                className="rounded border border-brand/30 px-2 py-1.5 text-xs"
              >
                Expand all
              </button>
              <button
                type="button"
                onClick={collapseAll}
                className="rounded border border-brand/30 px-2 py-1.5 text-xs"
              >
                Collapse all
              </button>
              <button
                type="button"
                onClick={() => setHideRare((v) => !v)}
                className={`rounded border px-2 py-1.5 text-xs ${
                  hideRare ? "border-brand bg-brand/10 text-brand" : "border-brand/30"
                }`}
              >
                {hideRare ? "Show rare" : "Hide rare"}
              </button>
              <button
                type="button"
                onClick={() => setOnlyFlagged((v) => !v)}
                className={`rounded border px-2 py-1.5 text-xs ${
                  onlyFlagged ? "border-accent bg-accent/15 text-accent-ink" : "border-brand/30"
                }`}
              >
                {onlyFlagged
                  ? "Show all"
                  : `Overs & unders${flaggedCount ? ` (${flaggedCount})` : ""}`}
              </button>
            </>
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

      {!locked && rows.length > 0 && !ready && (
        <p className="text-xs text-accent-ink">
          {placeholders} to review · {unmapped} unmapped — resolve to lock.
        </p>
      )}

      {rows.length === 0 ? (
        <p className="rounded border border-brand/20 p-3 text-sm opacity-80">
          No budget yet. Map the uploaded P&amp;L on the GL / Docs tab, then “Seed from actuals” to
          prefill prior-year and year-one — then edit either column, add or remove lines, and review
          the overs and unders here.
        </p>
      ) : (
        <div>
          <div className={`${GRID} px-2 pb-1 text-xs uppercase tracking-wide opacity-60`}>
            <span>Account</span>
            <span className="text-right">Prior year</span>
            <span className="text-right">Year one</span>
            <span className="text-right">$ var</span>
            <span />
          </div>
          {tree.sections.map((sec) => (
            <SectionBlock
              key={sec.key}
              sectionKey={sec.key}
              label={sec.label}
              section={sec.section}
              tree={tree}
              collapsed={collapsed}
              toggle={toggle}
              onlyFlagged={onlyFlagged}
              hideRare={hideRare}
              totals={totals}
              accounts={accountOptions}
              mutations={{ patch, add, remove, revert, reorder }}
              allRows={rows}
            />
          ))}
          {totals && (
            <div
              className={`${GRID} mt-1 border-t-2 border-brand/40 px-2 pt-2 text-sm font-semibold`}
            >
              <span>Net Operating Income</span>
              <span className="text-right font-figure">{money(totals.prior_noi)}</span>
              <span className="text-right font-figure">{money(totals.year1_noi)}</span>
              <span className="text-right font-figure opacity-70">
                {money(Number(totals.year1_noi) - Number(totals.prior_noi))}
              </span>
              <span />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

type Mutations = { patch: Patch; add: Add; remove: Remove; revert: Revert; reorder: Reorder };

function SectionBlock(props: {
  sectionKey: string;
  label: string;
  section: string | null;
  tree: Tree;
  collapsed: Set<string>;
  toggle: (k: string) => void;
  onlyFlagged: boolean;
  hideRare: boolean;
  totals: Schemas["BudgetTotals"] | undefined;
  accounts: GlAccount[];
  mutations: Mutations;
  allRows: BudgetRow[];
}) {
  const { sectionKey, label, section, collapsed, totals } = props;
  const open = !collapsed.has(sectionKey);
  const secTotal =
    section === "Income"
      ? totals && { prior: totals.prior_revenue, year1: totals.year1_revenue }
      : section === "Expense"
        ? totals && { prior: totals.prior_opex, year1: totals.year1_opex }
        : null;

  return (
    <div className="mt-1">
      <div className={`${GRID} rounded bg-brand/5 px-2 py-1 text-sm font-semibold`}>
        <button
          type="button"
          onClick={() => props.toggle(sectionKey)}
          className="flex items-center gap-1 text-left"
        >
          <Chevron open={open} />
          {label.toUpperCase()}
        </button>
        <span className="text-right font-figure">{secTotal ? money(secTotal.prior) : ""}</span>
        <span className="text-right font-figure">{secTotal ? money(secTotal.year1) : ""}</span>
        <span className="text-right font-figure opacity-70">
          {secTotal ? money(Number(secTotal.year1) - Number(secTotal.prior)) : ""}
        </span>
        <span />
      </div>
      {open && <NodeChildren {...props} bucket={sectionKey} depth={1} />}
      {section && (
        <AddLineForm
          section={section}
          accounts={props.accounts}
          add={props.mutations.add}
          depth={1}
        />
      )}
    </div>
  );
}

/** Render the groups + detail rows hanging off one bucket (a section root or a group code). */
function NodeChildren(props: {
  bucket: string;
  depth: number;
  tree: Tree;
  collapsed: Set<string>;
  toggle: (k: string) => void;
  onlyFlagged: boolean;
  hideRare: boolean;
  accounts: GlAccount[];
  mutations: Mutations;
  allRows: BudgetRow[];
}) {
  const { bucket, depth, tree, collapsed, onlyFlagged, hideRare, mutations, allRows } = props;
  const groups = tree.childGroups.get(bucket) ?? [];
  let rows = tree.childRows.get(bucket) ?? [];
  if (onlyFlagged) rows = rows.filter(needsReview);
  if (hideRare) rows = rows.filter((r) => r.tier !== "rare");

  // Drag-to-reorder within this bucket: send the full display order with the row moved, so the
  // server's dense sort_order stays globally consistent.
  const fromIdx = useRef<number | null>(null);
  const [overKey, setOverKey] = useState<string | null>(null);
  const drop = (toKey: string) => {
    const from = fromIdx.current;
    fromIdx.current = null;
    setOverKey(null);
    if (from === null) return;
    const ordered = [...rows];
    const toIdx = ordered.findIndex((r) => rowKey(r) === toKey);
    if (toIdx < 0 || from === toIdx) return;
    const [moved] = ordered.splice(from, 1);
    ordered.splice(toIdx, 0, moved);
    // Rebuild the full row order: replace this bucket's slice with the reordered one.
    const movedKeys = new Set(ordered.map(rowKey));
    const full: BudgetRow[] = [];
    let injected = false;
    for (const r of allRows) {
      if (movedKeys.has(rowKey(r))) {
        if (!injected) {
          full.push(...ordered);
          injected = true;
        }
      } else {
        full.push(r);
      }
    }
    mutations.reorder.mutate({ lines: full.map(lineRef) });
  };

  return (
    <>
      {groups.map((g) => {
        const gOpen = !collapsed.has(g.code);
        return (
          <div key={g.code}>
            <div
              className={`${GRID} px-2 py-1 text-sm font-medium`}
              style={{ paddingLeft: `${0.5 + depth * 1}rem` }}
            >
              <button
                type="button"
                onClick={() => props.toggle(g.code)}
                className="flex items-center gap-1 text-left"
              >
                <Chevron open={gOpen} />
                <span className="opacity-50">{g.code}</span> {g.name}
              </button>
              <span className="text-right font-figure">{money(g.prior_annual)}</span>
              <span className="text-right font-figure">{money(g.year1_annual)}</span>
              <span className="text-right font-figure opacity-70">{money(g.var_abs)}</span>
              <span />
            </div>
            {gOpen && <NodeChildren {...props} bucket={g.code} depth={depth + 1} />}
          </div>
        );
      })}
      {rows.map((r, i) => (
        <Row
          key={rowKey(r)}
          row={r}
          depth={depth}
          patch={mutations.patch}
          remove={mutations.remove}
          revert={mutations.revert}
          canReorder={!onlyFlagged && !hideRare && rows.length > 1}
          isOver={overKey === rowKey(r)}
          onDragStart={() => (fromIdx.current = i)}
          onDragOver={() => setOverKey(rowKey(r))}
          onDrop={() => drop(rowKey(r))}
          onDragEnd={() => {
            fromIdx.current = null;
            setOverKey(null);
          }}
        />
      ))}
    </>
  );
}

function Chevron({ open }: { open: boolean }) {
  return <span className={`inline-block w-3 text-ink/50 ${open ? "" : "-rotate-90"}`}>▾</span>;
}

function Row({
  row,
  depth,
  patch,
  remove,
  revert,
  canReorder,
  isOver,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
}: {
  row: BudgetRow;
  depth: number;
  patch: Patch;
  remove: Remove;
  revert: Revert;
  canReorder: boolean;
  isOver: boolean;
  onDragStart: () => void;
  onDragOver: () => void;
  onDrop: () => void;
  onDragEnd: () => void;
}) {
  const b = badge(row);
  const over = isOverUnder(row);
  const flagged = needsReview(row);
  const v_abs = Number(row.var_abs ?? 0);
  const [armed, setArmed] = useState(false);

  const commit = (field: "prior_amount" | "year1_amount", n: number) =>
    patch.mutate({ ...lineRef(row), [field]: n });
  const onRevert = () => {
    if (row.line_id) revert.mutate(row.line_id);
  };
  const onRemove = () => {
    if (!row.line_id) return; // un-seeded row: nothing stored to remove
    const hasData = Number(row.year1_annual || 0) !== 0 || Number(row.prior_annual || 0) !== 0;
    if (hasData && !window.confirm(`Remove “${row.name}” from the year-one projection?`)) return;
    remove.mutate(row.line_id);
  };

  return (
    <div
      draggable={canReorder && armed}
      onDragStart={onDragStart}
      onDragOver={(e) => {
        if (!canReorder) return;
        e.preventDefault();
        onDragOver();
      }}
      onDrop={(e) => {
        e.preventDefault();
        onDrop();
      }}
      onDragEnd={() => {
        setArmed(false);
        onDragEnd();
      }}
      className={`group ${GRID} rounded-md border px-2 py-1 text-sm ${
        flagged ? "border-accent/60" : "border-transparent"
      } ${row.removed ? "opacity-50" : ""} ${isOver ? "border-brand border-dashed" : ""}`}
      style={{ paddingLeft: `${0.5 + depth * 1}rem` }}
    >
      <span className="flex items-center gap-2">
        {canReorder && (
          <span
            role="button"
            aria-label={`Drag to reorder ${row.name}`}
            title="Drag to reorder within this group"
            onMouseDown={() => setArmed(true)}
            onMouseUp={() => setArmed(false)}
            className="cursor-grab select-none text-ink/30 hover:text-ink/60 active:cursor-grabbing"
          >
            ⠿
          </span>
        )}
        <span className={`rounded px-1.5 py-0.5 text-[10px] ${b.cls}`}>{b.label}</span>
        {row.account_code && <span className="text-[10px] opacity-40">{row.account_code}</span>}
        <span className={row.removed ? "line-through" : ""}>{row.name}</span>
        {row.is_contra && (
          <span title="Contra line — nets against its group" className="text-[10px] text-ink/50">
            ∓
          </span>
        )}
        {row.flagged_for_promotion && (
          <span title="Custom line — promote to the GL chart later" className="text-accent-ink">
            ⚑
          </span>
        )}
        {row.revertible && (
          <button
            type="button"
            onClick={onRevert}
            disabled={revert.isPending}
            title="Revert this manual edit back to the default value"
            className="text-[10px] text-brand hover:underline disabled:opacity-50"
          >
            ↺ revert
          </button>
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
        {row.removed ? "—" : money(v_abs)}
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
  depth,
}: {
  section: string;
  accounts: GlAccount[];
  add: Add;
  depth: number;
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
        className="py-1 text-left text-xs text-brand hover:underline"
        style={{ paddingLeft: `${0.5 + depth * 1}rem` }}
      >
        + Add line item
      </button>
    );
  }
  return (
    <div
      className="my-1 flex flex-wrap items-center gap-2 rounded border border-brand/20 bg-surface p-2"
      style={{ marginLeft: `${0.5 + depth * 1}rem` }}
    >
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
