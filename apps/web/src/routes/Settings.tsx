/**
 * Admin Settings — integration keys (ADR-0012). Admin-only (the API enforces it; non-admins
 * get a 403 and see the notice below). Keys are write-only: we show only Configured/Missing +
 * a last-4 hint and let an admin set/replace a value. Stored encrypted server-side; takes effect
 * immediately (no redeploy). No browser storage.
 */
import { useEffect, useState } from "react";
import {
  useDefaultRules,
  useIntegrations,
  useSaveUnderwritingDefaults,
  useSetIntegration,
  useUnderwritingDefaults,
  useUpdateDefaultRule,
} from "../api/hooks";
import type { DefaultRuleRow } from "../api/hooks";
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

// How a rule's stored value is shown/edited: percent rates display ×100; the rest are as-is.
function ruleDisplay(rule: DefaultRuleRow): { factor: number; suffix: string } {
  switch (rule.rule_type) {
    case "percent_of_gross_revenue":
    case "percent_of_line":
      return { factor: 100, suffix: "%" };
    case "prior_year_uplift":
      return { factor: 1, suffix: "× prior" };
    case "per_unit_annual":
      return { factor: 1, suffix: "$/unit/yr" };
    case "per_employee_month":
      return { factor: 1, suffix: "$/emp/mo" };
    case "fixed":
      return { factor: 1, suffix: rule.basis === "monthly" ? "$/mo" : "$/yr" };
    default:
      return { factor: 1, suffix: "" };
  }
}

function RuleRow({ rule }: { rule: DefaultRuleRow }) {
  const update = useUpdateDefaultRule();
  const { factor, suffix } = ruleDisplay(rule);
  const shown = String(Number(rule.value) * factor);
  const [value, setValue] = useState(shown);
  useEffect(() => setValue(shown), [shown]);

  const dirty = value.trim() !== "" && value.trim() !== shown;
  const band =
    rule.soft_min && rule.soft_max
      ? ` · band ${Number(rule.soft_min) * 100}–${Number(rule.soft_max) * 100}%`
      : "";

  return (
    <li className={`py-3 ${rule.enabled ? "" : "opacity-50"}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-medium">
            {rule.label}
            {rule.must_fix && (
              <span className="ml-2 rounded bg-accent/15 px-1.5 py-0.5 text-[10px] text-accent-ink">
                must fix
              </span>
            )}
            {rule.is_income_offset && (
              <span className="ml-2 rounded bg-ink/10 px-1.5 py-0.5 text-[10px] text-ink/70">
                contra
              </span>
            )}
          </div>
          <div className="text-xs opacity-70">
            <code>{rule.rule_type}</code> · → GL {rule.target_account_code}
            {band}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="number"
            aria-label={`${rule.label} value`}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="w-24 rounded border border-brand/20 bg-surface px-2 py-1 text-right font-figure text-sm focus:outline-none focus:ring-2 focus:ring-accent"
          />
          <span className="w-20 text-xs opacity-60">{suffix}</span>
          <button
            type="button"
            disabled={!dirty || update.isPending}
            onClick={() =>
              update.mutate({ ruleKey: rule.rule_key, patch: { value: Number(value) / factor } })
            }
            className="rounded bg-brand px-3 py-1.5 text-sm text-surface disabled:opacity-50"
          >
            Save
          </button>
          <label className="flex items-center gap-1 text-xs opacity-70">
            <input
              type="checkbox"
              checked={rule.enabled}
              onChange={() =>
                update.mutate({ ruleKey: rule.rule_key, patch: { enabled: !rule.enabled } })
              }
            />
            on
          </label>
        </div>
      </div>
      {update.isError && (
        <span role="alert" className="text-xs text-danger">
          {update.error instanceof ApiError && update.error.status === 403
            ? "Admin-only."
            : "Save failed."}
        </span>
      )}
    </li>
  );
}

function DefaultRulesSection() {
  const { data, error } = useDefaultRules();
  if (error) return null; // GET is open to any authenticated user; PUT is admin-gated server-side
  const rules = data?.rules ?? [];
  if (rules.length === 0) return null;

  return (
    <div className="mt-10">
      <h2 className="text-lg font-semibold">Budget default rules</h2>
      <p className="mt-1 text-sm opacity-70">
        The global rules that autofill year-one budget line items. A change applies to every deal on
        the next budget recompute; a per-acquisition manual edit always wins. Admin-only to change.
      </p>
      <ul className="mt-3 divide-y divide-brand/10">
        {rules.map((r) => (
          <RuleRow key={r.rule_key} rule={r} />
        ))}
      </ul>
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
      <DefaultRulesSection />
    </section>
  );
}
