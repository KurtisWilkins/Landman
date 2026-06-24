/**
 * Pipeline dashboard (design doc §5.8, §6): phase buckets with acquisition counts and rolled-up
 * acquisition dollars, then acquisition lists with blocker chips. Mobile-first. A ⋯ menu on each
 * row archives a deal (soft-delete — recoverable, never hard-deleted); the "Archived" toggle shows
 * the archived deals with a Restore action.
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useArchiveAcquisition, usePipeline, useRestoreAcquisition } from "../api/hooks";
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
  const [archived, setArchived] = useState(false);
  const { data, isLoading, error } = usePipeline({ archived });
  const acquisitions = data ?? [];
  const navigate = useNavigate();
  const [showForm, setShowForm] = useState(false);
  const archive = useArchiveAcquisition();
  const restore = useRestoreAcquisition();
  const pending = archive.isPending || restore.isPending;

  const onArchive = (d: AcquisitionSummary) => {
    if (
      window.confirm(
        `Archive “${d.name}”? It leaves the pipeline but stays fully recoverable — nothing is deleted.`,
      )
    ) {
      archive.mutate(d.acquisition_id);
    }
  };

  return (
    <section>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{archived ? "Archived deals" : "Pipeline"}</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setArchived((v) => !v)}
            className="rounded border border-brand/30 px-3 py-1.5 text-sm"
          >
            {archived ? "← Active pipeline" : "Archived"}
          </button>
          {!archived && (
            <button
              onClick={() => setShowForm((v) => !v)}
              className="rounded bg-brand px-3 py-1.5 text-sm text-surface"
            >
              {showForm ? "Close" : "New acquisition"}
            </button>
          )}
        </div>
      </div>

      {showForm && !archived && (
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
          {!archived && (
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
          )}

          {acquisitions.length === 0 ? (
            <p className="mt-6 text-sm opacity-70">
              {archived ? "No archived deals." : "No acquisitions yet."}
            </p>
          ) : (
            <div className="mt-6 overflow-x-auto">
              <table className="min-w-[860px] w-full border-collapse text-sm">
                <thead>
                  <tr className="text-left">
                    <th className="px-2 py-2 font-medium">Acquisition</th>
                    <th className="px-2 py-2 font-medium">Phase</th>
                    <th className="px-2 py-2 text-right font-medium">Price</th>
                    <th className="px-2 py-2 text-right font-medium">Partner IRR / MOIC</th>
                    <th className="px-2 py-2 text-right font-medium">RJourney IRR / MOIC</th>
                    <th className="px-2 py-2 text-right font-medium">Deal-Level IRR / MOIC</th>
                    <th className="px-2 py-2 text-right font-medium">Promote</th>
                    <th className="px-2 py-2" />
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
                      <td className="px-2 py-2 text-right">
                        <RowMenu
                          archived={archived}
                          pending={pending}
                          onArchive={() => onArchive(d)}
                          onRestore={() => restore.mutate(d.acquisition_id)}
                        />
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

/** The per-row three-dot menu: Archive (active) or Restore (archived). */
function RowMenu({
  archived,
  pending,
  onArchive,
  onRestore,
}: {
  archived: boolean;
  pending: boolean;
  onArchive: () => void;
  onRestore: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative inline-block text-left">
      <button
        type="button"
        aria-label="Deal actions"
        onClick={() => setOpen((v) => !v)}
        className="rounded px-2 py-1 text-lg leading-none text-ink/50 hover:bg-brand/5"
      >
        ⋯
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-20 mt-1 w-36 rounded border border-brand/20 bg-surface py-1 text-left text-sm shadow-lg">
            {archived ? (
              <button
                type="button"
                disabled={pending}
                onClick={() => {
                  setOpen(false);
                  onRestore();
                }}
                className="block w-full px-3 py-1.5 text-left hover:bg-brand/5 disabled:opacity-50"
              >
                Restore to pipeline
              </button>
            ) : (
              <button
                type="button"
                disabled={pending}
                onClick={() => {
                  setOpen(false);
                  onArchive();
                }}
                className="block w-full px-3 py-1.5 text-left text-danger hover:bg-brand/5 disabled:opacity-50"
              >
                Archive
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
