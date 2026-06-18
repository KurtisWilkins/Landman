/**
 * Pro forma tab (design doc §5.5, §3): 5-year levered cash flow. Renders on mobile via
 * horizontal scroll now ([DECISION] A-5: a condensed card view is a later hook). Live
 * numbers arrive with the underwriting backend; until then the screen degrades gracefully.
 */
import { useProforma } from "../../api/hooks";

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});
const pct = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 1 });

function n(v: unknown): number {
  return Number(v ?? 0);
}

export function ProformaTab({ dealId }: { dealId: string }) {
  const { data, isLoading, error } = useProforma(dealId);

  if (isLoading) return <p className="text-sm opacity-70">Loading…</p>;
  if (error || !data)
    return (
      <p className="rounded border border-brand/20 p-3 text-sm opacity-80">
        The pro forma lands with the underwriting backend (IRR, waterfall, 5-yr cash flow). This tab
        is wired to the contract and will render once it’s implemented.
      </p>
    );

  const years = data.years ?? [];
  const rows: { key: keyof (typeof years)[number]; label: string }[] = [
    { key: "revenue", label: "Revenue" },
    { key: "opex", label: "OpEx" },
    { key: "noi", label: "NOI" },
    { key: "debt_service", label: "Debt Service" },
    { key: "capex", label: "CapEx reserve" },
    { key: "levered_cf", label: "Levered CF" },
  ];

  return (
    <div>
      <dl className="mb-4 flex flex-wrap gap-4">
        <div>
          <dt className="text-xs uppercase opacity-60">Levered IRR</dt>
          <dd className="font-figure text-lg">
            {data.levered_irr != null ? pct.format(n(data.levered_irr)) : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase opacity-60">Equity multiple</dt>
          <dd className="font-figure text-lg">
            {data.equity_multiple != null ? `${n(data.equity_multiple).toFixed(2)}x` : "—"}
          </dd>
        </div>
      </dl>

      {/* Horizontal scroll keeps the full table usable on mobile (A-5). */}
      <div className="overflow-x-auto">
        <table className="min-w-[640px] border-collapse text-sm">
          <thead>
            <tr>
              <th className="px-2 py-1 text-left font-medium">Line</th>
              {years.map((y) => (
                <th key={y.yr} className="px-2 py-1 text-right font-medium">
                  Yr {y.yr}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="font-figure">
            {rows.map((r) => (
              <tr key={r.key} className="border-t border-brand/10">
                <td className="px-2 py-1">{r.label}</td>
                {years.map((y) => (
                  <td key={y.yr} className="px-2 py-1 text-right">
                    {usd.format(n(y[r.key]))}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
