import { Callout, Code, H3, P, Title, Subtitle } from "../components";

export default function CuratePage() {
  return (
    <>
      <Title>Curate</Title>
      <Subtitle>The sleep agent turns raw data into structured knowledge.</Subtitle>

      <H3>Sleep agent</H3>
      <P>
        A background worker running every N minutes (configurable, default 30). It reads
        newly ingested data and calls Claude to organize it:
      </P>
      <ul className="list-disc list-inside text-sm text-dim mb-3 space-y-1 ml-1">
        <li>Creates <strong>category index pages</strong> with [[wiki links]]</li>
        <li>Writes <strong>content pages</strong> summarizing topics</li>
        <li>Creates <strong>pattern cards</strong> for recurring situations</li>
        <li>Organizes everything into <strong>folders</strong> by category</li>
        <li>Merges duplicates, deletes stale content</li>
      </ul>

      <Callout type="tip">
        <strong>Persona = sleep agent + notebook.</strong> Each persona watches workspace histories
        (optionally filtered by agent_name) and curates what it finds into its personal notebook.
        Configure via Personas page or the API.
      </Callout>

      <H3>Configuration</H3>
      <P>Per-persona settings:</P>
      <ul className="list-disc list-inside text-sm text-dim mb-3 space-y-1 ml-1">
        <li><strong>Workspaces</strong> — which workspaces to watch</li>
        <li><strong>Agent name filter</strong> — which agent_name values to include (empty = all)</li>
        <li><strong>Sources</strong> — history, notebooks, tables</li>
        <li><strong>Interval</strong> — minutes between curation cycles</li>
        <li><strong>Model</strong> — which Claude model to use</li>
      </ul>

      <H3>Wiki features</H3>
      <P>
        Notebook pages support <Code>{"[[Page Name]]"}</Code> wiki links. Type <Code>{"[["}</Code> in
        the editor for autocomplete. Backlinks appear at the bottom of each page. The page graph
        visualizes connections. Auto-index generates a table of contents with backlink counts.
      </P>

      <H3>Semantic search</H3>
      <P>
        All notebook pages and table rows can be embedded (OpenAI text-embedding-3-small by
        default). Search by meaning, not just keywords.
      </P>
    </>
  );
}
