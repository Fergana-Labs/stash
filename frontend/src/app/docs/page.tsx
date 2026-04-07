import { Callout, P, Title, Subtitle, H3 } from "./components";

export default function DocsOverview() {
  return (
    <>
      <Title>Boozle</Title>
      <Subtitle>The auto-curating knowledge base for AI-augmented teams.</Subtitle>

      <Callout type="tip">
        <strong>New here?</strong> Start with the <a href="/docs/quickstart" className="text-brand underline">Quickstart</a> — three commands to import your bookmarks and start searching.
      </Callout>

      <P>
        Throw in your bookmarks, Claude Code sessions, PDFs, YouTube videos, articles.
        A sleep agent curates it all into a searchable wiki with backlinks and semantic search.
        You never write wiki entries manually.
      </P>

      <H3>Consume, Curate, Collaborate</H3>
      <div className="grid grid-cols-3 gap-3 my-4">
        {[
          { title: "Consume", desc: "Throw stuff in. Bookmarks, files, agent history, structured data.", items: "Files, History, Tables", color: "border-brand/30" },
          { title: "Curate", desc: "Sleep agent organizes data into a categorized wiki automatically.", items: "Notebooks, Personas", color: "border-green-500/30" },
          { title: "Collaborate", desc: "Chat with your team. Create and share pages, reports.", items: "Chats, Pages", color: "border-violet-500/30" },
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
        multiple agents and people collaborate. Each workspace has its own files, notebooks,
        tables, chats, and history.
      </P>
    </>
  );
}
