/**
 * Comps tab (design doc §5.6): "Find competitors within 50 miles" of the OM address, then a
 * rate × sentiment scatter (Recharts) + a ranked amenity list. Discovery geocodes the address and
 * searches OpenStreetMap (free, always on) + Google Places (when keyed); the niche RV-directory
 * scrapers stay off until D-22 clears. The search runs in the worker, so results fill in by polling.
 */
import { useEffect, useState } from "react";
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
import { useComps, useDiscoverComps } from "../../api/hooks";

function n(v: unknown): number {
  return Number(v ?? 0);
}

export function CompsTab({ acquisitionId }: { acquisitionId: string }) {
  const [searching, setSearching] = useState(false);
  const { data, isLoading, error } = useComps(acquisitionId, { poll: searching });
  const discover = useDiscoverComps(acquisitionId);
  const comps = data?.comps ?? [];

  // Stop polling once results land, or after a safety window (the worker may find nothing).
  useEffect(() => {
    if (!searching) return;
    if (comps.length > 0) {
      setSearching(false);
      return;
    }
    const t = setTimeout(() => setSearching(false), 45000);
    return () => clearTimeout(t);
  }, [searching, comps.length]);

  const onDiscover = () => discover.mutate(undefined, { onSuccess: () => setSearching(true) });
  const discoverError = discover.error instanceof Error ? discover.error.message : undefined;

  const Toolbar = (
    <div className="flex flex-wrap items-center gap-3">
      <span className="text-sm font-medium">Competitive set — within 50 miles</span>
      <button
        type="button"
        disabled={discover.isPending || searching}
        onClick={onDiscover}
        className="ml-auto rounded bg-brand px-3 py-1.5 text-sm text-surface disabled:opacity-50"
      >
        {discover.isPending
          ? "Locating…"
          : searching
            ? "Searching…"
            : comps.length > 0
              ? "Re-scan"
              : "Find competitors within 50 mi"}
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

      {comps.length === 0 ? (
        <p className="rounded border border-brand/20 p-3 text-sm opacity-80">
          {searching
            ? "Searching for RV parks, campgrounds, resorts, glamping sites and marinas within 50 miles…"
            : "No competitors found yet. Click “Find competitors within 50 mi” to search from the property’s address."}
        </p>
      ) : (
        <>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 8, right: 8, bottom: 24, left: 8 }}>
                <CartesianGrid strokeOpacity={0.15} />
                <XAxis type="number" dataKey="rate" name="Avg rate" unit="$" />
                <YAxis type="number" dataKey="sentiment" name="Sentiment" />
                <ZAxis type="number" dataKey="amenity" range={[40, 200]} name="Amenity" />
                <Tooltip cursor={{ strokeDasharray: "3 3" }} />
                <Scatter data={points} fill="var(--color-accent)" />
              </ScatterChart>
            </ResponsiveContainer>
          </div>

          <div>
            <p className="mb-1 text-xs uppercase tracking-wide opacity-60">
              {comps.length} competitor{comps.length === 1 ? "" : "s"} found
            </p>
            <ol className="divide-y divide-brand/10">
              {ranked.map((c) => (
                <li key={c.comp_id} className="flex items-center justify-between py-2 text-sm">
                  <span>
                    <span className="font-figure mr-2 opacity-60">#{c.amenity_rank ?? "—"}</span>
                    {c.name}
                    {c.source && <span className="ml-2 text-[10px] opacity-40">{c.source}</span>}
                  </span>
                  <span className="font-figure">
                    {c.distance_mi != null ? `${n(c.distance_mi).toFixed(1)} mi` : ""}
                    {c.avg_rate != null ? ` · $${n(c.avg_rate)}` : ""}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </>
      )}
    </div>
  );
}
