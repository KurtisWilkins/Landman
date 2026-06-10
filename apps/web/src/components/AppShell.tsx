/**
 * Responsive shell (design doc §6): left rail on desktop, bottom tab bar on mobile —
 * identical destinations, mobile-first. The "?" feedback widget lives here so it appears on
 * every page. No browser storage; navigation state is the URL.
 */
import { NavLink, Outlet } from "react-router-dom";
import { FeedbackWidget } from "./FeedbackWidget";
import { DESTINATIONS } from "./nav";

function linkClass(isActive: boolean): string {
  return [
    "flex items-center gap-2 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brass-accent",
    isActive ? "bg-forest text-bone-paper" : "text-forest-ink hover:bg-bone",
  ].join(" ");
}

export function AppShell() {
  return (
    <div className="min-h-screen bg-bone-paper text-forest-ink">
      {/* Left rail — desktop */}
      <nav
        aria-label="Primary"
        className="fixed inset-y-0 left-0 hidden w-48 flex-col gap-1 border-r border-forest/15 bg-bone-paper p-3 md:flex"
      >
        <div className="mb-4 px-2 font-figure text-sm uppercase tracking-wide">RJourney</div>
        {DESTINATIONS.map((d) => (
          <NavLink
            key={d.to}
            to={d.to}
            end={d.to === "/"}
            className={({ isActive }) => linkClass(isActive)}
          >
            {d.label}
          </NavLink>
        ))}
      </nav>

      {/* Content */}
      <main className="px-4 pb-24 pt-4 md:ml-48 md:pb-8">
        <Outlet />
      </main>

      {/* Bottom tab bar — mobile */}
      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-40 flex border-t border-forest/15 bg-bone-paper md:hidden"
      >
        {DESTINATIONS.map((d) => (
          <NavLink
            key={d.to}
            to={d.to}
            end={d.to === "/"}
            className={({ isActive }) =>
              `flex flex-1 flex-col items-center py-3 text-xs ${
                isActive ? "text-forest" : "text-forest-ink/70"
              }`
            }
          >
            {d.short}
          </NavLink>
        ))}
      </nav>

      <FeedbackWidget />
    </div>
  );
}
