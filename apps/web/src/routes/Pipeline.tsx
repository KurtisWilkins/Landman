/**
 * Pipeline dashboard (design doc §5.8, §6): phase buckets with deal counts and rolled-up
 * acquisition dollars, then deal lists with blocker chips. Mobile-first.
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { usePipeline } from "../api/hooks";
import { NewDealForm } from "./NewDealForm";
import type { components } from "../api/types";
import type { Schemas } from "../api/client";

type Phase = components["schemas"]["Phase"];
type DealSummary = Schemas["DealSummary"];

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

function rollup(deals: DealSummary[], phase: Phase): { count: number; dollars: number } {
  const inPhase = deals.filter((d) => d.current_phase === phase);
  const dollars = inPhase.reduce((acc, d) => acc + Number(d.ask_price ?? 0), 0);
  return { count: inPhase.length, dollars };
}

export function Pipeline() {
  const { data, isLoading, error } = usePipeline();
  const deals = data ?? [];
  const navigate = useNavigate();
  const [showForm, setShowForm] = useState(false);

  return (
    <section>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Pipeline</h1>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="rounded bg-forest px-3 py-1.5 text-sm text-bone"
        >
          {showForm ? "Close" : "New deal"}
        </button>
      </div>

      {showForm && (
        <NewDealForm
          onCreated={(dealId) => {
            setShowForm(false);
            navigate(`/deals/${dealId}`);
          }}
          onCancel={() => setShowForm(false)}
        />
      )}

      {isLoading && <p className="mt-4 text-sm opacity-70">Loading…</p>}
      {error && (
        <p className="mt-4 rounded border border-forest/20 p-3 text-sm opacity-80">
          The pipeline list isn’t available yet (the <code>/deals</code> endpoint lands with the
          deals/pipeline backend). The screen is wired to the contract and will populate once it’s
          implemented.
        </p>
      )}

      {!isLoading && !error && (
        <>
          {/* Phase buckets */}
          <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-5">
            {PHASES.map((p) => {
              const { count, dollars } = rollup(deals, p.key);
              return (
                <div key={p.key} className="rounded-lg border border-forest/15 p-3">
                  <div className="text-xs uppercase tracking-wide opacity-70">{p.label}</div>
                  <div className="mt-1 font-figure text-2xl">{count}</div>
                  <div className="font-figure text-sm opacity-80">{usd.format(dollars)}</div>
                </div>
              );
            })}
          </div>

          {/* Deal lists */}
          {deals.length === 0 ? (
            <p className="mt-6 text-sm opacity-70">No deals yet.</p>
          ) : (
            <ul className="mt-6 divide-y divide-forest/10">
              {deals.map((d) => (
                <li key={d.deal_id}>
                  <Link
                    to={`/deals/${d.deal_id}`}
                    className="flex items-center justify-between py-3 hover:bg-bone focus:outline-none focus:ring-2 focus:ring-brass-accent"
                  >
                    <div>
                      <div className="font-medium">{d.name}</div>
                      <div className="text-xs opacity-70">
                        {[d.city, d.state].filter(Boolean).join(", ")} · {d.property_type}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {d.blocking_gate_count > 0 && (
                        <span className="rounded-full bg-brass-accent/20 px-2 py-0.5 text-xs text-forest-ink">
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
