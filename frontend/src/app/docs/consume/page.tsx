import { Callout, CodeBlock, CodeTabs, H3, P, ParamTable, Title, Subtitle } from "../components";

export default function ConsumePage() {
  return (
    <>
      <Title>History & Files</Title>
      <Subtitle>
        Getting data into Octopus. Push events via the CLI or REST API.
        Import bookmarks, files, and structured data.
      </Subtitle>

      <H3>History stores</H3>
      <P>
        History stores are append-only event logs. Events are grouped by{" "}
        <code className="text-brand font-mono text-[13px]">agent_name</code> and{" "}
        <code className="text-brand font-mono text-[13px]">session_id</code>, giving you a
        conversation-like view of each agent session. Push events via the CLI or REST API.
      </P>
      <CodeTabs tabs={[
        {
          label: "CLI",
          code: `octopus history push "Searched for auth best practices" \\
  --agent my-agent --type tool_use`,
        },
        {
          label: "curl",
          code: `curl -X POST https://getoctopus.com/api/v1/workspaces/{ws}/memory/{store}/events \\
  -H "Authorization: Bearer $API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"agent_name":"my-agent","event_type":"tool_use","content":"..."}'`,
        },
      ]} />

      <H3>File uploads</H3>
      <P>
        Upload images, PDFs, and documents through the REST API or the image button in the
        notebook editor. Files are stored in S3-compatible storage (Cloudflare R2, AWS S3, or
        MinIO depending on your deployment).
      </P>

      <H3>Import bookmarks</H3>
      <P>
        Export your Chrome or Firefox bookmarks as HTML, then import them in one command.
        Octopus scrapes each URL — articles via trafilatura, YouTube transcripts via
        youtube-transcript-api, PDF text via pymupdf — and stores each as a notebook page.
      </P>
      <CodeBlock>{`octopus import-bookmarks bookmarks.html`}</CodeBlock>
      <ParamTable params={[
        { name: "--notebook", type: "string", desc: 'Notebook name to write to (default: "Bookmarks")' },
        { name: "--skip-scrape", type: "flag", desc: "Import titles and URLs only — skip content extraction" },
        { name: "--dry-run", type: "flag", desc: "Preview what would be imported without writing anything" },
        { name: "--delay", type: "float", desc: "Seconds between scrape requests (default: 0.5)" },
        { name: "--ws", type: "UUID", desc: "Workspace ID — uses personal notebook if omitted" },
      ]} />
    </>
  );
}
