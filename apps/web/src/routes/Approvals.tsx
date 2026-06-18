/**
 * Approvals (design doc §5.7): the admin review queue for gate-question suggestions.
 * Anyone may suggest; only an admin approves/declines here. Approved `add` items join the
 * live set going forward.
 */
import { useDecideSuggestion, useQuestionSuggestions } from "../api/hooks";

export function Approvals() {
  const { data, isLoading, error } = useQuestionSuggestions("pending");
  const decide = useDecideSuggestion();
  const suggestions = data ?? [];

  return (
    <section>
      <h1 className="text-2xl font-semibold">Approvals</h1>
      <p className="mt-1 text-sm opacity-70">Pending gate-question suggestions.</p>

      {isLoading && <p className="mt-4 text-sm opacity-70">Loading…</p>}
      {error && (
        <p className="mt-4 rounded border border-brand/20 p-3 text-sm opacity-80">
          Couldn’t load suggestions (admin access required).
        </p>
      )}

      {!isLoading && !error && suggestions.length === 0 && (
        <p className="mt-6 text-sm opacity-70">Nothing awaiting approval.</p>
      )}

      <ul className="mt-4 divide-y divide-brand/10">
        {suggestions.map((s) => (
          <li key={s.suggestion_id} className="py-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-xs uppercase tracking-wide opacity-60">
                  {s.phase} · {s.type}
                </div>
                <div className="font-medium">{s.text}</div>
                {s.rationale && <div className="mt-0.5 text-xs opacity-70">{s.rationale}</div>}
              </div>
              <div className="flex shrink-0 gap-2">
                <button
                  type="button"
                  onClick={() => decide.mutate({ id: s.suggestion_id, status: "approved" })}
                  disabled={decide.isPending}
                  className="rounded bg-brand px-3 py-1 text-sm text-paper disabled:opacity-50"
                >
                  Approve
                </button>
                <button
                  type="button"
                  onClick={() => decide.mutate({ id: s.suggestion_id, status: "declined" })}
                  disabled={decide.isPending}
                  className="rounded border border-brand/30 px-3 py-1 text-sm disabled:opacity-50"
                >
                  Decline
                </button>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
