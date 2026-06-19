/**
 * Pro forma tab (design doc §5.5): the acquisition's editable assumptions — stabilized NOI,
 * growth, exit, and **debt** (debt is sized here, not on the promote) — drive a server-side
 * recompute. The purchase price flows in from Underwriting; the result is the 5-yr levered cash
 * flow + equity required + returns, and the equity stream the promote consumes.
 *
 * Presentational; the calculation lives server-side. No browser storage.
 */
import { useEffect, useState } from "react";
import { useProforma, useProformaInputs, useSaveProformaInputs } from "../../api/hooks";
import type { Schemas } from "../../api/client";
import { fmtMult, fmtPct, fmtUsd } from "../../lib/format";

type Inputs = Schemas["ProformaInputs"];

// Best-guess starting defaults (configurable in Settings later). Stabilized revenue/opex start
// blank — they come from the underwriter's normalized P&L and must be entered.
const DEFAULTS: Inputs = {
  stabilized_revenue: null,
  stabilized_opex: null,
  noi_growth: 0.03,
  exit_cap: 0.07,
  ltv: 0.65,
  loan_rate: 0.065,
  amort_months: 360,
  io_years: 0,
  selling_cost_rate: 0.02,
  capex_reserve_rate: 0,
  hold_years: 5,
};

function num(v: unknown): number {
  return Number(v) || 0;
}

function Field({
  label,
  value,
  onChange,
  kind,
}: {
  label: string;
  value: number | string | null;
  onChange: (n: number) => void;
  kind: "money" | "pct" | "int";
}) {
  const shown = value == null ? "" : kind === "pct" ? num(value) * 100 : num(value);
  return (
    <label className="flex flex-col gap-1 text-xs">
      <span className="opacity-70">
        {label}
        {kind === "pct" ? " (%)" : kind === "money" ? " ($)" : ""}
      </span>
      <input
        type="number"
        aria-label={label}
        value={shown}
        step={kind === "pct" ? 0.25 : kind === "money" ? 100000 : 1}
        onChange={(e) => onChange(kind === "pct" ? num(e.target.value) / 100 : num(e.target.value))}
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

/** Drop null entries so saved values override defaults but absent ones keep the default. */
function stripNulls(obj: Inputs): Partial<Inputs> {
  return Object.fromEntries(
    Object.entries(obj).filter(([, v]) => v !== null && v !== undefined),
  ) as Partial<Inputs>;
}

export function ProformaTab({ acquisitionId }: { acquisitionId: string }) {
  const { data: saved } = useProformaInputs(acquisitionId);
  const { data: results } = useProforma(acquisitionId);
  const save = useSaveProformaInputs(acquisitionId);
  const [form, setForm] = useState<Inputs>(DEFAULTS);

  // Seed the form from saved inputs once they load (falling back to the best-guess defaults).
  useEffect(() => {
    if (saved) setForm({ ...DEFAULTS, ...stripNulls(saved) });
  }, [saved]);

  const set = (patch: Partial<Inputs>) => setForm((f) => ({ ...f, ...patch }));
  const years = results?.years ?? [];
  const rows: { key: keyof (typeof years)[number]; label: string }[] = [
    { key: "revenue", label: "Revenue" },
    { key: "opex", label: "OpEx" },
    { key: "noi", label: "NOI" },
    { key: "debt_service", label: "Debt Service" },
    { key: "capex", label: "CapEx reserve" },
    { key: "levered_cf", label: "Levered CF" },
  ];

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,340px)_1fr]">
      {/* ── Assumptions ──────────────────────────────────── */}
      <div className="space-y-3">
        <p className="text-xs opacity-70">
          Debt is sized here from the purchase price (entered on Underwriting). Edit and save to
          recompute; the promote uses the resulting equity cash flows.
        </p>
        <Panel title="Stabilized NOI (year 1)">
          <Field
            label="Revenue"
            kind="money"
            value={form.stabilized_revenue ?? null}
            onChange={(n) => set({ stabilized_revenue: n })}
          />
          <Field
            label="OpEx"
            kind="money"
            value={form.stabilized_opex ?? null}
            onChange={(n) => set({ stabilized_opex: n })}
          />
          <Field
            label="NOI growth"
            kind="pct"
            value={form.noi_growth ?? null}
            onChange={(n) => set({ noi_growth: n })}
          />
          <Field
            label="Hold (years)"
            kind="int"
            value={form.hold_years ?? null}
            onChange={(n) => set({ hold_years: n })}
          />
        </Panel>
        <Panel title="Debt">
          <Field
            label="LTV"
            kind="pct"
            value={form.ltv ?? null}
            onChange={(n) => set({ ltv: n })}
          />
          <Field
            label="Rate"
            kind="pct"
            value={form.loan_rate ?? null}
            onChange={(n) => set({ loan_rate: n })}
          />
          <Field
            label="Amortization (months)"
            kind="int"
            value={form.amort_months ?? null}
            onChange={(n) => set({ amort_months: n })}
          />
          <Field
            label="Interest-only (years)"
            kind="int"
            value={form.io_years ?? null}
            onChange={(n) => set({ io_years: n })}
          />
        </Panel>
        <Panel title="Exit">
          <Field
            label="Exit cap"
            kind="pct"
            value={form.exit_cap ?? null}
            onChange={(n) => set({ exit_cap: n })}
          />
          <Field
            label="Selling cost"
            kind="pct"
            value={form.selling_cost_rate ?? null}
            onChange={(n) => set({ selling_cost_rate: n })}
          />
          <Field
            label="CapEx reserve"
            kind="pct"
            value={form.capex_reserve_rate ?? null}
            onChange={(n) => set({ capex_reserve_rate: n })}
          />
        </Panel>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={save.isPending}
            onClick={() => save.mutate(form)}
            className="rounded bg-brand px-3 py-1.5 text-sm text-surface disabled:opacity-50"
          >
            {save.isPending ? "Recomputing…" : "Save & recompute"}
          </button>
          {save.isError && (
            <span role="alert" className="text-sm text-danger">
              Couldn&apos;t recompute — check the inputs.
            </span>
          )}
        </div>
      </div>

      {/* ── Results ──────────────────────────────────────── */}
      <div>
        {years.length === 0 ? (
          <p className="rounded border border-brand/20 p-3 text-sm opacity-80">
            Enter the stabilized NOI + debt assumptions and save to compute the pro forma. (A
            purchase price on the Underwriting tab is required.)
          </p>
        ) : (
          <>
            <dl className="mb-4 flex flex-wrap gap-4">
              <div>
                <dt className="text-xs uppercase opacity-60">Levered IRR</dt>
                <dd className="font-figure text-lg">{fmtPct(results?.levered_irr)}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase opacity-60">Equity multiple</dt>
                <dd className="font-figure text-lg">{fmtMult(results?.equity_multiple)}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase opacity-60">Equity required</dt>
                <dd className="font-figure text-lg">{fmtUsd(results?.equity_basis)}</dd>
              </div>
            </dl>
            <div className="overflow-x-auto">
              <table className="min-w-[640px] border-collapse text-sm">
                <thead>
                  <tr>
                    <th className="px-2 py-1 text-left font-medium">Line</th>
                    {years.map((y) => (
                      <th key={y.yr} className="px-2 py-1 text-right font-medium">
                        Yr {y.yr}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="font-figure">
                  {rows.map((r) => (
                    <tr key={r.key} className="border-t border-brand/10">
                      <td className="px-2 py-1">{r.label}</td>
                      {years.map((y) => (
                        <td key={y.yr} className="px-2 py-1 text-right">
                          {fmtUsd(y[r.key] as string | number | null)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
