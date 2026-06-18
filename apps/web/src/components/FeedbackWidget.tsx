/**
 * Floating "?" feedback widget (design doc §5.10). On every authenticated page, bottom-right
 * on desktop and thumb-reachable on mobile. Three actions: request a feature, report a bug,
 * ask a question. Context is captured silently on submit; the user types only a description.
 * No browser storage.
 */
import { useState } from "react";
import { useLocation } from "react-router-dom";
import { useSubmitFeedback } from "../api/hooks";
import type { components } from "../api/types";
import { captureContext } from "../lib/context";

type FeedbackType = components["schemas"]["FeedbackType"];

const ACTIONS: { type: FeedbackType; label: string }[] = [
  { type: "feature", label: "Request a feature" },
  { type: "bug", label: "Report a bug" },
  { type: "question", label: "Ask a question" },
];

/** Extract a acquisition id from a `/acquisitions/:id...` route, if present. */
function acquisitionIdFromRoute(pathname: string): string | null {
  const m = /^\/acquisitions\/([^/]+)/.exec(pathname);
  return m ? m[1] : null;
}

export function FeedbackWidget() {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [type, setType] = useState<FeedbackType>("bug");
  const [description, setDescription] = useState("");
  const submit = useSubmitFeedback();

  function reset() {
    setOpen(false);
    setDescription("");
    setType("bug");
    submit.reset();
  }

  function onSubmit() {
    const context = captureContext({
      route: location.pathname,
      acquisitionId: acquisitionIdFromRoute(location.pathname),
      includeBugDetail: type === "bug",
    });
    submit.mutate({ type, description, context }, { onSuccess: () => reset() });
  }

  return (
    <>
      <button
        type="button"
        aria-label="Send feedback"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="fixed bottom-20 right-4 z-50 h-12 w-12 rounded-full bg-accent text-brand shadow-lg focus:outline-none focus:ring-2 focus:ring-ink md:bottom-6"
      >
        <span className="text-xl font-semibold">?</span>
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Feedback"
          className="fixed bottom-36 right-4 z-50 w-80 max-w-[90vw] rounded-lg border border-brand/20 bg-paper p-4 shadow-xl md:bottom-20"
        >
          <fieldset className="mb-3">
            <legend className="sr-only">Feedback type</legend>
            <div className="flex gap-1">
              {ACTIONS.map((a) => (
                <button
                  key={a.type}
                  type="button"
                  aria-pressed={type === a.type}
                  onClick={() => setType(a.type)}
                  className={`flex-1 rounded px-2 py-1 text-xs ${
                    type === a.type ? "bg-brand text-paper" : "bg-surface text-ink"
                  }`}
                >
                  {a.label}
                </button>
              ))}
            </div>
          </fieldset>
          <label htmlFor="fb-desc" className="sr-only">
            Description
          </label>
          <textarea
            id="fb-desc"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What happened / what would help?"
            rows={4}
            className="w-full rounded border border-brand/20 bg-white p-2 text-sm"
          />
          {submit.isError && (
            <p className="mt-1 text-xs text-danger">Could not send — try again.</p>
          )}
          <div className="mt-3 flex justify-end gap-2">
            <button type="button" onClick={reset} className="px-3 py-1 text-sm">
              Cancel
            </button>
            <button
              type="button"
              onClick={onSubmit}
              disabled={!description.trim() || submit.isPending}
              className="rounded bg-brand px-3 py-1 text-sm text-paper disabled:opacity-50"
            >
              {submit.isPending ? "Sending…" : "Send"}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
