"use client";

import { useEffect, useState } from "react";
import pako from "pako";

type Props = {
  apiUrl: string;
  workspaceId: string;
  sessionId: string;
  accessToken: string;
};

type ContentBlock = {
  type: string;
  text?: string;
  name?: string;
};

type TranscriptLine = {
  type: string;
  message?: { content?: string | ContentBlock[] };
};

type Message = {
  role: "user" | "assistant";
  text: string;
  tools: string[];
};

function extractText(content: string | ContentBlock[] | undefined): string {
  if (!content) return "";
  if (typeof content === "string") return content;
  return content
    .filter((b) => b.type === "text" && b.text)
    .map((b) => b.text!)
    .join("\n");
}

function extractToolNames(content: string | ContentBlock[] | undefined): string[] {
  if (!content || typeof content === "string") return [];
  return content.filter((b) => b.type === "tool_use" && b.name).map((b) => b.name!);
}

export default function TranscriptViewer({ apiUrl, workspaceId, sessionId, accessToken }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [meta, setMeta] = useState<{ agent_name?: string; cwd?: string; uploaded_at?: string }>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const metaRes = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/transcripts/${sessionId}`,
        { headers: { Authorization: `Bearer ${accessToken}` } },
      );
      if (!metaRes.ok) {
        const detail = await metaRes.json().catch(() => ({}));
        setError(detail.detail || `HTTP ${metaRes.status}`);
        setLoading(false);
        return;
      }
      const metaData = await metaRes.json();
      setMeta(metaData);

      if (!metaData.download_url) {
        setError("No transcript content available");
        setLoading(false);
        return;
      }

      const contentRes = await fetch(metaData.download_url);
      const buf = new Uint8Array(await contentRes.arrayBuffer());
      let text: string;
      if (buf[0] === 0x1f && buf[1] === 0x8b) {
        text = new TextDecoder().decode(pako.ungzip(buf));
      } else {
        text = new TextDecoder().decode(buf);
      }

      const msgs: Message[] = [];
      for (const line of text.split("\n")) {
        if (!line.trim()) continue;
        const obj: TranscriptLine = JSON.parse(line);
        if (obj.type !== "user" && obj.type !== "assistant") continue;
        const t = extractText(obj.message?.content);
        const tools = extractToolNames(obj.message?.content);
        if (!t && tools.length === 0) continue;
        msgs.push({ role: obj.type as "user" | "assistant", text: t, tools });
      }
      setMessages(msgs);
      setLoading(false);
    })();
  }, [apiUrl, workspaceId, sessionId, accessToken]);

  if (error) {
    return (
      <div className="py-20 text-center">
        <h2 className="font-display text-[24px] font-bold text-ink">Transcript not found</h2>
        <p className="mt-2 text-dim">{error}</p>
      </div>
    );
  }

  return (
    <>
      {!loading && (
        <div className="mb-6 flex items-center gap-2 font-mono text-[12px] text-muted">
          {meta.agent_name && <span className="text-ink">{meta.agent_name}</span>}
          {meta.cwd && (
            <>
              <span>&middot;</span>
              <span>{meta.cwd}</span>
            </>
          )}
          {meta.uploaded_at && (
            <>
              <span>&middot;</span>
              <span>{new Date(meta.uploaded_at).toLocaleDateString()}</span>
            </>
          )}
        </div>
      )}

      <div className="space-y-3 pb-16">
        {loading &&
          Array.from({ length: 5 }).map((_, i) => (
            <div
              key={i}
              className={`h-14 animate-pulse rounded-xl bg-raised ${i % 2 === 0 ? "ml-auto w-2/3" : "w-3/4"}`}
            />
          ))}

        {messages.map((msg, i) => (
          <div key={i}>
            {msg.tools.length > 0 && (
              <div className={`mb-1 flex gap-1 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                {msg.tools.map((name, j) => (
                  <span
                    key={j}
                    className="rounded-md bg-agent-soft px-2 py-0.5 font-mono text-[11px] text-agent"
                  >
                    {name}
                  </span>
                ))}
              </div>
            )}
            {msg.text && (
              <div className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[80%] rounded-xl px-4 py-3 text-[14px] leading-[1.6] whitespace-pre-wrap ${
                    msg.role === "user"
                      ? "bg-inverted text-on-inverted"
                      : "bg-raised text-ink"
                  }`}
                >
                  {msg.text}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}
