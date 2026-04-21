import { Callout, Code, H3, P, Title, Subtitle } from "../components";

export default function CuratePage() {
  return (
    <>
      <Title>Wiki & Curation</Title>
      <Subtitle>
        Notebooks and tables form your wiki. The curation tool organizes raw data into
        structured, searchable wiki pages on demand.
      </Subtitle>

      <H3>Notebooks</H3>
      <P>
        Wiki-style markdown pages organized in folders. Supports{" "}
        <Code>{"[[Page Name]]"}</Code> wiki links with backlinks, page graph visualization, and
        semantic search. Rich-text editor with autosave.
      </P>

      <H3>Tables</H3>
      <P>
        Structured data with typed columns (text, number, date, select, relation).
        Import CSV files directly. Optionally enable row embeddings for semantic search —
        configure which columns to use in the table settings panel.
      </P>

      <H3>Curation tool</H3>
      <P>
        Curation runs automatically after agent sessions end (with a 24-hour cooldown), or on
        demand via the <Code>/curate</Code> slash command in Claude Code.
        It reads history, notebooks, and tables, then calls Claude to create structured content:
      </P>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {[
          { step: "01", title: "Category index pages", desc: "Creates top-level pages per topic with [[wiki links]] to content pages below." },
          { step: "02", title: "Content pages", desc: "Writes summaries of topics, discoveries, and research found in your data." },
          { step: "03", title: "Pattern cards", desc: "Surfaces recurring situations — patterns, anti-patterns, and decisions." },
          { step: "04", title: "Folder organization", desc: "Groups everything into folders by category so the wiki stays navigable." },
          { step: "05", title: "Merge and prune", desc: "Merges duplicates, updates stale content, deletes pages that no longer apply." },
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

      <Callout type="tip">
        Curation processes new data since the last run and writes organized wiki pages into
        the target notebook. Toggle auto-curation on or off in <Code>stash settings</Code>.
      </Callout>

      <H3>Wiki features</H3>
      <P>
        Notebook pages support <Code>{"[[Page Name]]"}</Code> wiki links. Type{" "}
        <Code>{"[["}</Code> in the editor for autocomplete. Backlinks appear at the bottom
        of each page showing which pages reference it. The page graph visualizes connections.
        Auto-index generates a table of contents with backlink counts for the whole notebook.
      </P>

      <H3>Semantic search</H3>
      <P>
        All notebook pages and table rows can be embedded (OpenAI text-embedding-3-small by
        default). Search by meaning, not just keywords — ask a question and get the most
        semantically relevant pages back.
      </P>
    </>
  );
}
