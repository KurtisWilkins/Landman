/**
 * Market tab (design doc §5.5): population rings — estimated population within 25 / 50 / 100 /
 * 150 miles of the property, auto-pulled on entry and overridable. Each ring shows whether the
 * value is the provider baseline or an operator override.
 */
import { usePopulationRings } from "../../api/hooks";

const RADII = [25, 50, 100, 150] as const;
const num = new Intl.NumberFormat("en-US");

export function MarketTab({ acquisitionId }: { acquisitionId: string }) {
  const { data, isLoading, error } = usePopulationRings(acquisitionId);
  const byRadius = new Map((data?.rings ?? []).map((r) => [r.radius_mi, r]));

  if (isLoading) return <p className="text-sm opacity-70">Loading…</p>;
  if (error)
    return (
      <p className="rounded border border-brand/20 p-3 text-sm opacity-80">
        Couldn’t load the market view.
      </p>
    );

  const hasAny = (data?.rings ?? []).some((r) => r.population != null);

  return (
    <section aria-label="Population rings">
      <h2 className="font-figure text-sm uppercase tracking-wide opacity-70">Population rings</h2>
      {!hasAny && (
        <p className="mt-2 text-sm opacity-70">
          No population estimates yet — they auto-pull once a demographics provider is configured,
          or can be entered per ring.
        </p>
      )}
      <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
        {RADII.map((radius) => {
          const ring = byRadius.get(radius);
          return (
            <div key={radius} className="rounded-lg border border-brand/15 p-3">
              <div className="text-xs uppercase tracking-wide opacity-70">{radius} mi</div>
              <div className="mt-1 font-figure text-2xl">
                {ring?.population != null ? num.format(ring.population) : "—"}
              </div>
              {ring?.is_override ? (
                <div className="font-figure text-xs text-accent-ink">override</div>
              ) : ring?.source ? (
                <div className="font-figure text-xs opacity-60">
                  {ring.source}
                  {ring.as_of ? ` · ${ring.as_of}` : ""}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}
