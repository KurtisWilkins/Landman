/**
 * Underwriting tab — the first layer of the acquisition: the OM-sourced acquisition details and
 * the negotiated purchase price that flows downstream (pro forma → promote). The stabilized
 * NOI / forward projection is sourced from the GL-mapped financials and lands with the pro-forma
 * engine; for now this captures price + surfaces what's already been ingested.
 *
 * Presentational; data-fetching lives in hooks. No browser storage.
 */
import { useEffect, useState } from "react";
import { useAcquisition, useUpdateAcquisition } from "../../api/hooks";
import { fmtUsd } from "../../lib/format";

function prettyType(v: string | undefined): string {
  return v ? v.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : "—";
}

function Detail({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide opacity-60">{label}</dt>
      <dd className="mt-0.5 text-sm">{value}</dd>
    </div>
  );
}

export function UnderwritingTab({ acquisitionId }: { acquisitionId: string }) {
  const { data, isLoading } = useAcquisition(acquisitionId);
  const update = useUpdateAcquisition(acquisitionId);
  const m = data?.metadata;

  // Editable purchase price; seed from the saved value, falling back to the OM ask.
  const [price, setPrice] = useState("");
  useEffect(() => {
    if (m) setPrice(String(m.purchase_price ?? m.ask_price ?? ""));
  }, [m]);

  if (isLoading || !m) return <p className="text-sm opacity-70">Loading…</p>;

  const location = [m.address?.city, m.address?.state].filter(Boolean).join(", ") || "—";
  const dirty = price !== String(m.purchase_price ?? m.ask_price ?? "");

  return (
    <div className="space-y-4">
      <fieldset className="rounded-lg border border-brand/15 p-4">
        <legend className="px-1 text-xs font-medium uppercase tracking-wide opacity-70">
          From the offering memorandum
        </legend>
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Detail label="Name" value={m.name} />
          <Detail label="Property type" value={prettyType(m.property_type)} />
          <Detail label="Location" value={location} />
          <Detail label="Sites / units" value={m.site_count ?? "—"} />
          <Detail label="Seller" value={m.seller_name ?? "—"} />
          <Detail label="Ask price (OM)" value={fmtUsd(m.ask_price)} />
        </dl>
      </fieldset>

      <fieldset className="rounded-lg border border-brand/15 p-4">
        <legend className="px-1 text-xs font-medium uppercase tracking-wide opacity-70">
          Purchase price
        </legend>
        <p className="text-xs opacity-70">
          The negotiated price entered once here flows downstream to the pro forma (debt sizing +
          equity) and the promote. Defaults to the OM ask until set.
        </p>
        <div className="mt-2 flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-xs">
            <span className="opacity-70">Purchase price ($)</span>
            <input
              inputMode="decimal"
              aria-label="Purchase price"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              className="w-56 rounded border border-brand/20 bg-surface px-2 py-1 font-figure text-sm focus:outline-none focus:ring-2 focus:ring-accent"
            />
          </label>
          <button
            type="button"
            disabled={!dirty || update.isPending}
            onClick={() => update.mutate({ purchase_price: price === "" ? null : price })}
            className="rounded bg-brand px-3 py-1.5 text-sm text-surface disabled:opacity-50"
          >
            {update.isPending ? "Saving…" : "Save"}
          </button>
          {update.isError && (
            <span role="alert" className="text-sm text-danger">
              Couldn&apos;t save.
            </span>
          )}
        </div>
      </fieldset>

      <fieldset className="rounded-lg border border-brand/15 p-4">
        <legend className="px-1 text-xs font-medium uppercase tracking-wide opacity-70">
          Stabilized NOI
        </legend>
        <p className="text-sm opacity-70">
          Stabilized income &amp; expense is normalized from the trailing P&amp;L on the RJourney GL
          chart. Upload the P&amp;L on the <span className="font-medium">GL / Docs</span> tab; the
          forward stabilized NOI and its projection arrive with the pro-forma engine.
        </p>
      </fieldset>
    </div>
  );
}
