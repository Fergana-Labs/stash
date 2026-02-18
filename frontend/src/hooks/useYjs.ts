"use client";

import { useEffect, useRef, useState } from "react";
import * as Y from "yjs";
import { WebsocketProvider } from "y-websocket";

interface UseYjsOptions {
  workspaceId: string;
  fileId: string;
  token: string | null;
  userName?: string;
  userColor?: string;
}

export function useYjs({ workspaceId, fileId, token, userName, userColor }: UseYjsOptions) {
  const [connected, setConnected] = useState(false);
  const [synced, setSynced] = useState(false);
  const docRef = useRef<Y.Doc | null>(null);
  const providerRef = useRef<WebsocketProvider | null>(null);

  useEffect(() => {
    if (!token || !fileId || !workspaceId) return;

    const doc = new Y.Doc();
    docRef.current = doc;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}`;

    // y-websocket constructs URL as: serverUrl + '/' + roomname + '?params'
    // So we set serverUrl to path up to /files/{id} and roomname to 'yjs'
    const provider = new WebsocketProvider(
      `${wsUrl}/api/v1/workspaces/${workspaceId}/files/${fileId}`,
      "yjs",
      doc,
      {
        connect: true,
        params: { token },
      }
    );

    provider.on("status", ({ status }: { status: string }) => {
      setConnected(status === "connected");
    });

    provider.on("sync", (isSynced: boolean) => {
      setSynced(isSynced);
    });

    // Set awareness state
    if (userName) {
      provider.awareness.setLocalStateField("user", {
        name: userName,
        color: userColor || "#" + Math.floor(Math.random() * 16777215).toString(16).padStart(6, "0"),
      });
    }

    providerRef.current = provider;

    return () => {
      provider.disconnect();
      provider.destroy();
      doc.destroy();
      docRef.current = null;
      providerRef.current = null;
      setConnected(false);
      setSynced(false);
    };
  }, [token, fileId, workspaceId, userName, userColor]);

  return {
    doc: docRef.current,
    provider: providerRef.current,
    connected,
    synced,
  };
}
