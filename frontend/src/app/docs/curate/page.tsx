import { Callout, Code, H3, P, Title, Subtitle } from "../components";

export default function CuratePage() {
  return (
    <>
      <Title>Curate</Title>
      <Subtitle>
        The sleep agent reads everything your agents produce and organizes it
        into a structured, searchable wiki — automatically.
      </Subtitle>

      <H3>How the sleep agent works</H3>
      <P>
        A background worker runs on a configurable schedule (default every 30 minutes).
        It reads newly ingested data from history stores, then calls Claude to organize it:
      </P>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {[
          { step: "01", title: "Category index pages", desc: "Creates top-level pages per topic with [[wiki links]] to content pages below." },
          { step: "02", title: "Content pages", desc: "Writes summaries of topics, discoveries, and research the agent has seen." },
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
        <strong>Persona = sleep agent + notebook.</strong> Each persona watches workspace history
        stores (optionally filtered by agent name) and curates what it finds into its personal
        notebook. Configure via the Personas page or the API.
      </Callout>

      <H3>Configuration</H3>
      <P>
        Each persona has its own sleep agent config. Update via the Personas page or the API
        (<Code>PUT /personas/me/sleep-config</Code>):
      </P>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {[
          { field: "workspace_ids", type: "uuid[]", desc: "Which workspaces to watch. Leave empty to watch all workspaces you're a member of." },
          { field: "agent_name_filter", type: "string[]", desc: "Only process history events from these agent names. Leave empty to include all agents." },
          { field: "curation_sources", type: "string[]", desc: 'Resource types to read from: "history", "notebooks", "tables". Default: ["history"].' },
          { field: "interval_minutes", type: "number", desc: "Minutes between curation cycles. Default: 60. Minimum: 5." },
          { field: "curation_model", type: "string", desc: "Claude model for writing notebook pages. Default: claude-3-5-haiku-20241022." },
          { field: "monologue_model", type: "string", desc: "Claude model for internal reasoning (pattern scoring). Defaults to curation_model." },
          { field: "max_pattern_cards", type: "number", desc: "Maximum pattern cards to keep in the persona notebook. Older cards are pruned. Default: 500." },
          { field: "monologue_batch_size", type: "number", desc: "Number of history events processed per curation run. Default: 20." },
          { field: "curation_rules", type: "string", desc: "Optional free-text instructions appended to the sleep agent's system prompt. Use to specialise curation for a domain." },
          { field: "enabled", type: "bool", desc: "Toggle the agent on/off without deleting config. Default: true." },
        ].map((item) => (
          <div key={item.field} className="flex gap-5 px-5 py-4">
            <span className="text-[13px] font-semibold text-foreground font-mono w-52 flex-shrink-0">{item.field}</span>
            <span className="text-[11px] font-mono text-muted w-16 flex-shrink-0 pt-0.5">{item.type}</span>
            <p className="text-[14px] text-dim leading-6">{item.desc}</p>
          </div>
        ))}
      </div>

      <Callout type="tip">
        Trigger a manual run without waiting for the next interval:{" "}
        <Code>POST /personas/me/sleep/trigger</Code>. Useful for testing config changes.
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
