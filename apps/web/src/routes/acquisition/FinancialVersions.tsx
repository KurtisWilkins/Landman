/**
 * Financials upload versions (design doc §5.2): every P&L upload is a dated, retained version.
 * The current one feeds the GL mapping view; older versions stay selectable (nothing is
 * overwritten or deleted). An operator picks which version is active. Presentational — data
 * lives in the useFinancialPeriods / useActivateFinancialPeriod hooks.
 */
import { useActivateFinancialPeriod, useFinancialPeriods } from "../../api/hooks";

function formatWhen(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export function FinancialVersions({ acquisitionId }: { acquisitionId: string }) {
  const { data, isLoading } = useFinancialPeriods(acquisitionId);
  const activate = useActivateFinancialPeriod(acquisitionId);

  if (isLoading) return null;
  const versions = data ?? [];
  // Nothing to choose between until there's more than one upload.
  if (versions.length < 2) return null;

  return (
    <div className="rounded-lg border border-brand/15 p-4">
      <div className="text-sm font-medium">Financials versions</div>
      <p className="mt-1 text-xs opacity-70">
        Each upload is kept as a dated version; the active one feeds the GL view below. Switching
        never deletes a version.
      </p>
      <ul className="mt-3 divide-y divide-brand/10">
        {versions.map((v) => (
          <li key={v.period_id} className="flex items-center justify-between gap-3 py-2">
            <div className="min-w-0">
              <div className="truncate text-sm">
                {v.source_filename ?? v.label ?? v.period_id}
                {v.is_current && (
                  <span className="ml-2 rounded bg-brand/10 px-1.5 py-0.5 text-xs text-brand">
                    Active
                  </span>
                )}
              </div>
              <div className="text-xs opacity-70">
                <span className="font-figure">{v.line_count}</span> lines ·{" "}
                {formatWhen(v.ingested_at)}
              </div>
            </div>
            {v.is_current ? (
              <span className="text-xs opacity-50">current</span>
            ) : (
              <button
                type="button"
                onClick={() => activate.mutate(v.period_id)}
                disabled={activate.isPending}
                className="rounded border border-brand/30 px-2 py-1 text-xs text-brand disabled:opacity-50"
              >
                Make active
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
