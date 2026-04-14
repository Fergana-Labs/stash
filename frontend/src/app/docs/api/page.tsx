import { Callout, Code, CodeBlock, H3, P, Title, Subtitle } from "../components";

export default function APIPage() {
  return (
    <>
      <Title>REST API</Title>
      <Subtitle>
        Complete HTTP API for all Octopus resources. All endpoints are versioned under{" "}
        <Code>{"https://getoctopus.com/api/v1"}</Code>.
      </Subtitle>

      <Callout type="info">
        <strong>Authentication</strong> — include{" "}
        <code className="font-mono text-[13px]">Authorization: Bearer {"<api_key>"}</code> on every request.
        Get your API key from the settings page or via <Code>POST /auth/login</Code>.
        <br /><br />
        <strong>OpenAPI spec</strong> — the full interactive spec is available at{" "}
        <Code>/docs</Code> on your backend instance (or{" "}
        <a href="https://getoctopus.com/docs" className="text-brand underline underline-offset-2">getoctopus.com/docs</a>
        ).
      </Callout>

      <H3>Auth</H3>
      <CodeBlock>{`POST   /auth/login          Login via Auth0 — returns api_key
GET    /users/me            Current user profile
PATCH  /users/me            Update profile (name, avatar, etc.)`}</CodeBlock>

      <H3>Workspaces</H3>
      <CodeBlock>{`POST   /workspaces              Create a new workspace
GET    /workspaces              List all public workspaces
GET    /workspaces/mine         List workspaces you're a member of
POST   /workspaces/{ws}/join    Join by invite code
GET    /workspaces/{ws}         Workspace details and metadata
GET    /workspaces/{ws}/members List workspace members with roles`}</CodeBlock>

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

      <H3>History stores</H3>
      <CodeBlock>{`POST   /workspaces/{ws}/memory                              Create store
POST   /workspaces/{ws}/memory/{store}/events               Push a single event
POST   /workspaces/{ws}/memory/{store}/events/batch         Push a batch of events
GET    /workspaces/{ws}/memory/{store}/events               Query events (filter, paginate)
GET    /workspaces/{ws}/memory/{store}/events/search?q=     Full-text search
POST   /workspaces/{ws}/memory/{store}/query                LLM synthesis over events`}</CodeBlock>

      <H3>Universal search</H3>
      <CodeBlock>{`POST   /workspaces/{ws}/search      Workspace-scoped search across all resources
POST   /me/search                   Personal search (outside any workspace)`}</CodeBlock>
      <P>
        Both accept a <Code>{"{ query, types, limit }"}</Code> body. Set{" "}
        <Code>types</Code> to filter by resource (e.g. <Code>"history,notebook,table"</Code>).
      </P>

      <H3>Files</H3>
      <CodeBlock>{`POST   /workspaces/{ws}/files          Upload a file (multipart/form-data)
GET    /workspaces/{ws}/files          List files
GET    /workspaces/{ws}/files/{id}     Get file metadata + presigned download URL
DELETE /workspaces/{ws}/files/{id}     Delete a file`}</CodeBlock>

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
        Every workspace resource has a visibility setting. Set it with a{" "}
        <Code>PATCH</Code> on the resource or via the dedicated visibility endpoint:
      </P>
      <CodeBlock>{`PUT /workspaces/{ws}/{resource_type}/{id}/visibility
body: { "visibility": "inherit" | "private" | "public" }`}</CodeBlock>
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
          { endpoint: "REST reads", limit: "60 requests / minute" },
          { endpoint: "File upload", limit: "10 requests / minute" },
          { endpoint: "Auth endpoints", limit: "20 requests / minute" },
        ].map((r) => (
          <div key={r.endpoint} className="flex gap-5 px-5 py-4">
            <span className="text-[13px] font-semibold text-foreground w-56 flex-shrink-0">{r.endpoint}</span>
            <span className="text-[13px] text-dim font-mono">{r.limit}</span>
          </div>
        ))}
      </div>

      <H3>Personal endpoints</H3>
      <P>
        Most workspace-scoped endpoints have a personal variant. For notebooks, for example:{" "}
        <Code>/me/notebooks</Code>. Personal endpoints return resources not tied to any workspace.
        Full list available in the{" "}
        <a href="https://getoctopus.com/docs" className="text-brand underline underline-offset-2">
          OpenAPI spec
        </a>
        .
      </P>
    </>
  );
}
