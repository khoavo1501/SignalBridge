import { BrowserRouter, Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import { LiveProvider } from "./state/LiveContext";
import DashboardPage from "./pages/DashboardPage";
import DiagnosticsPage from "./pages/DiagnosticsPage";
import EventsPage from "./pages/EventsPage";
import GatewayDetailPage from "./pages/GatewayDetailPage";
import SlaveDetailPage from "./pages/SlaveDetailPage";

export default function App() {
  return (
    <LiveProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/events" element={<EventsPage />} />
            <Route path="/diagnostics" element={<DiagnosticsPage />} />
            <Route path="/gateways/:id" element={<GatewayDetailPage />} />
            <Route path="/gateways/:id/slaves/:addr" element={<SlaveDetailPage />} />
            {/* M8: /admin */}
          </Route>
        </Routes>
      </BrowserRouter>
    </LiveProvider>
  );
}
