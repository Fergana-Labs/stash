import { CodeBlock, H3, P, Title, Subtitle } from "../components";

export default function ConsumePage() {
  return (
    <>
      <Title>History & Files</Title>
      <Subtitle>
        Getting data into Stash. Push events via the CLI.
      </Subtitle>

      <H3>History</H3>
      <P>
        Each workspace has an append-only event log. Events are grouped by{" "}
        <code className="text-brand font-mono text-[13px]">agent_name</code> and{" "}
        <code className="text-brand font-mono text-[13px]">session_id</code>, giving you a
        conversation-like view of each agent session.
      </P>
      <CodeBlock>{`stash history push "Searched for auth best practices" \\
  --agent my-agent --type tool_use`}</CodeBlock>

      <H3>File uploads</H3>
      <P>
        Upload images, PDFs, and documents through the CLI or the image button in the
        notebook editor. Files are stored in S3-compatible storage (Cloudflare R2, AWS S3, or
        MinIO depending on your deployment).
      </P>
    </>
  );
}
