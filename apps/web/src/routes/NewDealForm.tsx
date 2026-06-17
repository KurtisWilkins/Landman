/**
 * New-deal intake form (design doc §5.1). Manual entry creates the deal in Initial UW; the
 * market (population) block auto-pulls on the server when a geocode is present. Presentational —
 * data-fetching lives in the useCreateDeal hook. No browser storage.
 */
import { useState } from "react";
import { useCreateDeal } from "../api/hooks";
import { ApiError } from "../api/client";
import type { components } from "../api/types";

type PropertyType = components["schemas"]["PropertyType"];

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
  "mt-1 w-full rounded border border-forest/20 bg-bone px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brass-accent";

export function NewDealForm({
  onCreated,
  onCancel,
}: {
  onCreated: (dealId: string) => void;
  onCancel: () => void;
}) {
  const create = useCreateDeal();
  const [name, setName] = useState("");
  const [propertyType, setPropertyType] = useState<PropertyType>("rv_resort");
  const [city, setCity] = useState("");
  const [stateCode, setStateCode] = useState("");
  const [siteCount, setSiteCount] = useState("");
  const [askPrice, setAskPrice] = useState("");
  const [sellerName, setSellerName] = useState("");

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
      { onSuccess: (deal) => onCreated(deal.deal_id) },
    );
  }

  return (
    <form onSubmit={submit} className="mt-4 rounded-lg border border-forest/15 p-4">
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

      {create.isError && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {create.error instanceof ApiError ? create.error.message : "Could not create the deal."}
        </p>
      )}

      <div className="mt-4 flex gap-2">
        <button
          type="submit"
          disabled={!name.trim() || create.isPending}
          className="rounded bg-forest px-3 py-1.5 text-sm text-bone disabled:opacity-50"
        >
          {create.isPending ? "Creating…" : "Create deal"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded border border-forest/20 px-3 py-1.5 text-sm"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
