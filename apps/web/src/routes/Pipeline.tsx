/**
 * Pipeline dashboard (design doc §5.8, §6): phase buckets with acquisition counts and rolled-up
 * acquisition dollars, then acquisition lists with blocker chips. Mobile-first.
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { usePipeline } from "../api/hooks";
import { NewAcquisitionForm } from "./NewAcquisitionForm";
import { fmtMult, fmtPct, fmtUsd } from "../lib/format";
import type { components } from "../api/types";
import type { Schemas } from "../api/client";

type Phase = components["schemas"]["Phase"];
type AcquisitionSummary = Schemas["AcquisitionSummary"];

const PHASES: { key: Phase; label: string }[] = [
  { key: "initial_uw", label: "Initial UW" },
  { key: "loi", label: "LOI" },
  { key: "contract", label: "Contract" },
  { key: "due_diligence", label: "Due Diligence" },
  { key: "close", label: "Close" },
];

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});

function rollup(
  acquisitions: AcquisitionSummary[],
  phase: Phase,
): { count: number; dollars: number } {
  const inPhase = acquisitions.filter((d) => d.current_phase === phase);
  const dollars = inPhase.reduce((acc, d) => acc + Number(d.ask_price ?? 0), 0);
  return { count: inPhase.length, dollars };
}

/** IRR · MOIC pair, or "—" when neither is computed yet. */
function irrMoic(
  irr: string | number | null | undefined,
  moic: string | number | null | undefined,
): string {
  return irr == null && moic == null ? "—" : `${fmtPct(irr)} · ${fmtMult(moic)}`;
}

export function Pipeline() {
  const { data, isLoading, error } = usePipeline();
  const acquisitions = data ?? [];
  const navigate = useNavigate();
  const [showForm, setShowForm] = useState(false);

  return (
    <section>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Pipeline</h1>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="rounded bg-brand px-3 py-1.5 text-sm text-surface"
        >
          {showForm ? "Close" : "New acquisition"}
        </button>
      </div>

      {showForm && (
        <NewAcquisitionForm
          onCreated={(acquisitionId) => {
            setShowForm(false);
            navigate(`/acquisitions/${acquisitionId}`);
          }}
          onCancel={() => setShowForm(false)}
        />
      )}

      {isLoading && <p className="mt-4 text-sm opacity-70">Loading…</p>}
      {error && (
        <p className="mt-4 rounded border border-brand/20 p-3 text-sm opacity-80">
          The pipeline list isn’t available yet (the <code>/acquisitions</code> endpoint lands with
          the acquisitions/pipeline backend). The screen is wired to the contract and will populate
          once it’s implemented.
        </p>
      )}

      {!isLoading && !error && (
        <>
          {/* Phase buckets */}
          <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-5">
            {PHASES.map((p) => {
              const { count, dollars } = rollup(acquisitions, p.key);
              return (
                <div key={p.key} className="rounded-lg border border-brand/15 p-3">
                  <div className="text-xs uppercase tracking-wide opacity-70">{p.label}</div>
                  <div className="mt-1 font-figure text-2xl">{count}</div>
                  <div className="font-figure text-sm opacity-80">{usd.format(dollars)}</div>
                </div>
              );
            })}
          </div>

          {/* Acquisition comparison table — headline returns at a glance (#29). */}
          {acquisitions.length === 0 ? (
            <p className="mt-6 text-sm opacity-70">No acquisitions yet.</p>
          ) : (
            <div className="mt-6 overflow-x-auto">
              <table className="min-w-[820px] w-full border-collapse text-sm">
                <thead>
                  <tr className="text-left">
                    <th className="px-2 py-2 font-medium">Acquisition</th>
                    <th className="px-2 py-2 font-medium">Phase</th>
                    <th className="px-2 py-2 text-right font-medium">Price</th>
                    <th className="px-2 py-2 text-right font-medium">Partner IRR / MOIC</th>
                    <th className="px-2 py-2 text-right font-medium">RJourney IRR / MOIC</th>
                    <th className="px-2 py-2 text-right font-medium">Deal-Level IRR / MOIC</th>
                    <th className="px-2 py-2 text-right font-medium">Promote</th>
                  </tr>
                </thead>
                <tbody>
                  {acquisitions.map((d) => (
                    <tr
                      key={d.acquisition_id}
                      className="border-t border-brand/10 hover:bg-surface"
                    >
                      <td className="px-2 py-2">
                        <Link
                          to={`/acquisitions/${d.acquisition_id}`}
                          className="font-medium text-brand hover:underline focus:outline-none focus:ring-2 focus:ring-accent"
                        >
                          {d.name}
                        </Link>
                        <div className="text-xs opacity-70">
                          {[d.city, d.state].filter(Boolean).join(", ")} · {d.property_type}
                          {d.blocking_gate_count > 0 ? ` · ${d.blocking_gate_count} blocking` : ""}
                        </div>
                      </td>
                      <td className="px-2 py-2">{d.current_phase}</td>
                      <td className="px-2 py-2 text-right font-figure">
                        {usd.format(Number(d.ask_price ?? 0))}
                      </td>
                      <td className="px-2 py-2 text-right font-figure">
                        {irrMoic(d.returns?.partner_irr, d.returns?.partner_moic)}
                      </td>
                      <td className="px-2 py-2 text-right font-figure">
                        {irrMoic(d.returns?.rjourney_irr, d.returns?.rjourney_moic)}
                      </td>
                      <td className="px-2 py-2 text-right font-figure">
                        {irrMoic(d.returns?.deal_irr, d.returns?.deal_moic)}
                      </td>
                      <td className="px-2 py-2 text-right font-figure">
                        {d.returns?.promote_value == null ? "—" : fmtUsd(d.returns.promote_value)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
