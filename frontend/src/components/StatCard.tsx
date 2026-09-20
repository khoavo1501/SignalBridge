import type { ReactNode } from "react";

export default function StatCard({
  label,
  value,
  sub,
  tone = "amber",
  icon,
}: {
  label: string;
  value: ReactNode;
  sub?: string;
  tone?: "amber" | "ok" | "bad";
  icon?: ReactNode;
}) {
  return (
    <div className="stat-card">
      <div className="stat-top">
        <span className="stat-label">{label}</span>
        {icon ? <span className="stat-icon">{icon}</span> : null}
      </div>
      <p className={`stat-value stat-${tone}`}>{value}</p>
      {sub ? <p className="stat-sub">{sub}</p> : null}
    </div>
  );
}
