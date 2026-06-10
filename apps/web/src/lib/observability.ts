/**
 * Frontend observability (design doc §7). Initializes Sentry tagged by release/build hash
 * when a DSN is configured, and always installs the console capture so the breadcrumb
 * buffer feeds bug reports — even before a DSN is set ([DECISION] C-30: provider/residency).
 */
import * as Sentry from "@sentry/react";
import { addBreadcrumb, installConsoleCapture } from "./telemetry";

export function initObservability(): void {
  installConsoleCapture();
  const dsn = import.meta.env.VITE_SENTRY_DSN as string | undefined;
  if (!dsn) return; // no-op without a DSN; telemetry buffers still work
  Sentry.init({
    dsn,
    release: (import.meta.env.VITE_RELEASE as string | undefined) ?? undefined,
    environment: (import.meta.env.VITE_SENTRY_ENVIRONMENT as string | undefined) ?? "local",
    tracesSampleRate: 0.1,
    sendDefaultPii: false, // never ship PII/financials to the tracker
  });
}

/** Record a navigation breadcrumb (mirrors Sentry's, and feeds the widget). */
export function trackNavigation(route: string): void {
  addBreadcrumb("navigation", route);
}
