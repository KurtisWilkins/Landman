/**
 * Comps tab (design doc §5.6): rate × sentiment scatter (Recharts) + a ranked amenity list,
 * target highlighted. Live data arrives with the comp-intelligence backend.
 */
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
import { useComps } from "../../api/hooks";

function n(v: unknown): number {
  return Number(v ?? 0);
}

export function CompsTab({ dealId }: { dealId: string }) {
  const { data, isLoading, error } = useComps(dealId);

  if (isLoading) return <p className="text-sm opacity-70">Loading…</p>;
  if (error || !data)
    return (
      <p className="rounded border border-forest/20 p-3 text-sm opacity-80">
        Comps land with the comp-intelligence backend (50-mile set, sentiment, amenity scores). This
        tab is wired to the contract and will render once it’s implemented.
      </p>
    );

  const comps = data.comps ?? [];
  const points = comps.map((c) => ({
    name: c.name,
    rate: n(c.avg_rate),
    sentiment: n(c.sentiment_score),
    amenity: c.amenity_score ?? 0,
  }));
  const ranked = [...comps].sort((a, b) => (a.amenity_rank ?? 999) - (b.amenity_rank ?? 999));

  return (
    <div className="space-y-6">
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 8, right: 8, bottom: 24, left: 8 }}>
            <CartesianGrid strokeOpacity={0.15} />
            <XAxis type="number" dataKey="rate" name="Avg rate" unit="$" />
            <YAxis type="number" dataKey="sentiment" name="Sentiment" />
            <ZAxis type="number" dataKey="amenity" range={[40, 200]} name="Amenity" />
            <Tooltip cursor={{ strokeDasharray: "3 3" }} />
            <Scatter data={points} fill="#b08a3e" />
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      {ranked.length === 0 ? (
        <p className="text-sm opacity-70">No comps yet.</p>
      ) : (
        <ol className="divide-y divide-forest/10">
          {ranked.map((c) => (
            <li key={c.comp_id} className="flex items-center justify-between py-2 text-sm">
              <span>
                <span className="font-figure mr-2 opacity-60">#{c.amenity_rank ?? "—"}</span>
                {c.name}
              </span>
              <span className="font-figure">{c.avg_rate != null ? `$${n(c.avg_rate)}` : "—"}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
