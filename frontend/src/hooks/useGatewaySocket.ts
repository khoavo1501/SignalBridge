import { useEffect, useRef, useState } from "react";

import type { WsFrame } from "../api/types";

const MAX_BACKOFF_MS = 30_000;

// Reconnect exponential backoff §4.2 (plan M6: 1s → 2s → 4s ... cap 30s, reset khi mở lại)
// Trả về trạng thái kết nối để header hiển thị; frame đẩy qua onFrame (giữ ref để không nối lại mỗi render)
export function useGatewaySocket(onFrame: (frame: WsFrame) => void): boolean {
  const [connected, setConnected] = useState(false);
  const cbRef = useRef(onFrame);
  cbRef.current = onFrame;

  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: number | undefined;
    let attempt = 0;
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => {
        attempt = 0;
        setConnected(true);
      };
      ws.onmessage = (ev: MessageEvent) => {
        if (typeof ev.data !== "string") return;
        try {
          cbRef.current(JSON.parse(ev.data) as WsFrame);
        } catch {
          // frame hỏng — bỏ qua, phiên không dừng
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (disposed) return;
        const delay = Math.min(1000 * 2 ** attempt, MAX_BACKOFF_MS);
        attempt += 1;
        timer = window.setTimeout(connect, delay);
      };
      ws.onerror = () => ws?.close();
    };

    connect();
    return () => {
      disposed = true;
      if (timer !== undefined) window.clearTimeout(timer);
      if (ws !== null) {
        ws.onclose = null; // đóng chủ động (unmount/tab tắt) không reconnect
        ws.close();
      }
    };
  }, []);

  return connected;
}
