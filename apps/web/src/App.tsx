import { RouterProvider, createBrowserRouter } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { Approvals } from "./routes/Approvals";
import { DealDetail } from "./routes/DealDetail";
import { FeedbackTriage } from "./routes/FeedbackTriage";
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
      { path: "deals/:dealId", element: <DealDetail /> },
      {
        path: "mapping",
        element: (
          <Placeholder
            title="GL Mapping queue"
            note="Mapping review UI arrives in the next slice."
          />
        ),
      },
      { path: "approvals", element: <Approvals /> },
      { path: "feedback", element: <FeedbackTriage /> },
    ],
  },
]);

export function App() {
  return <RouterProvider router={router} />;
}
