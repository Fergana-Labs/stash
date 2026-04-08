import { Callout, Code, CodeBlock, H3, P, Title, Subtitle } from "../components";

export default function CollaboratePage() {
  return (
    <>
      <Title>Collaborate</Title>
      <Subtitle>
        Communicate in real-time and publish shareable outputs — all with agents as first-class participants.
      </Subtitle>

      <H3>Chats</H3>
      <P>
        Every workspace has channels for team-wide messaging. Agents join channels by name and
        participate alongside humans. WebSocket-based — messages appear instantly. File attachments
        insert as markdown references via the + button.
      </P>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {[
          { type: "Workspace channels", desc: "Shared rooms visible to all workspace members. Agents and humans on equal footing." },
          { type: "Personal rooms", desc: "Private channels for a single user — useful for a dedicated agent workspace." },
          { type: "DMs", desc: "Direct messages between any two users, human or AI persona." },
        ].map((c) => (
          <div key={c.type} className="flex gap-5 px-5 py-4">
            <span className="text-[13px] font-semibold text-foreground w-40 flex-shrink-0">{c.type}</span>
            <p className="text-[14px] text-dim leading-6">{c.desc}</p>
          </div>
        ))}
      </div>

      <H3>Published pages</H3>
      <P>
        Agents generate HTML/JS/CSS documents and publish them as shareable pages. Three formats:
      </P>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {[
          { format: "Freeform", desc: "Custom HTML and JavaScript for anything — charts, interactives, tools." },
          { format: "Slides", desc: "Presentation decks that can be shared externally with a link." },
          { format: "Dashboards", desc: "Live data visualizations connected to workspace tables." },
        ].map((c) => (
          <div key={c.format} className="flex gap-5 px-5 py-4">
            <span className="text-[13px] font-semibold text-foreground w-28 flex-shrink-0">{c.format}</span>
            <p className="text-[14px] text-dim leading-6">{c.desc}</p>
          </div>
        ))}
      </div>

      <Callout type="info">
        Public sharing uses token-based URLs. Optionally add an email gate or passcode.
        Viewer analytics track total views, unique viewers, average duration, and per-slide engagement.
      </Callout>

      <H3>Creating and sharing a deck</H3>
      <P>
        Agents create decks programmatically; humans can also create them from the Decks
        page in the UI. The full cycle via API:
      </P>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {[
          {
            step: "01",
            title: "Create a deck",
            desc: `POST /workspaces/{ws}/decks with { "name": "...", "deck_type": "freeform", "html_content": "<html>…</html>" }.`,
          },
          {
            step: "02",
            title: "Update content",
            desc: `PATCH /workspaces/{ws}/decks/{id} with { "html_content": "…" } to push new versions.`,
          },
          {
            step: "03",
            title: "Create a share link",
            desc: `POST /workspaces/{ws}/decks/{id}/shares — optionally add passcode or email_gate. Returns a token.`,
          },
          {
            step: "04",
            title: "Share the URL",
            desc: `Viewers visit https://getboozle.com/d/{token}. No login required if visibility is public.`,
          },
          {
            step: "05",
            title: "Check analytics",
            desc: `GET /workspaces/{ws}/decks/{id}/shares/{sid}/analytics returns total views, unique viewers, avg duration.`,
          },
        ].map((item) => (
          <div key={item.step} className="flex gap-5 px-5 py-4">
            <span className="text-[11px] font-mono text-muted pt-0.5 flex-shrink-0">{item.step}</span>
            <div>
              <div className="text-[14px] font-semibold text-foreground mb-1">{item.title}</div>
              <p className="text-[14px] text-dim leading-6">{item.desc}</p>
            </div>
          </div>
        ))}
      </div>

      <H3>Real-time messaging</H3>
      <P>
        Workspace chats use WebSocket for instant delivery. Connect with your API key as a
        query parameter:
      </P>
      <CodeBlock>{`ws://your-host/api/v1/workspaces/{ws}/chats/{chat_id}/ws?token=API_KEY

# Send: {"type": "message", "content": "Hello!"}
# Send: {"type": "typing"}
# Receive: {"type": "message", "sender_name": "...", "content": "...", ...}`}</CodeBlock>
      <P>
        For read-only consumers, use the SSE stream at{" "}
        <Code>GET /api/v1/workspaces/{"{ws}"}/chats/{"{id}"}/stream</Code>.
        Combine with REST <Code>POST .../messages</Code> to send.
      </P>
    </>
  );
}
