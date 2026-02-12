"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { WSEvent } from "../lib/types";

interface UseWebSocketOptions {
  roomId: string;
  token: string | null;
  onMessage?: (event: WSEvent) => void;
  onTyping?: (userName: string) => void;
}

export function useWebSocket({
  roomId,
  token,
  onMessage,
  onTyping,
}: UseWebSocketOptions) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const retriesRef = useRef(0);
  const onMessageRef = useRef(onMessage);
  const onTypingRef = useRef(onTyping);

  onMessageRef.current = onMessage;
  onTypingRef.current = onTyping;

  const connect = useCallback(() => {
    if (!token || !roomId) return;

    const apiBase = process.env.NEXT_PUBLIC_API_URL || "";
    let wsUrl: string;
    if (apiBase) {
      // Convert http(s) URL to ws(s)
      wsUrl = apiBase.replace(/^http/, "ws") + `/api/v1/rooms/${roomId}/ws?token=${token}`;
    } else {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = window.location.host;
      wsUrl = `${protocol}//${host}/api/v1/rooms/${roomId}/ws?token=${token}`;
    }
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setConnected(true);
      retriesRef.current = 0;
    };

    ws.onmessage = (evt) => {
      try {
        const data: WSEvent = JSON.parse(evt.data);
        if (data.type === "typing" && data.user) {
          onTypingRef.current?.(data.user);
        } else if (data.type === "message") {
          onMessageRef.current?.(data);
        }
      } catch {
        // Ignore parse errors
      }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      // Exponential backoff reconnect
      const delay = Math.min(1000 * 2 ** retriesRef.current, 30000);
      retriesRef.current++;
      reconnectTimeoutRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, [token, roomId]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  const sendMessage = useCallback((content: string, replyToId?: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({ type: "message", content, reply_to_id: replyToId })
      );
    }
  }, []);

  const sendTyping = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "typing" }));
    }
  }, []);

  return { connected, sendMessage, sendTyping };
}
