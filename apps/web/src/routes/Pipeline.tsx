/**
 * Pipeline dashboard (design doc §5.8, §6): phase buckets with acquisition counts and rolled-up
 * acquisition dollars, then acquisition lists with blocker chips. Mobile-first.
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { usePipeline } from "../api/hooks";
import { NewAcquisitionForm } from "./NewAcquisitionForm";
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

          {/* Acquisition lists */}
          {acquisitions.length === 0 ? (
            <p className="mt-6 text-sm opacity-70">No acquisitions yet.</p>
          ) : (
            <ul className="mt-6 divide-y divide-brand/10">
              {acquisitions.map((d) => (
                <li key={d.acquisition_id}>
                  <Link
                    to={`/acquisitions/${d.acquisition_id}`}
                    className="flex items-center justify-between py-3 hover:bg-surface focus:outline-none focus:ring-2 focus:ring-accent"
                  >
                    <div>
                      <div className="font-medium">{d.name}</div>
                      <div className="text-xs opacity-70">
                        {[d.city, d.state].filter(Boolean).join(", ")} · {d.property_type}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {d.blocking_gate_count > 0 && (
                        <span className="rounded-full bg-accent/20 px-2 py-0.5 text-xs text-ink">
                          {d.blocking_gate_count} blocking
                        </span>
                      )}
                      <span className="font-figure text-sm">
                        {usd.format(Number(d.ask_price ?? 0))}
                      </span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
