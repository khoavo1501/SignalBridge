import type { Badge } from "../api/types";

const LABEL: Record<Badge, string> = {
  online: "online",
  stale: "dữ liệu trễ",
  offline: "offline",
};

const TIP: Record<Badge, string> = {
  online: "Broker đang kết nối và telemetry tươi trong ngưỡng",
  stale: "Broker còn kết nối nhưng telemetry vượt ngưỡng tươi (ràng buộc #5)",
  offline: "Mất kết nối broker (LWT) hoặc chưa từng thấy",
};

export default function StatusBadge({ badge }: { badge: Badge }) {
  return (
    <span className={`badge badge-${badge}`} title={TIP[badge]}>
      <i className="badge-dot" aria-hidden="true" />
      {LABEL[badge]}
    </span>
  );
}
