import { Callout, Code, CodeBlock, H3, P, Title, Subtitle } from "../components";

export default function APIPage() {
  return (
    <>
      <Title>REST API</Title>
      <Subtitle>
        Complete HTTP API for all Stash resources. All endpoints are versioned under{" "}
        <Code>{"https://stash.ac/api/v1"}</Code>.
      </Subtitle>

      <Callout type="info">
        <strong>Authentication</strong> — include{" "}
        <code className="font-mono text-[13px]">Authorization: Bearer {"<api_key>"}</code> on every request.
        Get your API key from the settings page or via <Code>POST /users/login</Code>.
        <br /><br />
        <strong>OpenAPI spec</strong> — the full interactive spec is available at{" "}
        <Code>/docs</Code> on your backend instance (e.g.{" "}
        <Code>http://localhost:3456/docs</Code>).
      </Callout>

      <H3>Auth</H3>
      <CodeBlock>{`POST   /users/register      Register a new user — returns api_key
POST   /users/login         Password login — returns api_key
GET    /users/me            Current user profile
PATCH  /users/me            Update profile (name, avatar, etc.)`}</CodeBlock>

      <H3>Workspaces</H3>
      <CodeBlock>{`POST   /workspaces                          Create a new workspace
GET    /workspaces                          List all public workspaces
GET    /workspaces/mine                     List workspaces you're a member of
POST   /workspaces/join/{invite_code}       Join by invite code
GET    /workspaces/{ws}                     Workspace details and metadata
PATCH  /workspaces/{ws}                     Update workspace
DELETE /workspaces/{ws}                     Delete workspace
GET    /workspaces/{ws}/members             List workspace members with roles
POST   /workspaces/{ws}/members             Add a member
POST   /workspaces/{ws}/leave               Leave workspace`}</CodeBlock>

      <H3>Notebooks & pages</H3>
      <CodeBlock>{`POST   /workspaces/{ws}/notebooks                          Create notebook
GET    /workspaces/{ws}/notebooks/{nb}/pages               Page tree (folders + pages)
POST   /workspaces/{ws}/notebooks/{nb}/pages               Create a page
GET    /workspaces/{ws}/notebooks/{nb}/pages/{id}          Read a page
PATCH  /workspaces/{ws}/notebooks/{nb}/pages/{id}          Update a page
DELETE /workspaces/{ws}/notebooks/{nb}/pages/{id}          Delete a page

GET    /workspaces/{ws}/notebooks/{nb}/pages/{id}/backlinks Incoming links
GET    /workspaces/{ws}/notebooks/{nb}/pages/{id}/outlinks  Outgoing links
GET    /workspaces/{ws}/notebooks/{nb}/graph               Page link graph (nodes + edges)

GET    /workspaces/{ws}/notebooks/{nb}/pages/semantic-search?q=   Semantic search`}</CodeBlock>

      <H3>History</H3>
      <CodeBlock>{`POST   /workspaces/{ws}/memory/events               Push a single event
POST   /workspaces/{ws}/memory/events/batch         Push a batch of events
GET    /workspaces/{ws}/memory/events               Query events (filter, paginate)
GET    /workspaces/{ws}/memory/events/search?q=     Full-text search
GET    /workspaces/{ws}/memory/events/{id}          Get a specific event
GET    /workspaces/{ws}/memory/agent-names           List distinct agent names
DELETE /workspaces/{ws}/memory/agents/{agent_name}  Delete all events for an agent`}</CodeBlock>

      <H3>Files</H3>
      <CodeBlock>{`POST   /workspaces/{ws}/files                Upload a file (multipart/form-data)
GET    /workspaces/{ws}/files                List files
GET    /workspaces/{ws}/files/{id}           Get file metadata
GET    /workspaces/{ws}/files/{id}/download  Download file (redirects to signed URL)
GET    /workspaces/{ws}/files/{id}/text      Get extracted text (PDF, OCR, plain text)
DELETE /workspaces/{ws}/files/{id}           Delete a file`}</CodeBlock>

      <H3>Transcripts</H3>
      <CodeBlock>{`POST   /workspaces/{ws}/transcripts                Upload a session transcript
GET    /workspaces/{ws}/transcripts/{session_id}   Get transcript`}</CodeBlock>

      <H3>Tables & rows</H3>
      <CodeBlock>{`POST   /workspaces/{ws}/tables                               Create table
GET    /workspaces/{ws}/tables                               List tables
GET    /workspaces/{ws}/tables/{tbl}                         Table schema + metadata
POST   /workspaces/{ws}/tables/{tbl}/rows                    Create a row
GET    /workspaces/{ws}/tables/{tbl}/rows                    Query rows (filter, sort, paginate)
PATCH  /workspaces/{ws}/tables/{tbl}/rows/{id}               Update a row
DELETE /workspaces/{ws}/tables/{tbl}/rows/{id}               Delete a row

GET    /workspaces/{ws}/tables/{tbl}/rows/semantic-search?q= Semantic search
PUT    /workspaces/{ws}/tables/{tbl}/embedding               Configure row embeddings
POST   /workspaces/{ws}/tables/{tbl}/embedding/backfill      Backfill embeddings for existing rows`}</CodeBlock>

      <H3>Permissions</H3>
      <P>
        Notebooks and tables have per-resource visibility and sharing. Use the
        permissions endpoints on each resource type:
      </P>
      <CodeBlock>{`GET    /workspaces/{ws}/notebooks/{id}/permissions            Get visibility + shares
PATCH  /workspaces/{ws}/notebooks/{id}/permissions            Set visibility
POST   /workspaces/{ws}/notebooks/{id}/permissions/share      Share with a user
DELETE /workspaces/{ws}/notebooks/{id}/permissions/share/{uid} Remove share

GET    /workspaces/{ws}/tables/{id}/permissions               Get visibility + shares
PATCH  /workspaces/{ws}/tables/{id}/permissions               Set visibility
POST   /workspaces/{ws}/tables/{id}/permissions/share         Share with a user
DELETE /workspaces/{ws}/tables/{id}/permissions/share/{uid}   Remove share`}</CodeBlock>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {[
          { v: "inherit", desc: "Default. All workspace members have access (read + write based on role)." },
          { v: "private", desc: "Only explicitly shared users. Grant access with POST /share." },
          { v: "public", desc: "Anyone with the URL can read. No auth required." },
        ].map((r) => (
          <div key={r.v} className="flex gap-5 px-5 py-4">
            <span className="text-[13px] font-semibold text-foreground font-mono w-24 flex-shrink-0">{r.v}</span>
            <p className="text-[14px] text-dim leading-6">{r.desc}</p>
          </div>
        ))}
      </div>

      <H3>Rate limits</H3>
      <div className="rounded-2xl border border-border bg-surface divide-y divide-border my-6">
        {[
          { endpoint: "Register", limit: "5 requests / minute" },
          { endpoint: "Login", limit: "10 requests / minute" },
          { endpoint: "Create API key", limit: "10 requests / minute" },
          { endpoint: "CLI auth sessions", limit: "10 requests / minute" },
          { endpoint: "CLI auth poll", limit: "60 requests / minute" },
        ].map((r) => (
          <div key={r.endpoint} className="flex gap-5 px-5 py-4">
            <span className="text-[13px] font-semibold text-foreground w-56 flex-shrink-0">{r.endpoint}</span>
            <span className="text-[13px] text-dim font-mono">{r.limit}</span>
          </div>
        ))}
      </div>

      <H3>Personal / aggregate endpoints</H3>
      <CodeBlock>{`GET    /me/notebooks              List all your notebooks (cross-workspace)
GET    /me/history-events          List all your history events (cross-workspace)
GET    /me/tables                  List all your tables (cross-workspace)
GET    /me/activity-timeline       Activity timeline for dashboard
GET    /me/knowledge-density       Knowledge density heatmap data
GET    /me/embedding-projection    2D embedding projection for space explorer`}</CodeBlock>
    </>
  );
}
