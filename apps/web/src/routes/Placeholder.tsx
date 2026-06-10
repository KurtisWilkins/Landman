/**
 * Placeholder for screens landing in the next frontend slice (3b): GL mapping queue,
 * Approvals, Feedback triage, and Deal detail tabs. Keeps navigation whole today.
 */
export function Placeholder({ title, note }: { title: string; note: string }) {
  return (
    <section>
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="mt-4 rounded border border-forest/20 p-3 text-sm opacity-80">{note}</p>
    </section>
  );
}
