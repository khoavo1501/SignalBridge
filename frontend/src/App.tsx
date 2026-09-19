import { Activity } from "lucide-react";

export default function App() {
  return (
    <main style={{ padding: 48, fontFamily: "system-ui, sans-serif" }}>
      <h1>
        <Activity size={28} style={{ verticalAlign: "middle", marginRight: 8 }} />
        SignalBridge
      </h1>
      <p>Scaffold M0 — dashboard tổng quan sẽ có ở M6, chi tiết gateway ở M7, admin ở M8.</p>
    </main>
  );
}
