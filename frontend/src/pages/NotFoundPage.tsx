import { Compass } from "lucide-react";
import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="main-inner">
      <div className="empty-box" style={{ padding: "64px 24px", textAlign: "center" }}>
        <Compass size={28} className="amber" aria-hidden="true" />
        <h1 className="page-title" style={{ marginTop: 12 }}>
          Không tìm thấy trang
        </h1>
        <p className="dim">
          Đường dẫn không tồn tại trong SignalBridge. Có thể gateway đã bị xóa (M8 sẽ thêm quản lý).
        </p>
        <p style={{ marginTop: 16 }}>
          <Link to="/" className="btn" style={{ textDecoration: "none" }}>
            Về bảng điều khiển
          </Link>
        </p>
      </div>
    </div>
  );
}
