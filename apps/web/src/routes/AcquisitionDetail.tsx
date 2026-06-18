/**
 * Acquisition detail (design doc §5.8): header with phase progress, then tabs — Pro forma, Comps,
 * Gates, GL/Docs. Tab state is local UI state (no browser storage). The assembled acquisition
 * document is fetched for the header; individual tabs fetch their own slice.
 */
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useAcquisition } from "../api/hooks";
import { CompsTab } from "./acquisition/CompsTab";
import { GLDocsTab } from "./acquisition/GLDocsTab";
import { GatesTab } from "./acquisition/GatesTab";
import { MarketTab } from "./acquisition/MarketTab";
import { ProformaTab } from "./acquisition/ProformaTab";
import { PromoteTab } from "./acquisition/PromoteTab";

const TABS = ["Pro forma", "Promote", "Market", "Comps", "Gates", "GL / Docs"] as const;
type Tab = (typeof TABS)[number];

export function AcquisitionDetail() {
  const { acquisitionId = "" } = useParams();
  const [tab, setTab] = useState<Tab>("Pro forma");
  const { data: acquisition } = useAcquisition(acquisitionId);

  return (
    <section>
      <header>
        <h1 className="text-2xl font-semibold">{acquisition?.metadata.name ?? acquisitionId}</h1>
        <p className="mt-1 text-xs uppercase tracking-wide opacity-60">
          {acquisition?.metadata.current_phase ?? "phase —"} · {acquisition?.metadata.status ?? ""}
        </p>
      </header>

      <div
        role="tablist"
        aria-label="Acquisition sections"
        className="mt-4 flex gap-1 border-b border-brand/15"
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
