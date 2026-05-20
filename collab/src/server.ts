import { Mark, type Extensions } from "@tiptap/core";
import Bold from "@tiptap/extension-bold";
import Heading from "@tiptap/extension-heading";
import Image from "@tiptap/extension-image";
import Italic from "@tiptap/extension-italic";
import Link from "@tiptap/extension-link";
import Subscript from "@tiptap/extension-subscript";
import Superscript from "@tiptap/extension-superscript";
import { Table, TableCell, TableHeader, TableRow } from "@tiptap/extension-table";
import Typography from "@tiptap/extension-typography";
import Underline from "@tiptap/extension-underline";
import { generateJSON } from "@tiptap/html/server";
import StarterKit from "@tiptap/starter-kit";
import { Server } from "@hocuspocus/server";
import { TiptapTransformer } from "@hocuspocus/transformer";
import MarkdownIt from "markdown-it";
import pg from "pg";
import * as Y from "yjs";

type CollabAuth = {
  user: {
    id: string;
    name: string;
    display_name: string;
  };
  can_write: boolean;
};

type PageDocument = {
  workspaceId: string;
  pageId: string;
};

type CollabContext = {
  userId?: string;
  canWrite?: boolean;
};

const { Pool } = pg;

const port = Number(process.env.PORT || "3458");
const backendUrl = requiredEnv("BACKEND_URL").replace(/\/$/, "");
const databaseUrl = requiredEnv("DATABASE_URL");
const databaseSsl = process.env.DATABASE_SSL === "true";
const debugEnabled = process.env.COLLAB_DEBUG === "true";

const pool = new Pool({
  connectionString: databaseUrl,
  ssl: databaseSsl ? { rejectUnauthorized: false } : undefined,
});

const markdown = new MarkdownIt({ html: true, linkify: true, typographer: false });

const CommentMark = Mark.create({
  name: "comment",
  addAttributes() {
    return {
      id: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-comment-id"),
        renderHTML: (attributes) =>
          attributes.id ? { "data-comment-id": attributes.id } : {},
      },
    };
  },
  parseHTML() {
    return [{ tag: "span[data-comment-id]" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["span", HTMLAttributes, 0];
  },
});

const editorExtensions: Extensions = [
  StarterKit.configure({
    blockquote: false,
    codeBlock: false,
    heading: false,
    bold: false,
    italic: false,
    link: false,
    underline: false,
  }),
  Heading.configure({ levels: [1, 2, 3] }),
  Bold,
  Italic,
  Underline,
  Subscript,
  Superscript,
  Typography,
  Link.configure({ openOnClick: false, autolink: true }),
  Image,
  Table,
  TableRow,
  TableHeader,
  TableCell,
  CommentMark,
];

const server = new Server<CollabContext>({
  port,
  address: "0.0.0.0",
  debounce: 1500,
  maxDebounce: 10000,
  quiet: process.env.COLLAB_QUIET !== "false",

  async onAuthenticate(data) {
    const page = parsePageDocument(data.documentName);
    const auth = await authorize(data.documentName, data.token);
    if (!auth.can_write) {
      data.connectionConfig.readOnly = true;
    }
    debug("authenticated", {
      documentName: data.documentName,
      userId: auth.user.id,
      canWrite: auth.can_write,
    });
    return {
      userId: auth.user.id,
      canWrite: auth.can_write,
      pageId: page.pageId,
    };
  },

  async onLoadDocument({ documentName }) {
    const page = parsePageDocument(documentName);
    const persisted = await loadPersistedState(page.pageId);
    if (persisted) {
      debug("loaded persisted document", {
        documentName,
        bytes: persisted.byteLength,
      });
      return persisted;
    }
    const document = await bootstrapPageDocument(page);
    debug("bootstrapped document", {
      documentName,
      fields: Array.from(document.share.keys()),
      bytes: Y.encodeStateAsUpdate(document).byteLength,
    });
    return document;
  },

  async onStoreDocument({ document, documentName }) {
    const page = parsePageDocument(documentName);
    const state = Buffer.from(Y.encodeStateAsUpdate(document));
    debug("stored document", {
      documentName,
      bytes: state.byteLength,
    });
    await pool.query(
      `
      INSERT INTO page_collab_documents (page_id, workspace_id, yjs_state)
      VALUES ($1, $2, $3)
      ON CONFLICT (page_id)
      DO UPDATE SET yjs_state = EXCLUDED.yjs_state, updated_at = now()
      `,
      [page.pageId, page.workspaceId, state],
    );
  },
});

await server.listen();
console.log(`Stash collaboration server listening on ${server.webSocketURL}`);

process.on("SIGTERM", () => {
  void shutdown();
});
process.on("SIGINT", () => {
  void shutdown();
});

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
}

function debug(message: string, data: Record<string, unknown>): void {
  if (!debugEnabled) return;
  console.log(`[collab] ${message}`, JSON.stringify(data));
}

function parsePageDocument(documentName: string): PageDocument {
  const parts = documentName.split(":");
  if (parts.length !== 4 || parts[0] !== "workspace" || parts[2] !== "page") {
    throw new Error("Unsupported collaboration document");
  }
  return {
    workspaceId: parts[1],
    pageId: parts[3],
  };
}

async function authorize(documentName: string, token: string): Promise<CollabAuth> {
  if (!token) {
    throw new Error("Authentication token is required");
  }
  const response = await fetch(`${backendUrl}/api/v1/collab/authorize`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ document_name: documentName }),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as CollabAuth;
}

async function loadPersistedState(pageId: string): Promise<Uint8Array | null> {
  const result = await pool.query<{ yjs_state: Buffer }>(
    "SELECT yjs_state FROM page_collab_documents WHERE page_id = $1",
    [pageId],
  );
  const state = result.rows[0]?.yjs_state;
  return state ? new Uint8Array(state) : null;
}

async function bootstrapPageDocument(page: PageDocument): Promise<Y.Doc> {
  const result = await pool.query<{ content_markdown: string }>(
    `
    SELECT content_markdown
    FROM pages
    WHERE id = $1
      AND workspace_id = $2
      AND content_type = 'markdown'
      AND deleted_at IS NULL
    `,
    [page.pageId, page.workspaceId],
  );
  const markdownSource = result.rows[0]?.content_markdown;
  if (markdownSource === undefined) {
    throw new Error("Page not found");
  }
  const html = markdown.render(markdownSource);
  const json = generateJSON(html, editorExtensions);
  return TiptapTransformer.toYdoc(json, "default", editorExtensions);
}

async function shutdown(): Promise<void> {
  await server.hocuspocus.flushPendingStores();
  await server.destroy();
  await pool.end();
  process.exit(0);
}
