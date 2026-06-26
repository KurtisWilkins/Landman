/**
 * Acquisition detail (design doc §5.8): an acquisition summary header on top, then the layered
 * workspace tabs in flow order — Underwriting → Pro forma → Promote — followed by Market, Comps,
 * Gates, GL/Docs. Tab state is local UI state (no browser storage). The assembled acquisition
 * document feeds the header; individual tabs fetch their own slice.
 */
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useAcquisition, useAcquisitionReturns } from "../api/hooks";
import type { Schemas } from "../api/client";
import { fmtMult, fmtPct, fmtUsd } from "../lib/format";
import { BudgetTab } from "./acquisition/BudgetTab";
import { CompsTab } from "./acquisition/CompsTab";
import { GLDocsTab } from "./acquisition/GLDocsTab";
import { GatesTab } from "./acquisition/GatesTab";
import { LaborTab } from "./acquisition/LaborTab";
import { MarketTab } from "./acquisition/MarketTab";
import { ProformaTab } from "./acquisition/ProformaTab";
import { PromoteTab } from "./acquisition/PromoteTab";
import { UnderwritingTab } from "./acquisition/UnderwritingTab";

const TABS = [
  "Underwriting",
  "Budget",
  "Labor",
  "Pro forma",
  "Promote",
  "Market",
  "Comps",
  "Gates",
  "GL / Docs",
] as const;
type Tab = (typeof TABS)[number];

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide opacity-60">{label}</div>
      <div className="mt-0.5 font-figure text-sm">{value}</div>
    </div>
  );
}

function prettyType(v: string | undefined): string {
  return v ? v.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : "—";
}

/** IRR · MOIC pair, or "—" when neither is computed yet. */
function irrMoic(
  irr: string | number | null | undefined,
  moic: string | number | null | undefined,
) {
  return irr == null && moic == null ? "—" : `${fmtPct(irr)} · ${fmtMult(moic)}`;
}

/** Acquisition summary header — key facts + headline returns (filled once a pro forma exists). */
function SummaryHeader({
  m,
  r,
}: {
  m: Schemas["AcquisitionMetadata"] | undefined;
  r: Schemas["AcquisitionReturns"] | undefined;
}) {
  const price = m?.purchase_price ?? m?.ask_price ?? null;
  const location = [m?.address?.city, m?.address?.state].filter(Boolean).join(", ") || "—";
  const loanLtv = r?.loan_amount == null ? "—" : `${fmtUsd(r.loan_amount)} (${fmtPct(r.ltv)})`;
  return (
    <header className="rounded-lg border border-brand/15 p-4">
      <h1 className="text-2xl font-semibold">{m?.name ?? "—"}</h1>
      <p className="mt-1 text-xs uppercase tracking-wide opacity-60">
        {m?.current_phase ?? "phase —"} · {m?.status ?? ""}
      </p>
      <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        <Fact label="Location" value={location} />
        <Fact label="Type" value={prettyType(m?.property_type)} />
        <Fact label="Sites / units" value={m?.site_count ?? "—"} />
        <Fact label="Purchase price" value={fmtUsd(price)} />
        <Fact label="Price / site" value={fmtUsd(m?.price_per_site)} />
        <Fact label="Going-in cap" value={r?.going_in_cap == null ? "—" : fmtPct(r.going_in_cap)} />
        <Fact label="Loan / LTV" value={loanLtv} />
        <Fact label="Hold" value={r?.hold_years == null ? "—" : `${r.hold_years} yr`} />
      </dl>
      <dl className="mt-3 grid grid-cols-3 gap-3 border-t border-brand/10 pt-3">
        <Fact label="Partner IRR / MOIC" value={irrMoic(r?.partner_irr, r?.partner_moic)} />
        <Fact label="RJourney IRR / MOIC" value={irrMoic(r?.rjourney_irr, r?.rjourney_moic)} />
        <Fact label="Deal-Level IRR / MOIC" value={irrMoic(r?.deal_irr, r?.deal_moic)} />
      </dl>
    </header>
  );
}

export function AcquisitionDetail() {
  const { acquisitionId = "" } = useParams();
  const [tab, setTab] = useState<Tab>("Underwriting");
  const { data: acquisition } = useAcquisition(acquisitionId);
  const { data: returns } = useAcquisitionReturns(acquisitionId);

  return (
    <section>
      <SummaryHeader m={acquisition?.metadata} r={returns} />

      <div
        role="tablist"
        aria-label="Acquisition sections"
        className="mt-4 flex flex-wrap gap-1 border-b border-brand/15"
      >
        {TABS.map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${
              tab === t ? "border-brand font-medium" : "border-transparent opacity-70"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="mt-4">
        {tab === "Underwriting" && <UnderwritingTab acquisitionId={acquisitionId} />}
        {tab === "Budget" && <BudgetTab acquisitionId={acquisitionId} />}
        {tab === "Labor" && <LaborTab acquisitionId={acquisitionId} />}
        {tab === "Pro forma" && <ProformaTab acquisitionId={acquisitionId} />}
        {tab === "Promote" && <PromoteTab acquisitionId={acquisitionId} />}
        {tab === "Market" && <MarketTab acquisitionId={acquisitionId} />}
        {tab === "Comps" && <CompsTab acquisitionId={acquisitionId} />}
        {tab === "Gates" && <GatesTab />}
        {tab === "GL / Docs" && <GLDocsTab acquisitionId={acquisitionId} />}
      </div>
    </section>
  );
}
