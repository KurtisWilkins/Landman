/**
 * Admin Settings — integration keys (ADR-0012). Admin-only (the API enforces it; non-admins
 * get a 403 and see the notice below). Keys are write-only: we show only Configured/Missing +
 * a last-4 hint and let an admin set/replace a value. Stored encrypted server-side; takes effect
 * immediately (no redeploy). No browser storage.
 */
import { useState } from "react";
import { useIntegrations, useSetIntegration } from "../api/hooks";
import { ApiError } from "../api/client";
import type { Schemas } from "../api/client";

type IntegrationStatus = Schemas["IntegrationStatus"];

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
              <span className="text-forest">
                Configured{item.hint ? ` (…${item.hint})` : ""}
                {item.source ? ` · ${item.source}` : ""}
              </span>
            ) : (
              <span className="text-red-700">Missing</span>
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
          className="w-full max-w-md rounded border border-forest/20 bg-bone px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brass-accent"
        />
        <button
          type="button"
          onClick={save}
          disabled={!value.trim() || setKey.isPending}
          className="rounded bg-forest px-3 py-1.5 text-sm text-bone disabled:opacity-50"
        >
          {setKey.isPending ? "Saving…" : "Save"}
        </button>
        {setKey.isSuccess && <span className="text-xs text-forest">Saved.</span>}
        {setKey.isError && (
          <span role="alert" className="text-xs text-red-700">
            {setKey.error instanceof ApiError ? setKey.error.message : "Save failed."}
          </span>
        )}
      </div>
    </li>
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
        <p className="mt-4 rounded border border-forest/20 p-3 text-sm opacity-80">
          {error instanceof ApiError && error.status === 403
            ? "Integration keys are admin-only. Ask an admin to set them."
            : "Couldn’t load integration settings."}
        </p>
      )}

      {data && (
        <ul className="mt-4 divide-y divide-forest/10">
          {data.map((item) => (
            <IntegrationRow key={item.key} item={item} />
          ))}
        </ul>
      )}
    </section>
  );
}
