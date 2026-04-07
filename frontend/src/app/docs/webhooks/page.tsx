import { CodeBlock, H3, P, ParamTable, Title, Subtitle } from "../components";

export default function WebhooksPage() {
  return (
    <>
      <Title>Webhooks</Title>
      <Subtitle>Subscribe to workspace events with HMAC-SHA256 signed delivery.</Subtitle>

      <P>One webhook per user per workspace. Events are delivered via HTTP POST.</P>

      <H3>Event types</H3>
      <ParamTable params={[
        { name: "chat.message", type: "event", desc: "New message in a chat" },
        { name: "memory.event", type: "event", desc: "New history event pushed" },
        { name: "table.row_created", type: "event", desc: "Table row created" },
        { name: "table.row_updated", type: "event", desc: "Table row updated" },
        { name: "table.row_deleted", type: "event", desc: "Table row deleted" },
        { name: "table.rows_batch_created", type: "event", desc: "Batch of rows created" },
        { name: "table.rows_batch_updated", type: "event", desc: "Batch of rows updated" },
      ]} />

      <H3>Setup</H3>
      <CodeBlock>{`POST /workspaces/{ws}/webhooks
{
  "url": "https://your-server.com/webhook",
  "secret": "optional-hmac-secret",
  "event_filter": ["table.row_created", "chat.message"]
}`}</CodeBlock>

      <H3>Payload format</H3>
      <CodeBlock>{`{
  "event": "table.row_created",
  "workspace_id": "uuid",
  "data": {
    "table_id": "uuid",
    "row": { "id": "uuid", "data": {...}, ... }
  }
}`}</CodeBlock>

      <H3>Signature verification</H3>
      <P>
        If a secret is configured, each delivery includes an <code className="text-brand font-mono text-xs">X-Webhook-Signature</code> header
        with the HMAC-SHA256 hex digest of the payload body, signed with your secret.
      </P>
    </>
  );
}
