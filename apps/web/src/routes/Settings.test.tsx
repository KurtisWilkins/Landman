import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Settings } from "./Settings";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

function renderSettings() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <Settings />
    </QueryClientProvider>,
  );
}

const ANTHROPIC = "Anthropic API key (PDF/OM extraction, AI)";
const LIST = [
  { key: "anthropic_api_key", label: ANTHROPIC, configured: false, source: null, hint: null },
  {
    key: "voyage_api_key",
    label: "Voyage embeddings key (GL mapping)",
    configured: true,
    source: "environment",
    hint: "6789",
  },
];

describe("Settings", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if ((init?.method ?? "GET") === "GET" && url.includes("/admin/integrations"))
          return jsonResponse(LIST);
        if (init?.method === "PUT")
          return jsonResponse({
            key: "anthropic_api_key",
            label: ANTHROPIC,
            configured: true,
            source: "database",
            hint: "WXYZ",
          });
        return jsonResponse([], 200);
      }),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("shows configured/missing status and saves a key (write-only)", async () => {
    const user = userEvent.setup();
    renderSettings();

    await waitFor(() => expect(screen.getByText("Missing")).toBeInTheDocument());
    expect(screen.getByText(/Configured \(…6789\)/)).toBeInTheDocument();

    await user.type(screen.getByLabelText(`${ANTHROPIC} value`), "sk-ant-newkeyWXYZ");
    await user.click(screen.getAllByRole("button", { name: "Save" })[0]);

    await waitFor(() => expect(screen.getByText("Saved.")).toBeInTheDocument());

    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    const put = fetchMock.mock.calls.find(([, i]) => (i as RequestInit)?.method === "PUT")!;
    expect(put[0]).toContain("/admin/integrations/anthropic_api_key");
    expect(JSON.parse((put[1] as RequestInit).body as string)).toEqual({
      value: "sk-ant-newkeyWXYZ",
    });
  });

  it("shows an admin-only notice on 403", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ error: { code: "forbidden", message: "no" } }, 403)),
    );
    renderSettings();
    await waitFor(() => expect(screen.getByText(/admin-only/i)).toBeInTheDocument());
  });
});
