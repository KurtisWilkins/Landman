import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./api/client";

interface Health {
  status: string;
  version: string;
  env: string;
}

/**
 * Phase-0 placeholder shell. It exists to prove the toolchain and the typed API client
 * wire up against the frozen contract. The responsive shell, screens, charts, gates, and
 * feedback widget are built by Stream D (design doc §6, §5.7–5.12) against `./api/types`.
 */
export function App() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["health"],
    queryFn: () => apiFetch<Health>("/health"),
  });

  return (
    <main className="min-h-screen bg-bone-paper text-forest-ink p-6">
      <h1 className="text-2xl font-semibold">RJourney Acquisitions</h1>
      <p className="mt-2 text-sm opacity-70">
        Phase-0 scaffold. Screens are built by Stream D against the generated contract types.
      </p>
      <section className="mt-6 rounded border border-forest/20 p-4">
        <h2 className="font-figure text-sm uppercase tracking-wide">API health</h2>
        {isLoading && <p>Checking…</p>}
        {error && <p className="text-red-700">API unreachable (expected until `make dev`).</p>}
        {data && (
          <p className="font-figure">
            {data.status} · v{data.version} · {data.env}
          </p>
        )}
      </section>
    </main>
  );
}
