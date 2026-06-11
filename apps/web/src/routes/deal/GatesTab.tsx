/**
 * Gates tab (design doc §5.7): the gate checklist for the deal's phase. The gate-question
 * config is live; per-deal item statuses arrive with the assembled deal document. Until
 * then we show the active questions grouped by phase.
 */
import { useGateQuestions } from "../../api/hooks";

export function GatesTab() {
  const { data, isLoading, error } = useGateQuestions();
  const questions = data ?? [];

  if (isLoading) return <p className="text-sm opacity-70">Loading…</p>;
  if (error)
    return (
      <p className="rounded border border-forest/20 p-3 text-sm opacity-80">
        Couldn’t load gate questions.
      </p>
    );
  if (questions.length === 0)
    return <p className="text-sm opacity-70">No gate questions configured for this phase.</p>;

  return (
    <ul className="divide-y divide-forest/10">
      {questions.map((q) => (
        <li key={q.question_id} className="flex items-start gap-3 py-2 text-sm">
          <span
            aria-hidden
            className={`mt-1 h-2 w-2 shrink-0 rounded-full ${q.blocking ? "bg-brass-accent" : "bg-forest/30"}`}
          />
          <div>
            <div>{q.text}</div>
            <div className="text-xs uppercase tracking-wide opacity-60">
              {q.phase}
              {q.blocking ? " · blocking" : ""}
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
