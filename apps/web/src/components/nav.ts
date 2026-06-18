/** Primary navigation destinations, shared by the desktop rail and the mobile tab bar. */
export interface Destination {
  to: string;
  label: string;
  short: string;
}

export const DESTINATIONS: Destination[] = [
  { to: "/", label: "Pipeline", short: "Pipe" },
  { to: "/mapping", label: "GL Mapping", short: "Map" },
  { to: "/promote", label: "Promote", short: "Promo" },
  { to: "/approvals", label: "Approvals", short: "Appr" },
  { to: "/feedback", label: "Feedback", short: "Feed" },
  { to: "/settings", label: "Settings", short: "Set" },
];
