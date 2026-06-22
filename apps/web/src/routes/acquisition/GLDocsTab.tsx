/**
 * GL / Docs tab (design doc §5.3): the GL mapping confirm workstation. Uploaded P&L lines are
 * auto-classified in the background (learned phrases resolve; the rest await the AI providers),
 * then a human confirms each line against the canonical GL chart here — remap, set NOI placement,
 * learn for reuse. Lines are bucketed by status so the unmatched/ambiguous ones surface first.
 */
import { useMemo, useState } from "react";
import { useConfirmMapping, useGlAccounts, useMapping } from "../../api/hooks";
import type { Schemas } from "../../api/client";
import { fmtUsd } from "../../lib/format";
import { DocUpload } from "./DocUpload";
import { FinancialVersions } from "./FinancialVersions";

type ReviewLine = Schemas["MappingReviewLine"];
type GlAccount = Schemas["GlAccountOption"];
type Confirm = Schemas["MappingConfirm"];
type Noi = Confirm["noi_placement"];
type Level = Confirm["account_level"];

const NOI_OPTIONS: { value: Noi; label: string }[] = [
  { value: "above", label: "Above the line" },
  { value: "below", label: "Below the line" },
  { value: "non_operating", label: "Non-operating" },
];

export function GLDocsTab({ acquisitionId }: { acquisitionId: string }) {
  return (
    <div className="space-y-4">
      <DocUpload acquisitionId={acquisitionId} />
      <FinancialVersions acquisitionId={acquisitionId} />
      <MappingWorkstation acquisitionId={acquisitionId} />
    </div>
  );
}

function MappingWorkstation({ acquisitionId }: { acquisitionId: string }) {
  const { data, isLoading, error } = useMapping(acquisitionId);
  const { data: accounts } = useGlAccounts();
  const confirm = useConfirmMapping(acquisitionId);

  const lines = useMemo(() => data?.lines ?? [], [data]);
  const buckets = useMemo(() => {
    const confirmed = lines.filter((l) => l.reviewed_at);
    const open = lines.filter((l) => !l.reviewed_at);
    const needsReview = open.filter(
      (l) => !l.proposed_account_code || l.map_confidence === "coarse",
    );
    const autoMapped = open.filter((l) => l.proposed_account_code && l.map_confidence !== "coarse");
    return { confirmed, needsReview, autoMapped };
  }, [lines]);

  if (isLoading) return <p className="text-sm opacity-70">Loading…</p>;
  if (error || !data)
    return (
      <p className="rounded border border-brand/20 p-3 text-sm opacity-80">
        Proposed GL mappings appear here once a document is uploaded and classified.
      </p>
    );
  if (lines.length === 0) return <p className="text-sm opacity-70">No lines to map.</p>;

  const accountOptions = accounts ?? [];

  const confirmAllAutoMapped = async () => {
    for (const line of buckets.autoMapped) {
      const acct = accountOptions.find((a) => a.account_code === line.proposed_account_code);
      if (!line.proposed_account_code || !acct) continue;
      await confirm.mutateAsync({
        line_id: line.line_id,
        account_code: line.proposed_account_code,
        account_level: acct.level ?? "leaf",
        noi_placement: line.noi_placement ?? acct.noi_placement ?? "above",
        learn: true,
      });
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">GL mapping</span>
        <Chip tone="warn" label={`${buckets.needsReview.length} needs review`} />
        <Chip tone="info" label={`${buckets.autoMapped.length} auto-mapped`} />
        <Chip tone="muted" label={`${buckets.confirmed.length} confirmed`} />
        {buckets.autoMapped.length > 0 && (
          <button
            type="button"
            disabled={confirm.isPending || accountOptions.length === 0}
            onClick={confirmAllAutoMapped}
            className="ml-auto rounded border border-brand/30 px-3 py-1.5 text-sm disabled:opacity-50"
          >
            Confirm all auto-mapped
          </button>
        )}
      </div>

      {accountOptions.length === 0 && (
        <p className="rounded border border-brand/20 p-3 text-xs opacity-80">
          The GL chart isn’t loaded yet, so the account picker is empty.
        </p>
      )}

      <Bucket title="Needs review" lines={buckets.needsReview}>
        {(l) => <Row key={l.line_id} line={l} accounts={accountOptions} confirm={confirm} />}
      </Bucket>
      <Bucket title="Auto-mapped — confirm" lines={buckets.autoMapped}>
        {(l) => <Row key={l.line_id} line={l} accounts={accountOptions} confirm={confirm} />}
      </Bucket>
      <Bucket title="Confirmed" lines={buckets.confirmed}>
        {(l) => (
          <Row key={l.line_id} line={l} accounts={accountOptions} confirm={confirm} confirmed />
        )}
      </Bucket>
    </div>
  );
}

function Bucket({
  title,
  lines,
  children,
}: {
  title: string;
  lines: ReviewLine[];
  children: (l: ReviewLine) => React.ReactNode;
}) {
  if (lines.length === 0) return null;
  return (
    <div className="space-y-2">
      <p className="text-xs uppercase tracking-wide opacity-60">{title}</p>
      <div className="space-y-2">{lines.map((l) => children(l))}</div>
    </div>
  );
}

function Row({
  line,
  accounts,
  confirm,
  confirmed = false,
}: {
  line: ReviewLine;
  accounts: GlAccount[];
  confirm: ReturnType<typeof useConfirmMapping>;
  confirmed?: boolean;
}) {
  const [accountCode, setAccountCode] = useState(line.proposed_account_code ?? "");
  const selected = accounts.find((a) => a.account_code === accountCode);
  const [noi, setNoi] = useState<Noi>(
    (line.noi_placement as Noi) ?? selected?.noi_placement ?? "above",
  );

  const onPickAccount = (code: string) => {
    setAccountCode(code);
    const acct = accounts.find((a) => a.account_code === code);
    if (acct?.noi_placement) setNoi(acct.noi_placement);
  };

  const submit = () => {
    if (!selected) return;
    const level: Level = selected.level ?? "leaf";
    confirm.mutate({
      line_id: line.line_id,
      account_code: accountCode,
      account_level: level,
      noi_placement: noi,
      learn: true,
    });
  };

  return (
    <div className="rounded-md border border-brand/15 p-2.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-figure text-sm">{line.seller_source_line ?? "—"}</span>
        <span className="text-xs opacity-60">{fmtUsd(line.amount)}</span>
      </div>
      {!confirmed && line.map_confidence && (
        <p className="mt-0.5 text-xs opacity-60">
          suggested: {line.proposed_account_name ?? line.proposed_account_code ?? "none"} ·{" "}
          {line.map_confidence}
        </p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <select
          aria-label={`Account for ${line.seller_source_line ?? line.line_id}`}
          value={accountCode}
          onChange={(e) => onPickAccount(e.target.value)}
          className="min-w-[220px] rounded border border-brand/20 bg-surface px-2 py-1 text-sm"
        >
          <option value="">Choose GL…</option>
          {accounts.map((a) => (
            <option key={a.account_code} value={a.account_code}>
              {a.account_code} · {a.name}
            </option>
          ))}
        </select>
        <select
          aria-label={`NOI placement for ${line.seller_source_line ?? line.line_id}`}
          value={noi}
          onChange={(e) => setNoi(e.target.value as Noi)}
          className="rounded border border-brand/20 bg-surface px-2 py-1 text-sm"
        >
          {NOI_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={!accountCode || confirm.isPending}
          onClick={submit}
          className="rounded bg-brand px-3 py-1 text-sm text-surface disabled:opacity-50"
        >
          {confirmed ? "Re-confirm" : "Confirm"}
        </button>
        {confirmed && <span className="text-xs text-success">✓ confirmed</span>}
      </div>
    </div>
  );
}

function Chip({ tone, label }: { tone: "warn" | "info" | "muted"; label: string }) {
  const cls =
    tone === "warn"
      ? "bg-accent/15 text-accent-ink"
      : tone === "info"
        ? "bg-brand/10 text-brand"
        : "bg-ink/10 text-ink/70";
  return <span className={`rounded px-2 py-0.5 text-xs ${cls}`}>{label}</span>;
}
