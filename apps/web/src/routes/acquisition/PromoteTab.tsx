/**
 * Promote tab — the acquisition-by-acquisition JV promote waterfall, living inside a acquisition beside its pro
 * forma (not a standalone page). It consumes THIS acquisition's pro forma cash flows: the acquisition-level
 * equity stream ([-equity_basis, levered CF…, +net exit]) is derived from the pro forma and fed
 * to the pure waterfall engine via `cashflow_override`. Only promote-specific assumptions
 * (hurdles, promote %s, RJourney co-invest, fees) are entered here.
 *
 * Until a acquisition has a computed pro forma (the projection engine is deferred — §14 A-1..A-4), the
 * tab falls back to editable return-case assumptions so the promote is still usable per acquisition;
 * it switches to pro-forma-fed automatically once the pro forma produces cash flows.
 *
 * Presentational; the calculation lives server-side (usePromoteWaterfall). No browser storage.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  useAcquisition,
  useProforma,
  useProformaInputs,
  usePromoteWaterfall,
  useSaveProformaInputs,
  useSaveWaterfallTiers,
  useWaterfallTiers,
} from "../../api/hooks";
import type { Schemas } from "../../api/client";
import { fmtMult, fmtPct, fmtUsd } from "../../lib/format";

type PromoteRequest = Schemas["PromoteRequest"];
type ProformaResults = Schemas["ProformaResults"];

/** Promote-specific assumptions — the only inputs entered on this tab. */
type PromoteInputs = {
  start_date: string;
  acquisition_fee_pct: number;
  mgmt_fee_pct: number;
  rjourney_coinvest_pct: number;
  hurdles: number[];
  promotes: number[];
};

/** Return-case assumptions — used only as the fallback when there is no pro forma. */
type ReturnCase = {
  equity: number;
  yr1_distribution_pct: number;
  distribution_growth: number;
  exit: { cap_rate: number; base_value: number; income_yield: number };
};

const PROMOTE_DEFAULTS: PromoteInputs = {
  start_date: "2025-12-31",
  acquisition_fee_pct: 0,
  mgmt_fee_pct: 0,
  rjourney_coinvest_pct: 0.1,
  hurdles: [0.08, 0.15, 0.2, 0.2],
  promotes: [0.1, 0.2, 0.3, 0.3],
};

const RETURN_CASE_DEFAULTS: ReturnCase = {
  equity: 150000000,
  yr1_distribution_pct: 0.05,
  distribution_growth: 0.05,
  exit: { cap_rate: 0.05, base_value: 300000000, income_yield: 0.07 },
};

const DEFAULT_HOLD_YEARS = 5;

function num(v: unknown): number {
  return Number(v) || 0;
}

/**
 * Derive the acquisition-level equity cash-flow stream from a pro forma:
 * `[-equity_basis, levered_cf₁ … levered_cfₙ]`, with the net exit proceeds added to the final
 * year. Returns null when the pro forma has no usable cash flows yet (so we fall back).
 */
function streamFromProforma(pf: ProformaResults | undefined): number[] | null {
  if (!pf) return null;
  const years = [...(pf.years ?? [])].sort((a, b) => (a.yr ?? 0) - (b.yr ?? 0));
  const equityBasis = pf.equity_basis;
  if (years.length === 0 || equityBasis == null) return null;
  const stream = [-num(equityBasis), ...years.map((y) => num(y.levered_cf))];
  stream[stream.length - 1] += num(pf.exit?.net_proceeds);
  return stream;
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

export function PromoteTab({ acquisitionId }: { acquisitionId: string }) {
  const { data: acquisition } = useAcquisition(acquisitionId);
  const { data: proforma, isLoading: pfLoading } = useProforma(acquisitionId);
  const [inputs, setInputs] = useState<PromoteInputs>(PROMOTE_DEFAULTS);
  const [returnCase, setReturnCase] = useState<ReturnCase>(RETURN_CASE_DEFAULTS);
  const calc = usePromoteWaterfall();
  const timer = useRef<ReturnType<typeof setTimeout>>();

  // Persisted promote terms: co-invest / fees / start date live on the pro-forma inputs (the
  // canonical store); hurdles / promotes in waterfall_tiers. Load to seed the form, save to persist.
  const { data: savedInputs } = useProformaInputs(acquisitionId);
  const { data: savedTiers } = useWaterfallTiers(acquisitionId);
  const saveInputs = useSaveProformaInputs(acquisitionId);
  const saveTiers = useSaveWaterfallTiers(acquisitionId);

  // Seed the editable terms from the persisted store; fall back to the defaults until saved.
  useEffect(() => {
    setInputs((prev) => {
      const next = { ...prev };
      if (savedInputs) {
        if (savedInputs.start_date != null) next.start_date = String(savedInputs.start_date);
        if (savedInputs.acquisition_fee_pct != null)
          next.acquisition_fee_pct = Number(savedInputs.acquisition_fee_pct);
        if (savedInputs.mgmt_fee_pct != null) next.mgmt_fee_pct = Number(savedInputs.mgmt_fee_pct);
        if (savedInputs.rjourney_coinvest_pct != null)
          next.rjourney_coinvest_pct = Number(savedInputs.rjourney_coinvest_pct);
      }
      if (savedTiers && savedTiers.length > 0) {
        next.hurdles = savedTiers.map((t) => Number(t.irr_floor ?? 0));
        next.promotes = savedTiers.map((t) => Number(t.gp_split ?? 0));
      }
      return next;
    });
  }, [savedInputs, savedTiers]);

  const savePending = saveInputs.isPending || saveTiers.isPending;
  const saveError = saveInputs.isError || saveTiers.isError;
  const saveSucceeded = saveInputs.isSuccess && saveTiers.isSuccess && !savePending;
  const onSavePromote = () => {
    saveInputs.mutate({
      rjourney_coinvest_pct: inputs.rjourney_coinvest_pct,
      acquisition_fee_pct: inputs.acquisition_fee_pct,
      mgmt_fee_pct: inputs.mgmt_fee_pct,
      start_date: inputs.start_date,
    });
    saveTiers.mutate({ hurdles: inputs.hurdles, promotes: inputs.promotes });
  };

  const dealName = acquisition?.metadata.name ?? acquisitionId;
  const sourcedStream = useMemo(() => streamFromProforma(proforma), [proforma]);
  const sourced = sourcedStream != null;
  const holdYears = sourcedStream ? sourcedStream.length - 1 : DEFAULT_HOLD_YEARS;

  // Build the engine request: promote-specific inputs always; cash flows from the pro forma
  // when present (cashflow_override), else from the editable return case.
  const request = useMemo<PromoteRequest>(() => {
    // Debt lives on the pro forma now. Derive LTV from the purchase price (entered on
    // Underwriting) + the pro-forma equity so the engine reproduces the real purchase price for
    // the acquisition fee + display — no debt input on this tab, engine unchanged.
    const purchasePrice = num(
      acquisition?.metadata.purchase_price ?? acquisition?.metadata.ask_price ?? 0,
    );
    const equity = sourcedStream ? -sourcedStream[0] : returnCase.equity;
    const ltv =
      sourcedStream && purchasePrice > 0 && equity < purchasePrice ? 1 - equity / purchasePrice : 0;
    return {
      acquisition_name: dealName,
      start_date: inputs.start_date,
      hold_years: holdYears,
      ltv,
      acquisition_fee_pct: inputs.acquisition_fee_pct,
      mgmt_fee_pct: inputs.mgmt_fee_pct,
      rjourney_coinvest_pct: inputs.rjourney_coinvest_pct,
      hurdles: inputs.hurdles,
      promotes: inputs.promotes,
      equity,
      // Return-case fields are ignored when cashflow_override is set, but the contract requires
      // them — send the (defaulted/edited) values either way.
      yr1_distribution_pct: returnCase.yr1_distribution_pct,
      distribution_growth: returnCase.distribution_growth,
      exit: returnCase.exit,
      cashflow_override: sourcedStream ?? null,
    };
  }, [acquisition, dealName, inputs, returnCase, sourcedStream, holdYears]);

  // Live recalc: debounce edits, then POST. Runs on mount and whenever inputs/pro forma change.
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => calc.mutate(request), 350);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request]);

  const setI = (patch: Partial<PromoteInputs>) => setInputs((f) => ({ ...f, ...patch }));
  const setR = (patch: Partial<ReturnCase>) => setReturnCase((f) => ({ ...f, ...patch }));
  const partnerPct = 1 - num(inputs.rjourney_coinvest_pct);
  const r = calc.data;

  return (
    <div className="space-y-4">
      <p className="text-sm opacity-70">
        Acquisition-by-acquisition JV returns for <span className="font-medium">{dealName}</span> —
        IRR hurdles &amp; promote splits. Edit any input; results recalculate live.
      </p>

      {/* Source-of-cash-flows banner: pro-forma-fed vs. interim return case. */}
      {sourced ? (
        <p className="rounded border border-brand/20 bg-brand/5 p-2 text-xs">
          Cash flows are sourced from this acquisition&apos;s{" "}
          <span className="font-medium">pro forma</span> ({holdYears}-year hold). Edit the pro forma
          to change them; only promote assumptions are entered here.
        </p>
      ) : (
        <p className="rounded border border-accent/40 bg-accent/10 p-2 text-xs text-accent-ink">
          No pro forma for this acquisition yet — using editable return-case assumptions. Once the
          pro forma produces cash flows, this tab switches to them automatically.
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,360px)_1fr]">
        {/* ── Inputs ───────────────────────────────────────── */}
        <div className="space-y-3">
          <Panel title="Acquisition setup">
            <label className="flex flex-col gap-1 text-xs">
              <span className="opacity-70">Start date</span>
              <input
                type="date"
                aria-label="Start date"
                value={String(inputs.start_date)}
                onChange={(e) => setI({ start_date: e.target.value })}
                className="rounded border border-brand/20 bg-surface px-2 py-1 font-figure text-sm focus:outline-none focus:ring-2 focus:ring-accent"
              />
            </label>
            <Field
              label="Acquisition fee"
              pct
              value={num(inputs.acquisition_fee_pct)}
              onChange={(n) => setI({ acquisition_fee_pct: n })}
            />
            <Field
              label="Mgmt fee / yr"
              pct
              value={num(inputs.mgmt_fee_pct)}
              onChange={(n) => setI({ mgmt_fee_pct: n })}
            />
          </Panel>

          <Panel title="Equity split">
            <Field
              label="RJourney co-invest"
              pct
              value={num(inputs.rjourney_coinvest_pct)}
              onChange={(n) => setI({ rjourney_coinvest_pct: n })}
            />
            <label className="flex flex-col gap-1 text-xs">
              <span className="opacity-70">Partner equity (%)</span>
              <output className="rounded border border-brand/10 bg-surface/50 px-2 py-1 font-figure text-sm">
                {fmtPct(partnerPct)}
              </output>
            </label>
          </Panel>

          {/* Return case + exit: only the interim fallback (no pro forma). */}
          {!sourced && (
            <>
              <Panel title="Return case (no pro forma yet)">
                <Field
                  label="Total equity"
                  money
                  value={num(returnCase.equity)}
                  onChange={(n) => setR({ equity: n })}
                />
                <Field
                  label="Year-1 distribution"
                  pct
                  value={num(returnCase.yr1_distribution_pct)}
                  onChange={(n) => setR({ yr1_distribution_pct: n })}
                />
                <Field
                  label="Distribution growth"
                  pct
                  value={num(returnCase.distribution_growth)}
                  onChange={(n) => setR({ distribution_growth: n })}
                />
              </Panel>
              <Panel title="Exit (year 5 reversion)">
                <Field
                  label="Exit cap rate"
                  pct
                  value={returnCase.exit.cap_rate}
                  onChange={(n) => setR({ exit: { ...returnCase.exit, cap_rate: n } })}
                />
                <Field
                  label="Income yield"
                  pct
                  value={returnCase.exit.income_yield}
                  onChange={(n) => setR({ exit: { ...returnCase.exit, income_yield: n } })}
                />
                <Field
                  label="Reversion base value"
                  money
                  value={returnCase.exit.base_value}
                  onChange={(n) => setR({ exit: { ...returnCase.exit, base_value: n } })}
                />
              </Panel>
            </>
          )}

          <Panel title="Hurdles & promotes">
            {inputs.hurdles.map((h, i) => (
              <Field
                key={`h${i}`}
                label={`Hurdle ${i + 1}`}
                pct
                value={h}
                onChange={(n) => setI({ hurdles: inputs.hurdles.map((x, j) => (j === i ? n : x)) })}
              />
            ))}
            {inputs.promotes.map((p, i) => (
              <Field
                key={`p${i}`}
                label={`Promote ${i + 1}`}
                pct
                value={p}
                onChange={(n) =>
                  setI({ promotes: inputs.promotes.map((x, j) => (j === i ? n : x)) })
                }
              />
            ))}
          </Panel>

          {/* Persist the promote terms so they drive the saved headline returns (the panels above
              are a live preview; saving makes them stick across reloads + feed the pipeline). */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={savePending}
              onClick={onSavePromote}
              className="rounded bg-brand px-3 py-1.5 text-sm text-surface disabled:opacity-50"
            >
              {savePending ? "Saving…" : "Save promote terms"}
            </button>
            {saveSucceeded && (
              <span className="text-xs opacity-60">Saved · drives the headline returns</span>
            )}
            {saveError && (
              <span role="alert" className="text-sm text-danger">
                Couldn&apos;t save — check the inputs.
              </span>
            )}
          </div>
        </div>

        {/* ── Outputs ──────────────────────────────────────── */}
        <div className="space-y-4">
          {pfLoading && <p className="text-sm opacity-70">Loading pro forma…</p>}
          {calc.isError && (
            <p role="alert" className="rounded border border-danger/30 p-3 text-sm text-danger">
              Couldn&apos;t calculate — check the inputs.
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
    </div>
  );
}

type Result = Schemas["PromoteResponse"];

function ReturnsSummary({ result }: { result: Result }) {
  const cols: [string, Schemas["PositionOut"]][] = [
    ["Partner Equity", result.partner],
    ["RJourney Equity", result.rjourney],
    ["Acquisition-Level", result.acquisition],
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
