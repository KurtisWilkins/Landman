import { RouterProvider, createBrowserRouter } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { Pipeline } from "./routes/Pipeline";
import { Placeholder } from "./routes/Placeholder";

/**
 * App routes. The responsive shell wraps every page (so the "?" widget is always present).
 * Screens not yet built in this slice render a placeholder; they land in slice 3b against
 * the same generated contract types.
 */
const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Pipeline /> },
      {
        path: "deals/:dealId",
        element: (
          <Placeholder
            title="Deal detail"
            note="Pro forma / Comps / Gates / GL-Docs tabs arrive in the next frontend slice."
          />
        ),
      },
      {
        path: "mapping",
        element: (
          <Placeholder
            title="GL Mapping queue"
            note="Mapping review UI arrives in the next slice."
          />
        ),
      },
      {
        path: "approvals",
        element: (
          <Placeholder
            title="Approvals"
            note="Gate-question suggest→approve queue arrives in the next slice."
          />
        ),
      },
      {
        path: "feedback",
        element: (
          <Placeholder title="Feedback triage" note="Triage board arrives in the next slice." />
        ),
      },
    ],
  },
]);

export function App() {
  return <RouterProvider router={router} />;
}
