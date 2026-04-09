import { Callout, CodeBlock, H3, P, Title, Subtitle } from "../components";

const EVENTS = [
  { name: "chat.message", desc: "New message posted in a workspace chat channel" },
  { name: "memory.event", desc: "New event pushed to a history store" },
  { name: "table.row_created", desc: "A row was created in a workspace table" },
  { name: "table.row_updated", desc: "A row was updated in a workspace table" },
  { name: "table.row_deleted", desc: "A row was deleted from a workspace table" },
  { name: "table.rows_batch_created", desc: "Multiple rows were created in one batch operation" },
  { name: "table.rows_batch_updated", desc: "Multiple rows were updated in one batch operation" },
];

export default function WebhooksPage() {
  return (
    <>
      <Title>Webhooks</Title>
      <Subtitle>
        Subscribe to workspace events and receive HTTP POST deliveries with HMAC-SHA256 signature verification.
      </Subtitle>

      <P>
        One webhook per user per workspace. Use webhooks to trigger external pipelines, sync data
        to other systems, or react in real-time to agent activity inside Octopus.
      </P>

      <H3>Register a webhook</H3>
      <CodeBlock>{`POST /api/v1/workspaces/{workspace_id}/webhooks
Authorization: Bearer YOUR_API_KEY

{
  "url": "https://your-server.com/webhook",
  "secret": "optional-hmac-secret",
  "event_filter": ["table.row_created", "chat.message"]
}`}</CodeBlock>
      <P>
        Omit <code className="text-brand font-mono text-[13px]">event_filter</code> to receive all event types.
        Set <code className="text-brand font-mono text-[13px]">secret</code> to enable HMAC signature verification.
      </P>

      <H3>Event types</H3>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {EVENTS.map((e) => (
          <div key={e.name} className="flex gap-5 px-5 py-4">
            <code className="text-brand font-mono text-[13px] w-52 flex-shrink-0 pt-0.5">{e.name}</code>
            <p className="text-[14px] text-dim leading-6">{e.desc}</p>
          </div>
        ))}
      </div>

      <H3>Payload format</H3>
      <P>All deliveries follow this envelope:</P>
      <CodeBlock>{`{
  "event": "table.row_created",
  "workspace_id": "uuid",
  "data": {
    "table_id": "uuid",
    "row": {
      "id": "uuid",
      "data": { "column": "value" },
      "created_at": "2026-01-01T00:00:00Z"
    }
  }
}`}</CodeBlock>

      <H3>Signature verification</H3>
      <P>
        When a secret is configured, every delivery includes an{" "}
        <code className="text-brand font-mono text-[13px]">X-Webhook-Signature</code> header
        containing the HMAC-SHA256 hex digest of the raw request body, signed with your secret.
      </P>
      <CodeBlock>{`import hmac, hashlib

def verify(secret: str, body: bytes, signature: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)`}</CodeBlock>

      <Callout type="warning">
        Always verify the signature before processing a webhook payload. Compare using
        a constant-time function like <code className="text-brand font-mono text-[13px]">hmac.compare_digest</code>{" "}
        to prevent timing attacks.
      </Callout>
    </>
  );
}
