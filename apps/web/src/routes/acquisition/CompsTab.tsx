/**
 * Comps tab (design doc §5.6): "Find competitors within 50 miles" of the OM address, then a
 * scatter (Recharts) you can flip between amenity × sentiment and rate × sentiment, plus a ranked
 * list with an editable nightly rate per competitor. Discovery searches OpenStreetMap (free, always
 * on) + Google (when keyed). Enrichment: an amenity score from OSM tags + sentiment from Google
 * ratings populate automatically; nightly rates are entered by hand (no free source has them); an
 * optional "✨" pulls an AI review summary (Google reviews → Claude) once both keys are set.
 */
import { useState } from "react";
import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { useComps, useDiscoverComps, useEnrichComp, useUpdateCompRate } from "../../api/hooks";
import type { Schemas } from "../../api/client";

type Comp = Schemas["CompOut"];

function n(v: unknown): number {
  return Number(v ?? 0);
}

export function CompsTab({ acquisitionId }: { acquisitionId: string }) {
  const { data, isLoading, error } = useComps(acquisitionId);
  const discover = useDiscoverComps(acquisitionId);
  const updateRate = useUpdateCompRate(acquisitionId);
  const enrich = useEnrichComp(acquisitionId);
  const [view, setView] = useState<"amenity" | "rate">("amenity");
  const comps = data?.comps ?? [];
  const searching = discover.isPending;

  const onDiscover = () => discover.mutate();
  const discoverError = discover.error instanceof Error ? discover.error.message : undefined;
  const enrichError = enrich.error instanceof Error ? enrich.error.message : undefined;

  const Toolbar = (
    <div className="flex flex-wrap items-center gap-3">
      <span className="text-sm font-medium">Competitive set — within 50 miles</span>
      <button
        type="button"
        disabled={searching}
        onClick={onDiscover}
        className="ml-auto rounded bg-brand px-3 py-1.5 text-sm text-surface disabled:opacity-50"
      >
        {searching ? "Searching…" : comps.length > 0 ? "Re-scan" : "Find competitors within 50 mi"}
      </button>
    </div>
  );

  if (isLoading) return <p className="text-sm opacity-70">Loading…</p>;

  if (error || !data) {
    return (
      <div className="space-y-4">
        {Toolbar}
        <p className="rounded border border-brand/20 p-3 text-sm opacity-80">
          Couldn’t load the comp set. Try again, or run a search.
        </p>
      </div>
    );
  }

  const xKey = view === "rate" ? "rate" : "amenity";
  const points = comps.map((c) => ({
    name: c.name,
    rate: n(c.avg_rate),
    sentiment: n(c.sentiment_score),
    amenity: c.amenity_score ?? 0,
  }));
  const ranked = [...comps].sort((a, b) => (a.amenity_rank ?? 999) - (b.amenity_rank ?? 999));

  return (
    <div className="space-y-6">
      {Toolbar}

      {discoverError && (
        <p className="rounded border border-accent/40 bg-accent/10 p-2 text-sm text-accent-ink">
          {discoverError.includes("address")
            ? "This acquisition has no locatable address yet — add the street/city/state on the property, then search."
            : discoverError}
        </p>
      )}
      {enrichError && (
        <p className="rounded border border-accent/40 bg-accent/10 p-2 text-sm text-accent-ink">
          {enrichError.includes("configured")
            ? "AI review summaries need the Google Places + Anthropic keys configured."
            : enrichError}
        </p>
      )}

      {comps.length === 0 ? (
        <p className="rounded border border-brand/20 p-3 text-sm opacity-80">
          {searching
            ? "Searching for RV parks, campgrounds, resorts, glamping sites and marinas within 50 miles…"
            : "No competitors found yet. Click “Find competitors within 50 mi” to search from the property’s address."}
        </p>
      ) : (
        <>
          <div className="flex items-center gap-2 text-xs">
            <span className="opacity-60">Plot:</span>
            {(["amenity", "rate"] as const).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setView(v)}
                className={`rounded border px-2 py-1 ${
                  view === v ? "border-brand bg-brand/10 text-brand" : "border-brand/30"
                }`}
              >
                {v === "amenity" ? "Amenity × sentiment" : "Rate × sentiment"}
              </button>
            ))}
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 8, right: 8, bottom: 24, left: 8 }}>
                <CartesianGrid strokeOpacity={0.15} />
                <XAxis
                  type="number"
                  dataKey={xKey}
                  name={view === "rate" ? "Avg rate" : "Amenity"}
                  unit={view === "rate" ? "$" : ""}
                />
                <YAxis type="number" dataKey="sentiment" name="Sentiment" domain={[0, 5]} />
                <ZAxis
                  type="number"
                  dataKey={view === "rate" ? "amenity" : "rate"}
                  range={[40, 200]}
                  name={view === "rate" ? "Amenity" : "Rate"}
                />
                <Tooltip cursor={{ strokeDasharray: "3 3" }} />
                <Scatter data={points} fill="var(--color-accent)" />
              </ScatterChart>
            </ResponsiveContainer>
          </div>

          <div>
            <div className="mb-1 grid grid-cols-[1fr_auto_auto_auto_auto] items-center gap-3 text-xs uppercase tracking-wide opacity-60">
              <span>{comps.length} competitors · ranked by amenities</span>
              <span className="text-right">Amenity</span>
              <span className="text-right">Sentiment</span>
              <span className="text-right">Dist</span>
              <span className="text-right">Rate / night</span>
            </div>
            <ol className="divide-y divide-brand/10">
              {ranked.map((c) => (
                <CompRow
                  key={c.comp_id}
                  comp={c}
                  onRate={(avgRate) => updateRate.mutate({ compId: c.comp_id, avgRate })}
                  onEnrich={() => enrich.mutate(c.comp_id)}
                  enriching={enrich.isPending}
                />
              ))}
            </ol>
          </div>
        </>
      )}
    </div>
  );
}

function CompRow({
  comp: c,
  onRate,
  onEnrich,
  enriching,
}: {
  comp: Comp;
  onRate: (avgRate: number | null) => void;
  onEnrich: () => void;
  enriching: boolean;
}) {
  const rate = c.avg_rate == null ? "" : String(n(c.avg_rate));
  return (
    <li className="grid grid-cols-[1fr_auto_auto_auto_auto] items-center gap-3 py-2 text-sm">
      <span className="flex items-center gap-2">
        <span className="font-figure opacity-60">#{c.amenity_rank ?? "—"}</span>
        <span>{c.name}</span>
        {c.source && <span className="text-[10px] opacity-40">{c.source}</span>}
        {c.ai_summary && (
          <span title={c.ai_summary} className="cursor-help text-[10px] text-brand">
            ⓘ
          </span>
        )}
        <button
          type="button"
          onClick={onEnrich}
          disabled={enriching}
          title="Summarize guest reviews with AI (needs Google + Anthropic keys)"
          className="text-[11px] text-ink/40 hover:text-brand disabled:opacity-50"
        >
          ✨
        </button>
      </span>
      <span className="text-right font-figure">{c.amenity_score ?? "—"}</span>
      <span className="text-right font-figure">
        {c.sentiment_score != null ? n(c.sentiment_score).toFixed(1) : "—"}
      </span>
      <span className="text-right font-figure opacity-70">
        {c.distance_mi != null ? `${n(c.distance_mi).toFixed(1)}` : "—"}
      </span>
      <input
        type="number"
        aria-label={`Average nightly rate for ${c.name}`}
        defaultValue={rate}
        placeholder="$"
        key={rate}
        onBlur={(e) => {
          const raw = e.target.value;
          const next = raw === "" ? null : Number(raw);
          if (next !== (c.avg_rate == null ? null : n(c.avg_rate))) onRate(next);
        }}
        className="w-20 rounded border border-brand/20 bg-surface px-2 py-1 text-right font-figure text-sm focus:outline-none focus:ring-2 focus:ring-accent"
      />
    </li>
  );
}
