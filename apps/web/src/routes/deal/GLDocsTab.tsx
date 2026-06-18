/**
 * GL / Docs tab (design doc §5.3): the GL mapping review for the deal — each seller line
 * with its proposed account, level, and confidence. Live data arrives with the ingestion /
 * mapping backend; until then the tab degrades gracefully.
 */
import { useMapping } from "../../api/hooks";
import { DocUpload } from "./DocUpload";
import { FinancialVersions } from "./FinancialVersions";

export function GLDocsTab({ dealId }: { dealId: string }) {
  return (
    <div className="space-y-4">
      <DocUpload dealId={dealId} />
      <FinancialVersions dealId={dealId} />
      <MappingReview dealId={dealId} />
    </div>
  );
}

function MappingReview({ dealId }: { dealId: string }) {
  const { data, isLoading, error } = useMapping(dealId);

  if (isLoading) return <p className="text-sm opacity-70">Loading…</p>;
  if (error || !data)
    return (
      <p className="rounded border border-forest/20 p-3 text-sm opacity-80">
        Proposed GL mappings for human review appear here once a document is uploaded and the
        mapping backend has processed it.
      </p>
    );

  const lines = data.lines ?? [];
  if (lines.length === 0) return <p className="text-sm opacity-70">No lines to map.</p>;

  return (
    <div className="overflow-x-auto">
      <table className="min-w-[560px] border-collapse text-sm">
        <thead>
          <tr>
            <th className="px-2 py-1 text-left font-medium">Seller line</th>
            <th className="px-2 py-1 text-left font-medium">Proposed account</th>
            <th className="px-2 py-1 text-left font-medium">Confidence</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((l) => (
            <tr key={l.line_id} className="border-t border-forest/10">
              <td className="px-2 py-1">{l.seller_source_line}</td>
              <td className="px-2 py-1 font-figure">
                {l.proposed_account_code ?? "—"}
                {l.proposed_level ? ` (${l.proposed_level})` : ""}
              </td>
              <td className="px-2 py-1">{l.map_confidence ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
