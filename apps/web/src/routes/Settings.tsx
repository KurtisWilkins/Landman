/**
 * Admin Settings — integration keys (ADR-0012). Admin-only (the API enforces it; non-admins
 * get a 403 and see the notice below). Keys are write-only: we show only Configured/Missing +
 * a last-4 hint and let an admin set/replace a value. Stored encrypted server-side; takes effect
 * immediately (no redeploy). No browser storage.
 */
import { useEffect, useState } from "react";
import {
  useIntegrations,
  useSaveUnderwritingDefaults,
  useSetIntegration,
  useUnderwritingDefaults,
} from "../api/hooks";
import { ApiError } from "../api/client";
import type { Schemas } from "../api/client";

type IntegrationStatus = Schemas["IntegrationStatus"];
type UnderwritingDefaults = Schemas["UnderwritingDefaults"];

function IntegrationRow({ item }: { item: IntegrationStatus }) {
  const setKey = useSetIntegration();
  const [value, setValue] = useState("");

  function save() {
    const v = value.trim();
    if (!v) return;
    setKey.mutate({ key: item.key, value: v }, { onSuccess: () => setValue("") });
  }

  return (
    <li className="py-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-medium">{item.label}</div>
          <div className="text-xs opacity-70">
            <code>{item.key}</code> ·{" "}
            {item.configured ? (
              <span className="text-brand">
                Configured{item.hint ? ` (…${item.hint})` : ""}
                {item.source ? ` · ${item.source}` : ""}
              </span>
            ) : (
              <span className="text-danger">Missing</span>
            )}
          </div>
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input
          type="password"
          aria-label={`${item.label} value`}
          placeholder={item.configured ? "Replace value…" : "Paste key…"}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="w-full max-w-md rounded border border-brand/20 bg-surface px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
        />
        <button
          type="button"
          onClick={save}
          disabled={!value.trim() || setKey.isPending}
          className="rounded bg-brand px-3 py-1.5 text-sm text-surface disabled:opacity-50"
        >
          {setKey.isPending ? "Saving…" : "Save"}
        </button>
        {setKey.isSuccess && <span className="text-xs text-brand">Saved.</span>}
        {setKey.isError && (
          <span role="alert" className="text-xs text-danger">
            {setKey.error instanceof ApiError ? setKey.error.message : "Save failed."}
          </span>
        )}
      </div>
    </li>
  );
}

// Editable numeric default. `pct` fields display ×100 and store the decimal.
const UW_FIELDS: { key: keyof UnderwritingDefaults; label: string; pct: boolean }[] = [
  { key: "ltv", label: "LTV", pct: true },
  { key: "loan_rate", label: "Loan rate", pct: true },
  { key: "amort_months", label: "Amortization (months)", pct: false },
  { key: "io_years", label: "Interest-only (years)", pct: false },
  { key: "noi_growth", label: "NOI growth", pct: true },
  { key: "exit_cap", label: "Exit cap", pct: true },
  { key: "selling_cost_rate", label: "Selling cost", pct: true },
  { key: "capex_reserve_rate", label: "CapEx reserve", pct: true },
  { key: "hold_years", label: "Hold (years)", pct: false },
];

function num(v: unknown): number {
  return Number(v) || 0;
}

function UnderwritingDefaultsSection() {
  const { data, error } = useUnderwritingDefaults();
  const save = useSaveUnderwritingDefaults();
  const [form, setForm] = useState<UnderwritingDefaults>({});

  useEffect(() => {
    if (data) setForm(data);
  }, [data]);

  if (error) return null; // GET is open to any authenticated user; ignore transient errors here

  return (
    <div className="mt-10">
      <h2 className="text-lg font-semibold">Underwriting defaults</h2>
      <p className="mt-1 text-sm opacity-70">
        Best-guess starting values that pre-fill each acquisition&apos;s pro forma. Per-acquisition
        edits always override these. Admin-only to change.
      </p>
      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
        {UW_FIELDS.map((f) => {
          const raw = form[f.key];
          const shown = raw == null ? "" : f.pct ? num(raw) * 100 : num(raw);
          return (
            <label key={f.key} className="flex flex-col gap-1 text-xs">
              <span className="opacity-70">
                {f.label}
                {f.pct ? " (%)" : ""}
              </span>
              <input
                type="number"
                aria-label={f.label}
                value={shown}
                step={f.pct ? 0.25 : 1}
                onChange={(e) =>
                  setForm((s) => ({
                    ...s,
                    [f.key]: f.pct ? num(e.target.value) / 100 : num(e.target.value),
                  }))
                }
                className="w-full rounded border border-brand/20 bg-surface px-2 py-1 font-figure text-sm focus:outline-none focus:ring-2 focus:ring-accent"
              />
            </label>
          );
        })}
      </div>
      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          onClick={() => save.mutate(form)}
          disabled={save.isPending}
          className="rounded bg-brand px-3 py-1.5 text-sm text-surface disabled:opacity-50"
        >
          {save.isPending ? "Saving…" : "Save defaults"}
        </button>
        {save.isSuccess && <span className="text-xs text-brand">Saved.</span>}
        {save.isError && (
          <span role="alert" className="text-xs text-danger">
            {save.error instanceof ApiError && save.error.status === 403
              ? "Admin-only."
              : "Save failed."}
          </span>
        )}
      </div>
    </div>
  );
}

export function Settings() {
  const { data, isLoading, error } = useIntegrations();

  return (
    <section>
      <h1 className="text-2xl font-semibold">Settings</h1>
      <p className="mt-1 text-sm opacity-70">
        Integration API keys. Values are stored encrypted and never shown back — only whether each
        is configured, plus the last 4 characters. Saving takes effect immediately.
      </p>

      {isLoading && <p className="mt-4 text-sm opacity-70">Loading…</p>}

      {error && (
        <p className="mt-4 rounded border border-brand/20 p-3 text-sm opacity-80">
          {error instanceof ApiError && error.status === 403
            ? "Integration keys are admin-only. Ask an admin to set them."
            : "Couldn’t load integration settings."}
        </p>
      )}

      {data && (
        <ul className="mt-4 divide-y divide-brand/10">
          {data.map((item) => (
            <IntegrationRow key={item.key} item={item} />
          ))}
        </ul>
      )}

      <UnderwritingDefaultsSection />
    </section>
  );
}
