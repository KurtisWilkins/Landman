import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppShell } from "./AppShell";
import { DESTINATIONS } from "./nav";

describe("AppShell", () => {
  it("renders all primary destinations (rail + tab bar) and the feedback widget", () => {
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<div>home</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    for (const d of DESTINATIONS) {
      // Each destination appears in both the desktop rail and the mobile tab bar.
      expect(screen.getAllByRole("link", { name: new RegExp(d.label) }).length).toBeGreaterThan(0);
    }
    expect(screen.getByRole("button", { name: /send feedback/i })).toBeInTheDocument();
  });
});
