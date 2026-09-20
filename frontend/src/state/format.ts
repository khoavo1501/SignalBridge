export function fmtNum(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("vi-VN");
}

export function fmtClock(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("vi-VN", { hour12: false });
}

export function fmtAgo(iso: string | null | undefined, nowMs: number): string {
  if (!iso) return "chưa có";
  const s = Math.max(0, Math.round((nowMs - Date.parse(iso)) / 1000));
  if (s < 60) return `${s} s trước`;
  if (s < 3600) return `${Math.floor(s / 60)} ph trước`;
  return `${Math.floor(s / 3600)} h trước`;
}
