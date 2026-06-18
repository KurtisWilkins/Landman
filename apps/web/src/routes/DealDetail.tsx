/**
 * Deal detail (design doc §5.8): header with phase progress, then tabs — Pro forma, Comps,
 * Gates, GL/Docs. Tab state is local UI state (no browser storage). The assembled deal
 * document is fetched for the header; individual tabs fetch their own slice.
 */
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useDeal } from "../api/hooks";
import { CompsTab } from "./deal/CompsTab";
import { GLDocsTab } from "./deal/GLDocsTab";
import { GatesTab } from "./deal/GatesTab";
import { MarketTab } from "./deal/MarketTab";
import { ProformaTab } from "./deal/ProformaTab";

const TABS = ["Pro forma", "Market", "Comps", "Gates", "GL / Docs"] as const;
type Tab = (typeof TABS)[number];

export function DealDetail() {
  const { dealId = "" } = useParams();
  const [tab, setTab] = useState<Tab>("Pro forma");
  const { data: deal } = useDeal(dealId);

  return (
    <section>
      <header>
        <h1 className="text-2xl font-semibold">{deal?.metadata.name ?? dealId}</h1>
        <p className="mt-1 text-xs uppercase tracking-wide opacity-60">
          {deal?.metadata.current_phase ?? "phase —"} · {deal?.metadata.status ?? ""}
        </p>
      </header>

      <div
        role="tablist"
        aria-label="Deal sections"
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
        {tab === "Pro forma" && <ProformaTab dealId={dealId} />}
        {tab === "Market" && <MarketTab dealId={dealId} />}
        {tab === "Comps" && <CompsTab dealId={dealId} />}
        {tab === "Gates" && <GatesTab />}
        {tab === "GL / Docs" && <GLDocsTab dealId={dealId} />}
      </div>
    </section>
  );
}
