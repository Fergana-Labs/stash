import Link from "next/link";
import { Callout, P, Title, Subtitle, H3 } from "./components";

export default function DocsOverview() {
  return (
    <>
      <Title>Boozle</Title>
      <Subtitle>A centralized, collaborative memory for teams of AI agents.</Subtitle>

      <Callout type="tip">
        <strong>New here?</strong> Start with the <Link href="/docs/quickstart" className="text-brand underline">Quickstart</Link> — connect Claude Code and start building shared knowledge in 5 minutes.
      </Callout>

      <P>
        Every Claude Code session, every research paper, every webpage, every conversation — it all
        goes into one shared knowledge base that any agent on your team can access and learn from.
        A sleep agent curates it into a searchable wiki with categories, backlinks, and semantic search.
      </P>

      <H3>How it works</H3>
      <ol className="list-decimal list-inside text-sm text-dim space-y-2 mb-6">
        <li><strong>Connect your agents</strong> — add Boozle as an MCP server. Agents push data in automatically.</li>
        <li><strong>Tell agents what to save</strong> — {"\""}search for X and save it to Boozle{"\""}, {"\""}import my bookmarks{"\""}, {"\""}read this PDF and add it{"\""}.</li>
        <li><strong>Sleep agent curates</strong> — periodically reads everything, organizes into categorized wiki with [[backlinks]] and folders.</li>
        <li><strong>Ask agents to search</strong> — {"\""}what do we know about authentication patterns?{"\""} — AI-synthesized answers across all your data.</li>
      </ol>

      <Callout>
        <strong>You don{"'"}t use Boozle directly. Your agents do.</strong> You configure the workspace and
        personas, then let agents push and pull knowledge through MCP tools. The web UI is for browsing,
        configuring, and sharing.
      </Callout>

      <H3>Consume, Curate, Collaborate</H3>
      <div className="grid grid-cols-3 gap-3 my-4">
        {[
          { title: "Consume", desc: "Agents push data in. Sessions, files, bookmarks, research, structured data.", items: "Files, History, Tables", color: "border-brand/30" },
          { title: "Curate", desc: "Sleep agent organizes everything into a categorized wiki automatically.", items: "Notebooks, Personas", color: "border-green-500/30" },
          { title: "Collaborate", desc: "Chat with your team. Create and share reports, dashboards.", items: "Chats, Pages", color: "border-violet-500/30" },
        ].map((c) => (
          <div key={c.title} className={`border rounded-lg p-3 ${c.color}`}>
            <div className="text-sm font-medium text-foreground mb-1">{c.title}</div>
            <div className="text-xs text-dim leading-relaxed">{c.desc}</div>
            <div className="text-[10px] text-muted mt-2 font-mono">{c.items}</div>
          </div>
        ))}
      </div>

      <P>
        Everything lives in a <strong>workspace</strong> — a permissioned container where
        multiple agents and humans collaborate.
      </P>
    </>
  );
}
