/**
 * Promote Waterfall calculator (standalone tool). Reconstructs the deal-by-deal JV promote
 * model: an editable input set drives a live recalculation (debounced POST to the pure Python
 * engine) and shows returns for both equity positions — **Partner Equity** and **RJourney
 * Equity** — plus the deal-level reference. Genericized: no fund/brand/property names.
 *
 * Presentational; the calculation lives server-side (usePromoteWaterfall). No browser storage.
 */
import { useEffect, useRef, useState } from "react";
import { usePromoteWaterfall } from "../api/hooks";
import type { Schemas } from "../api/client";
import { fmtMult, fmtPct, fmtUsd } from "../lib/format";

type PromoteRequest = Schemas["PromoteRequest"];

const DEFAULTS: PromoteRequest = {
  deal_name: "Deal 1",
  start_date: "2025-12-31",
  hold_years: 5,
  equity: 150000000,
  ltv: 0.65,
  acquisition_fee_pct: 0,
  mgmt_fee_pct: 0,
  rjourney_coinvest_pct: 0.1,
  yr1_distribution_pct: 0.05,
  distribution_growth: 0.05,
  exit: { cap_rate: 0.05, base_value: 300000000, income_yield: 0.07 },
  hurdles: [0.08, 0.15, 0.2, 0.2],
  promotes: [0.1, 0.2, 0.3, 0.3],
  cashflow_override: null,
};

type Form = Omit<PromoteRequest, "exit" | "hurdles" | "promotes" | "cashflow_override"> & {
  exit: { cap_rate: number; base_value: number; income_yield: number };
  hurdles: number[];
  promotes: number[];
  cashflow_override: number[] | null;
};

function num(v: unknown): number {
  return Number(v) || 0;
}

// A labelled numeric input. `pct` fields display ×100 and store the decimal.
function Field({
  label,
  value,
  onChange,
  pct = false,
  money = false,
  step,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
  pct?: boolean;
  money?: boolean;
  step?: number;
}) {
  const shown = pct ? value * 100 : value;
  return (
    <label className="flex flex-col gap-1 text-xs">
      <span className="opacity-70">
        {label}
        {pct ? " (%)" : money ? " ($)" : ""}
      </span>
      <input
        type="number"
        aria-label={label}
        value={Number.isFinite(shown) ? shown : 0}
        step={step ?? (pct ? 0.5 : money ? 1000000 : 1)}
        onChange={(e) => onChange(pct ? num(e.target.value) / 100 : num(e.target.value))}
        className="w-full rounded border border-brand/20 bg-surface px-2 py-1 font-figure text-sm focus:outline-none focus:ring-2 focus:ring-accent"
      />
    </label>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <fieldset className="rounded-lg border border-brand/15 p-3">
      <legend className="px-1 text-xs font-medium uppercase tracking-wide opacity-70">
        {title}
      </legend>
      <div className="grid grid-cols-2 gap-3">{children}</div>
    </fieldset>
  );
}

export function Promote() {
  const [form, setForm] = useState<Form>(DEFAULTS as Form);
  const calc = usePromoteWaterfall();
  const timer = useRef<ReturnType<typeof setTimeout>>();

  // Live recalc: debounce edits, then POST. Runs on mount for the reference scenario too.
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => calc.mutate(form), 350);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form]);

  const set = (patch: Partial<Form>) => setForm((f) => ({ ...f, ...patch }));
  const partnerPct = 1 - num(form.rjourney_coinvest_pct);
  const r = calc.data;

  return (
    <section className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Promote Waterfall</h1>
        <p className="mt-1 text-sm opacity-70">
          Deal-by-deal JV returns — IRR hurdles &amp; promote splits. Edit any input; results
          recalculate live.
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,360px)_1fr]">
        {/* ── Inputs ───────────────────────────────────────── */}
        <div className="space-y-3">
          <Panel title="Deal setup">
            <label className="col-span-2 flex flex-col gap-1 text-xs">
              <span className="opacity-70">Deal name</span>
              <input
                aria-label="Deal name"
                value={form.deal_name}
                onChange={(e) => set({ deal_name: e.target.value })}
                className="rounded border border-brand/20 bg-surface px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs">
              <span className="opacity-70">Start date</span>
              <input
                type="date"
                aria-label="Start date"
                value={String(form.start_date)}
                onChange={(e) => set({ start_date: e.target.value })}
                className="rounded border border-brand/20 bg-surface px-2 py-1 font-figure text-sm focus:outline-none focus:ring-2 focus:ring-accent"
              />
            </label>
            <Field
              label="Total equity"
              money
              value={num(form.equity)}
              onChange={(n) => set({ equity: n })}
            />
            <Field label="Asset LTV" pct value={num(form.ltv)} onChange={(n) => set({ ltv: n })} />
            <Field
              label="Acquisition fee"
              pct
              value={num(form.acquisition_fee_pct)}
              onChange={(n) => set({ acquisition_fee_pct: n })}
            />
            <Field
              label="Mgmt fee / yr"
              pct
              value={num(form.mgmt_fee_pct)}
              onChange={(n) => set({ mgmt_fee_pct: n })}
            />
          </Panel>

          <Panel title="Equity split">
            <Field
              label="RJourney co-invest"
              pct
              value={num(form.rjourney_coinvest_pct)}
              onChange={(n) => set({ rjourney_coinvest_pct: n })}
            />
            <label className="flex flex-col gap-1 text-xs">
              <span className="opacity-70">Partner equity (%)</span>
              <output className="rounded border border-brand/10 bg-surface/50 px-2 py-1 font-figure text-sm">
                {fmtPct(partnerPct)}
              </output>
            </label>
          </Panel>

          <Panel title="Return case">
            <Field
              label="Year-1 distribution"
              pct
              value={num(form.yr1_distribution_pct)}
              onChange={(n) => set({ yr1_distribution_pct: n })}
            />
            <Field
              label="Distribution growth"
              pct
              value={num(form.distribution_growth)}
              onChange={(n) => set({ distribution_growth: n })}
            />
          </Panel>

          <Panel title="Exit (year 5 reversion)">
            <Field
              label="Exit cap rate"
              pct
              value={form.exit.cap_rate}
              onChange={(n) => set({ exit: { ...form.exit, cap_rate: n } })}
            />
            <Field
              label="Income yield"
              pct
              value={form.exit.income_yield}
              onChange={(n) => set({ exit: { ...form.exit, income_yield: n } })}
            />
            <Field
              label="Reversion base value"
              money
              value={form.exit.base_value}
              onChange={(n) => set({ exit: { ...form.exit, base_value: n } })}
            />
          </Panel>

          <Panel title="Hurdles & promotes">
            {form.hurdles.map((h, i) => (
              <Field
                key={`h${i}`}
                label={`Hurdle ${i + 1}`}
                pct
                value={h}
                onChange={(n) => set({ hurdles: form.hurdles.map((x, j) => (j === i ? n : x)) })}
              />
            ))}
            {form.promotes.map((p, i) => (
              <Field
                key={`p${i}`}
                label={`Promote ${i + 1}`}
                pct
                value={p}
                onChange={(n) => set({ promotes: form.promotes.map((x, j) => (j === i ? n : x)) })}
              />
            ))}
          </Panel>
        </div>

        {/* ── Outputs ──────────────────────────────────────── */}
        <div className="space-y-4">
          {calc.isError && (
            <p role="alert" className="rounded border border-danger/30 p-3 text-sm text-danger">
              Couldn’t calculate — check the inputs.
            </p>
          )}
          {!r && !calc.isError && <p className="text-sm opacity-70">Calculating…</p>}
          {r && (
            <>
              <ReturnsSummary result={r} />
              <ContributionAndProfit result={r} />
              <TierBreakdown result={r} />
              <AnnualTable
                title="Partner Equity — annual cash flow"
                position={r.partner}
                dates={r.dates}
              />
              <AnnualTable
                title="RJourney Equity — annual cash flow"
                position={r.rjourney}
                dates={r.dates}
              />
            </>
          )}
        </div>
      </div>
    </section>
  );
}

type Result = Schemas["PromoteResponse"];

function ReturnsSummary({ result }: { result: Result }) {
  const cols: [string, Schemas["PositionOut"]][] = [
    ["Partner Equity", result.partner],
    ["RJourney Equity", result.rjourney],
    ["Deal-Level", result.deal],
  ];
  return (
    <div className="rounded-lg border border-brand/15 p-4">
      <h2 className="text-sm font-medium">Returns summary</h2>
      <table className="mt-2 w-full text-sm">
        <thead>
          <tr className="text-left">
            <th className="py-1 font-medium">Metric</th>
            {cols.map(([label]) => (
              <th key={label} className="py-1 text-right font-medium">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="border-t border-brand/10">
            <td className="py-1">IRR</td>
            {cols.map(([label, p]) => (
              <td key={label} className="py-1 text-right font-figure">
                {fmtPct(p.irr)}
              </td>
            ))}
          </tr>
          <tr className="border-t border-brand/10">
            <td className="py-1">MOIC</td>
            {cols.map(([label, p]) => (
              <td key={label} className="py-1 text-right font-figure">
                {fmtMult(p.moic)}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function ContributionAndProfit({ result }: { result: Result }) {
  const items: [string, string, string][] = [
    ["Equity contributed", fmtUsd(result.partner.equity), fmtUsd(result.rjourney.equity)],
    ["Profit", fmtUsd(result.partner.profit), fmtUsd(result.rjourney.profit)],
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="rounded-lg border border-brand/15 p-4">
        <h2 className="text-sm font-medium">Equity &amp; profit</h2>
        <table className="mt-2 w-full text-sm">
          <thead>
            <tr className="text-left">
              <th className="py-1" />
              <th className="py-1 text-right font-medium">Partner</th>
              <th className="py-1 text-right font-medium">RJourney</th>
            </tr>
          </thead>
          <tbody>
            {items.map(([label, a, b]) => (
              <tr key={label} className="border-t border-brand/10">
                <td className="py-1">{label}</td>
                <td className="py-1 text-right font-figure">{a}</td>
                <td className="py-1 text-right font-figure">{b}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="rounded-lg border border-brand/15 p-4">
        <h2 className="text-sm font-medium">Promote / carried interest</h2>
        <p className="mt-2 font-figure text-2xl">{fmtUsd(result.total_promote)}</p>
        <p className="mt-1 text-xs opacity-70">
          Purchase price {fmtUsd(result.purchase_price)} · waterfall reconciles:{" "}
          {result.cashflow_ties_out ? "✓" : "✗"}
        </p>
      </div>
    </div>
  );
}

function TierBreakdown({ result }: { result: Result }) {
  return (
    <div className="rounded-lg border border-brand/15 p-4 overflow-x-auto">
      <h2 className="text-sm font-medium">Per-tier waterfall</h2>
      <table className="mt-2 min-w-[560px] w-full text-sm">
        <thead>
          <tr className="text-left">
            <th className="py-1 font-medium">Tier</th>
            <th className="py-1 text-right font-medium">Hurdle</th>
            <th className="py-1 text-right font-medium">Promote</th>
            <th className="py-1 text-right font-medium">To Combined Equity</th>
            <th className="py-1 text-right font-medium">To RJourney (carry)</th>
            <th className="py-1 text-right font-medium">IRR check</th>
          </tr>
        </thead>
        <tbody>
          {result.tiers.map((t) => (
            <tr key={t.tier} className="border-t border-brand/10">
              <td className="py-1">Hurdle {t.tier}</td>
              <td className="py-1 text-right font-figure">{fmtPct(t.hurdle_rate)}</td>
              <td className="py-1 text-right font-figure">{fmtPct(t.promote_pct)}</td>
              <td className="py-1 text-right font-figure">{fmtUsd(t.equity_total)}</td>
              <td className="py-1 text-right font-figure">{fmtUsd(t.carry_total)}</td>
              <td className="py-1 text-right">
                <span className={t.binds ? "text-brand" : "opacity-50"}>
                  {fmtPct(t.irr_check)} {t.binds ? "✓" : "(not binding)"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AnnualTable({
  title,
  position,
  dates,
}: {
  title: string;
  position: Schemas["PositionOut"];
  dates: string[];
}) {
  return (
    <div className="rounded-lg border border-brand/15 p-4 overflow-x-auto">
      <h2 className="text-sm font-medium">{title}</h2>
      <table className="mt-2 min-w-[480px] w-full text-sm">
        <thead>
          <tr className="text-left">
            <th className="py-1 font-medium">Year</th>
            {position.cashflows.map((_, i) => (
              <th key={i} className="py-1 text-right font-medium">
                {i}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="border-t border-brand/10">
            <td className="py-1 opacity-70">{(dates[0] ?? "").slice(0, 4)}…</td>
            {position.cashflows.map((cf, i) => (
              <td key={i} className="py-1 text-right font-figure">
                {fmtUsd(cf)}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
