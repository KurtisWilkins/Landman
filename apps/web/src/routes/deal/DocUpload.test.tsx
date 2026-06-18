import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DocUpload } from "./DocUpload";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

function renderUpload() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <DocUpload dealId="dl_1" />
    </QueryClientProvider>,
  );
}

describe("DocUpload", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          { status: "loaded", sheet_type: "pnl", financial_lines_loaded: 12, units_loaded: 0 },
          202,
        ),
      ),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("uploads the chosen file as multipart and shows the load result", async () => {
    const user = userEvent.setup();
    renderUpload();

    const file = new File(["Description,Amount\nRent,1000\n"], "pnl.csv", { type: "text/csv" });
    await user.upload(screen.getByLabelText("Source document"), file);
    await user.click(screen.getByRole("button", { name: "Upload" }));

    await waitFor(() => expect(screen.getByText(/12/)).toBeInTheDocument());
    expect(screen.getByText(/pnl/)).toBeInTheDocument();

    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    const [url, init] = fetchMock.mock.calls.at(-1)!;
    expect(url).toContain("/deals/dl_1/documents");
    expect((init as RequestInit).method).toBe("POST");
    // Multipart: body is FormData and no JSON content-type was forced.
    expect((init as RequestInit).body).toBeInstanceOf(FormData);
  });

  it("disables upload until a file is chosen", () => {
    renderUpload();
    expect(screen.getByRole("button", { name: "Upload" })).toBeDisabled();
  });
});
