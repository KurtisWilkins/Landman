/**
 * New-acquisition intake (design doc §5.1, §5.2). Two paths into the same reviewable form:
 *  • Upload an Offering Memorandum (PDF) → Claude extracts a proposal → the fields below are
 *    pre-filled for the operator to review/correct (AI proposes, a person accepts — CLAUDE.md).
 *  • Enter everything by hand.
 * On create, if an OM was used it's also uploaded to the new acquisition so its financials load.
 * Presentational — data-fetching lives in hooks. No browser storage.
 */
import { useState } from "react";
import { useCreateAcquisition, useExtractOm } from "../api/hooks";
import { ApiError, apiUpload } from "../api/client";
import type { components } from "../api/types";

type PropertyType = components["schemas"]["PropertyType"];
type OmFinancialLine = components["schemas"]["OmFinancialLine"];

const PROPERTY_TYPES: { value: PropertyType; label: string }[] = [
  { value: "rv_resort", label: "RV resort" },
  { value: "campground", label: "Campground" },
  { value: "glamping", label: "Glamping" },
  { value: "cabin_resort", label: "Cabin resort" },
  { value: "marina", label: "Marina" },
  { value: "mobile_home", label: "Mobile home" },
  { value: "hybrid", label: "Hybrid" },
];

const labelCls = "block text-xs uppercase tracking-wide opacity-70";
const inputCls =
  "mt-1 w-full rounded border border-brand/20 bg-surface px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-accent";

export function NewAcquisitionForm({
  onCreated,
  onCancel,
}: {
  onCreated: (acquisitionId: string) => void;
  onCancel: () => void;
}) {
  const create = useCreateAcquisition();
  const extract = useExtractOm();
  const [mode, setMode] = useState<"manual" | "om">("manual");
  const [omFile, setOmFile] = useState<File | null>(null);
  const [financials, setFinancials] = useState<OmFinancialLine[]>([]);

  const [name, setName] = useState("");
  const [propertyType, setPropertyType] = useState<PropertyType>("rv_resort");
  const [city, setCity] = useState("");
  const [stateCode, setStateCode] = useState("");
  const [siteCount, setSiteCount] = useState("");
  const [askPrice, setAskPrice] = useState("");
  const [sellerName, setSellerName] = useState("");

  function extractFromOm() {
    if (!omFile) return;
    extract.mutate(omFile, {
      onSuccess: (p) => {
        // Pre-fill for review — every field stays editable; nothing is saved yet.
        if (p.name) setName(p.name);
        if (p.property_type) setPropertyType(p.property_type);
        if (p.address?.city) setCity(p.address.city);
        if (p.address?.state) setStateCode(p.address.state);
        if (p.site_count != null) setSiteCount(String(p.site_count));
        if (p.ask_price != null) setAskPrice(String(p.ask_price));
        if (p.seller_name) setSellerName(p.seller_name);
        setFinancials(p.financial_lines ?? []);
      },
    });
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    create.mutate(
      {
        name: name.trim(),
        property_type: propertyType,
        address: city || stateCode ? { city: city || null, state: stateCode || null } : null,
        site_count: siteCount ? Number(siteCount) : null,
        // Money stays a string to the API (Decimal server-side; never a float).
        ask_price: askPrice ? askPrice : null,
        seller_name: sellerName || null,
      },
      {
        onSuccess: async (acquisition) => {
          // If this came from an OM, attach the PDF so its financials load on the new acquisition.
          // Best-effort: a failed attachment shouldn't block landing on the created acquisition.
          if (omFile) {
            try {
              await apiUpload(`/acquisitions/${acquisition.acquisition_id}/documents`, omFile);
            } catch {
              /* acquisition exists; the OM can be re-uploaded from the GL/Docs tab */
            }
          }
          onCreated(acquisition.acquisition_id);
        },
      },
    );
  }

  const busy = create.isPending || extract.isPending;

  return (
    <form onSubmit={submit} className="mt-4 rounded-lg border border-brand/15 p-4">
      <div role="tablist" aria-label="Intake method" className="mb-4 flex gap-1">
        {(["manual", "om"] as const).map((m) => (
          <button
            key={m}
            type="button"
            role="tab"
            aria-selected={mode === m}
            onClick={() => setMode(m)}
            className={`rounded px-3 py-1 text-sm ${
              mode === m ? "bg-brand text-surface" : "border border-brand/20"
            }`}
          >
            {m === "manual" ? "Enter manually" : "Upload OM (PDF)"}
          </button>
        ))}
      </div>

      {mode === "om" && (
        <div className="mb-4 rounded-lg border border-brand/15 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="file"
              aria-label="Offering memorandum"
              accept=".pdf"
              onChange={(e) => setOmFile(e.target.files?.[0] ?? null)}
              className="text-sm"
            />
            <button
              type="button"
              onClick={extractFromOm}
              disabled={!omFile || extract.isPending}
              className="rounded bg-accent px-3 py-1.5 text-sm text-ink disabled:opacity-50"
            >
              {extract.isPending ? "Extracting…" : "Extract from OM"}
            </button>
          </div>
          {extract.isError && (
            <p role="alert" className="mt-2 text-sm text-danger">
              {extract.error instanceof ApiError &&
              extract.error.code === "extractor_not_configured"
                ? "OM extraction isn’t configured yet (needs the AI provider key). Enter the acquisition manually for now."
                : "Couldn’t read that OM. Try another file or enter the acquisition manually."}
            </p>
          )}
          {extract.isSuccess && (
            <p className="mt-2 text-sm opacity-70">
              Extracted — review and correct the fields below before creating the acquisition.
            </p>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="md:col-span-2">
          <label htmlFor="nd-name" className={labelCls}>
            Property name
          </label>
          <input
            id="nd-name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={inputCls}
          />
        </div>
        <div>
          <label htmlFor="nd-type" className={labelCls}>
            Property type
          </label>
          <select
            id="nd-type"
            value={propertyType}
            onChange={(e) => setPropertyType(e.target.value as PropertyType)}
            className={inputCls}
          >
            {PROPERTY_TYPES.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="nd-seller" className={labelCls}>
            Seller (optional)
          </label>
          <input
            id="nd-seller"
            value={sellerName}
            onChange={(e) => setSellerName(e.target.value)}
            className={inputCls}
          />
        </div>
        <div>
          <label htmlFor="nd-city" className={labelCls}>
            City
          </label>
          <input
            id="nd-city"
            value={city}
            onChange={(e) => setCity(e.target.value)}
            className={inputCls}
          />
        </div>
        <div>
          <label htmlFor="nd-state" className={labelCls}>
            State
          </label>
          <input
            id="nd-state"
            value={stateCode}
            onChange={(e) => setStateCode(e.target.value)}
            maxLength={2}
            className={inputCls}
          />
        </div>
        <div>
          <label htmlFor="nd-sites" className={labelCls}>
            Site count
          </label>
          <input
            id="nd-sites"
            type="number"
            min="0"
            value={siteCount}
            onChange={(e) => setSiteCount(e.target.value)}
            className={`${inputCls} font-figure`}
          />
        </div>
        <div>
          <label htmlFor="nd-ask" className={labelCls}>
            Ask price (USD)
          </label>
          <input
            id="nd-ask"
            inputMode="decimal"
            value={askPrice}
            onChange={(e) => setAskPrice(e.target.value)}
            className={`${inputCls} font-figure`}
          />
        </div>
      </div>

      {financials.length > 0 && (
        <div className="mt-4">
          <div className="text-xs uppercase tracking-wide opacity-70">
            Extracted financials (loaded on create)
          </div>
          <ul className="mt-1 divide-y divide-brand/10 text-sm">
            {financials.map((line, i) => (
              <li key={i} className="flex justify-between py-1">
                <span>{line.description}</span>
                <span className="font-figure">{line.amount ?? "—"}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {create.isError && (
        <p role="alert" className="mt-3 text-sm text-danger">
          {create.error instanceof ApiError
            ? create.error.message
            : "Could not create the acquisition."}
        </p>
      )}

      <div className="mt-4 flex gap-2">
        <button
          type="submit"
          disabled={!name.trim() || busy}
          className="rounded bg-brand px-3 py-1.5 text-sm text-surface disabled:opacity-50"
        >
          {create.isPending ? "Creating…" : "Create acquisition"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded border border-brand/20 px-3 py-1.5 text-sm"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
