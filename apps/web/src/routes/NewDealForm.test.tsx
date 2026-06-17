import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NewDealForm } from "./NewDealForm";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

function renderForm(onCreated = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <NewDealForm onCreated={onCreated} onCancel={vi.fn()} />
    </QueryClientProvider>,
  );
  return { onCreated };
}

describe("NewDealForm", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        if ((init?.method ?? "GET") === "POST") {
          return jsonResponse({ deal_id: "dl_new123", metadata: {}, market: { rings: [] } }, 201);
        }
        return jsonResponse([], 200);
      }),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("submits the entered fields and reports the new deal id", async () => {
    const user = userEvent.setup();
    const { onCreated } = renderForm();

    await user.type(screen.getByLabelText("Property name"), "Cedar Ridge RV");
    await user.selectOptions(screen.getByLabelText("Property type"), "campground");
    await user.type(screen.getByLabelText("City"), "Austin");
    await user.type(screen.getByLabelText("Ask price (USD)"), "4500000");
    await user.click(screen.getByRole("button", { name: "Create deal" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("dl_new123"));

    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    const [url, init] = fetchMock.mock.calls.at(-1)!;
    expect(url).toContain("/deals");
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body).toMatchObject({
      name: "Cedar Ridge RV",
      property_type: "campground",
      address: { city: "Austin" },
      ask_price: "4500000", // money sent as a string, never a float
    });
  });

  it("disables submit until a name is entered", () => {
    renderForm();
    expect(screen.getByRole("button", { name: "Create deal" })).toBeDisabled();
  });
});
