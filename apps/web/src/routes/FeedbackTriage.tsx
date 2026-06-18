/**
 * Feedback triage board (design doc §5.11): the admin queue over submitted feedback. Set
 * status as the item moves toward `ready`, then dispatch it to Claude Code (§5.12). No
 * auto-merge — dispatch only opens a GitHub issue for a human-reviewed PR.
 */
import { useState } from "react";
import { useDispatchFeedback, useFeedbackQueue, usePatchFeedback } from "../api/hooks";
import type { components } from "../api/types";

type FeedbackStatus = components["schemas"]["FeedbackStatus"];

const STATUSES: FeedbackStatus[] = [
  "new",
  "triaged",
  "needs_detail",
  "ready",
  "dispatched",
  "in_progress",
  "deployed",
  "closed",
  "declined",
];

export function FeedbackTriage() {
  const [filter, setFilter] = useState<FeedbackStatus | "">("");
  const { data, isLoading, error } = useFeedbackQueue(filter ? { status: filter } : undefined);
  const patch = usePatchFeedback();
  const dispatch = useDispatchFeedback();
  const items = data ?? [];

  return (
    <section>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Feedback triage</h1>
        <label className="text-sm">
          <span className="sr-only">Filter by status</span>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as FeedbackStatus | "")}
            className="rounded border border-brand/20 bg-white px-2 py-1 text-sm"
          >
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      </div>

      {isLoading && <p className="mt-4 text-sm opacity-70">Loading…</p>}
      {error && (
        <p className="mt-4 rounded border border-brand/20 p-3 text-sm opacity-80">
          Couldn’t load the triage queue (admin access required).
        </p>
      )}
      {!isLoading && !error && items.length === 0 && (
        <p className="mt-6 text-sm opacity-70">No feedback in this view.</p>
      )}

      <ul className="mt-4 divide-y divide-brand/10">
        {items.map((f) => (
          <li key={f.feedback_id} className="py-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-xs uppercase tracking-wide opacity-60">
                  {f.type}
                  {f.page_route ? ` · ${f.page_route}` : ""}
                </div>
                <div className="font-medium">{f.title ?? f.description ?? f.feedback_id}</div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <select
                  aria-label={`Status for ${f.feedback_id}`}
                  value={f.status}
                  onChange={(e) =>
                    patch.mutate({
                      id: f.feedback_id,
                      patch: { status: e.target.value as FeedbackStatus },
                    })
                  }
                  className="rounded border border-brand/20 bg-white px-2 py-1 text-xs"
                >
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => dispatch.mutate({ id: f.feedback_id, body: {} })}
                  disabled={f.status !== "ready" || dispatch.isPending}
                  title={f.status !== "ready" ? "Item must be 'ready' to dispatch" : undefined}
                  className="rounded bg-accent px-3 py-1 text-xs text-brand disabled:opacity-40"
                >
                  Dispatch
                </button>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
