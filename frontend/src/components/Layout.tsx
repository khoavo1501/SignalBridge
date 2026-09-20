import {
  Activity,
  CalendarClock,
  LayoutDashboard,
  Radar,
  Settings,
  type LucideIcon,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

import { useLive } from "../state/LiveContext";

interface NavItem {
  to: string;
  icon: LucideIcon;
  label: string;
  end?: boolean;
}

const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: "Tổng quan",
    items: [{ to: "/", icon: LayoutDashboard, label: "Bảng điều khiển", end: true }],
  },
  {
    section: "Hoạt động",
    items: [
      { to: "/events", icon: CalendarClock, label: "Sự kiện" },
      { to: "/diagnostics", icon: Radar, label: "Chẩn đoán" },
    ],
  },
  {
    section: "Quản trị",
    items: [{ to: "/admin", icon: Settings, label: "Gateway" }],
  },
];

export default function Layout() {
  const { connected, thresholdS } = useLive();
  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">SB</span>
          <span className="brand-name">SignalBridge</span>
          <span className="chip chip-dev">DEMO</span>
          <span className={`chip ${connected ? "chip-live" : "chip-dead"}`}>
            <i className="badge-dot" aria-hidden="true" />
            {connected ? "live" : "mất kết nối"}
          </span>
        </div>
        <div className="topbar-right">
          <Activity size={15} className="topbar-icon" aria-hidden="true" />
          <span className="topbar-meta">giám sát PLC realtime · ngưỡng stale {thresholdS} s</span>
        </div>
      </header>
      <div className="body">
        <nav className="sidebar" aria-label="Điều hướng chính">
          {NAV.map((group) => (
            <div key={group.section} className="nav-group">
              <p className="nav-section">{group.section}</p>
              {group.items.map(({ to, icon: Icon, label, end }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  className={({ isActive }) => `nav-item${isActive ? " nav-active" : ""}`}
                >
                  <Icon size={16} strokeWidth={1.8} aria-hidden="true" />
                  {label}
                </NavLink>
              ))}
            </div>
          ))}
          <div className="sidebar-foot">
            <p>
              giá trị analog hiển thị raw
              <br />
              (chờ công thức scale · Q2)
            </p>
          </div>
        </nav>
        <main className="main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
