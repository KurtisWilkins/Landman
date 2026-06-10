import { beforeEach, describe, expect, it } from "vitest";
import {
  _resetTelemetry,
  addBreadcrumb,
  getBreadcrumbs,
  getLastApiError,
  installConsoleCapture,
  setLastApiError,
} from "./telemetry";

describe("telemetry", () => {
  beforeEach(() => _resetTelemetry());

  it("records breadcrumbs and caps the ring buffer", () => {
    for (let i = 0; i < 60; i++) addBreadcrumb("test", `crumb ${i}`);
    const crumbs = getBreadcrumbs();
    expect(crumbs.length).toBe(50);
    expect(crumbs.at(-1)?.message).toBe("crumb 59");
  });

  it("holds the last API error", () => {
    expect(getLastApiError()).toBeNull();
    setLastApiError({ status: 500, code: "internal_error" });
    expect(getLastApiError()).toMatchObject({ status: 500 });
  });

  it("captures console.error into breadcrumbs", () => {
    installConsoleCapture();
    console.error("boom");
    expect(getBreadcrumbs().some((c) => c.category === "console")).toBe(true);
  });
});
