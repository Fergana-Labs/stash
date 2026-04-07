import { Code, CodeBlock, H3, P, Title, Subtitle } from "../components";

export default function APIPage() {
  return (
    <>
      <Title>REST API</Title>
      <Subtitle>Complete HTTP API for all Boozle resources.</Subtitle>

      <P>
        Base URL: <Code>https://getboozle.com/api/v1/</Code>
      </P>
      <P>
        Auth: <Code>{"Authorization: Bearer <api_key>"}</Code>
      </P>

      <H3>Auth</H3>
      <CodeBlock>{`POST /users/register          # Create account → returns api_key
POST /users/login             # Login → returns api_key
GET  /users/me                # Current user profile
PATCH /users/me               # Update profile`}</CodeBlock>

      <H3>Workspaces</H3>
      <CodeBlock>{`POST   /workspaces                          # Create workspace
GET    /workspaces                          # List public workspaces
GET    /workspaces/mine                     # List my workspaces
POST   /workspaces/{ws}/join                # Join by invite code
GET    /workspaces/{ws}                     # Workspace info
GET    /workspaces/{ws}/members             # List members`}</CodeBlock>

      <H3>Notebooks & Pages</H3>
      <CodeBlock>{`POST   /workspaces/{ws}/notebooks                        # Create notebook
GET    /workspaces/{ws}/notebooks/{nb}/pages              # Page tree
POST   /workspaces/{ws}/notebooks/{nb}/pages              # Create page
GET    /workspaces/{ws}/notebooks/{nb}/pages/{id}         # Read page
PATCH  /workspaces/{ws}/notebooks/{nb}/pages/{id}         # Update page
GET    /workspaces/{ws}/notebooks/{nb}/pages/{id}/backlinks
GET    /workspaces/{ws}/notebooks/{nb}/pages/{id}/outlinks
GET    /workspaces/{ws}/notebooks/{nb}/graph               # Page graph
GET    /workspaces/{ws}/notebooks/{nb}/pages/semantic-search?q=...
POST   /workspaces/{ws}/notebooks/{nb}/auto-index`}</CodeBlock>

      <H3>History</H3>
      <CodeBlock>{`POST   /workspaces/{ws}/memory                             # Create store
POST   /workspaces/{ws}/memory/{store}/events              # Push event
POST   /workspaces/{ws}/memory/{store}/events/batch        # Batch push
GET    /workspaces/{ws}/memory/{store}/events              # Query events
GET    /workspaces/{ws}/memory/{store}/events/search?q=... # FTS search
POST   /workspaces/{ws}/memory/{store}/query               # LLM synthesis`}</CodeBlock>

      <H3>Search</H3>
      <CodeBlock>{`POST   /workspaces/{ws}/search              # Workspace-scoped universal search
POST   /me/search                           # Personal universal search`}</CodeBlock>

      <H3>Files</H3>
      <CodeBlock>{`POST   /workspaces/{ws}/files               # Upload (multipart)
GET    /workspaces/{ws}/files               # List files
GET    /workspaces/{ws}/files/{id}          # Get file + presigned URL
DELETE /workspaces/{ws}/files/{id}          # Delete file`}</CodeBlock>

      <H3>Tables</H3>
      <CodeBlock>{`POST   /workspaces/{ws}/tables                              # Create table
POST   /workspaces/{ws}/tables/{tbl}/rows                  # Create row
PATCH  /workspaces/{ws}/tables/{tbl}/rows/{id}             # Update row
GET    /workspaces/{ws}/tables/{tbl}/rows/semantic-search?q=...
PUT    /workspaces/{ws}/tables/{tbl}/embedding             # Configure embeddings
POST   /workspaces/{ws}/tables/{tbl}/embedding/backfill`}</CodeBlock>

      <H3>Chats</H3>
      <CodeBlock>{`POST   /workspaces/{ws}/chats                # Create chat
POST   /workspaces/{ws}/chats/{id}/messages  # Send message
GET    /workspaces/{ws}/chats/{id}/messages  # Read messages`}</CodeBlock>

      <P>
        Personal variants (without workspace prefix) exist for all endpoints.
        Full OpenAPI spec available at <Code>/docs</Code> on the backend.
      </P>
    </>
  );
}
