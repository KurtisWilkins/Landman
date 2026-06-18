/**
 * Silent context capture for feedback submissions (design doc §5.10).
 *
 * Gathers route + acquisition, app version/build, browser, OS, viewport, and — for bug reports —
 * breadcrumbs, captured console errors, and the last API error. Shapes to the API's
 * `FeedbackContext`. No browser storage is read or written.
 */
import type { components } from "../api/types";
import { getBreadcrumbs, getConsoleErrors, getLastApiError } from "./telemetry";

type FeedbackContext = components["schemas"]["FeedbackContext"];

const APP_VERSION = (import.meta.env.VITE_RELEASE as string | undefined) ?? "dev";

function parseUserAgent(ua: string): { browser: string; os: string; device: string } {
  const browser = /Edg/.test(ua)
    ? "Edge"
    : /Chrome/.test(ua)
      ? "Chrome"
      : /Safari/.test(ua)
        ? "Safari"
        : /Firefox/.test(ua)
          ? "Firefox"
          : "Unknown";
  const os = /Windows/.test(ua)
    ? "Windows"
    : /Mac OS/.test(ua)
      ? "macOS"
      : /Android/.test(ua)
        ? "Android"
        : /(iPhone|iPad|iOS)/.test(ua)
          ? "iOS"
          : /Linux/.test(ua)
            ? "Linux"
            : "Unknown";
  const device = /Mobi|Android|iPhone/.test(ua) ? "mobile" : "desktop";
  return { browser, os, device };
}

export function captureContext(args: {
  route: string;
  acquisitionId?: string | null;
  includeBugDetail: boolean;
}): FeedbackContext {
  const ua = typeof navigator !== "undefined" ? navigator.userAgent : "";
  const { browser, os, device } = parseUserAgent(ua);
  const viewport =
    typeof window !== "undefined" ? `${window.innerWidth}x${window.innerHeight}` : undefined;

  const ctx: FeedbackContext = {
    page_route: args.route,
    acquisition_id: args.acquisitionId ?? null,
    app_version: APP_VERSION,
    browser,
    os,
    device,
    viewport,
  };

  // Bugs additionally carry the diagnostic buffers; features/questions stay lean.
  if (args.includeBugDetail) {
    ctx.breadcrumbs = getBreadcrumbs() as unknown as FeedbackContext["breadcrumbs"];
    ctx.console_errors = getConsoleErrors() as unknown as FeedbackContext["console_errors"];
    ctx.last_api_error = (getLastApiError() ?? undefined) as FeedbackContext["last_api_error"];
  }
  return ctx;
}
