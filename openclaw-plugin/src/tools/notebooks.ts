/**
 * Notebook tools — list, create, read, update, delete.
 */

import { Type } from "@sinclair/typebox";
import type { BoozleClient } from "../boozle-client.js";

export function registerNotebookTools(
  api: { registerTool: (def: unknown, opts?: unknown) => void },
  client: BoozleClient,
) {
  api.registerTool({
    name: "boozle_list_notebooks",
    description: "List notebooks in a Boozle workspace",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
    }),
    async execute(_id: string, params: { workspace_id: string }) {
      const result = await client.listNotebooks(params.workspace_id);
      return { content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }] };
    },
  });

  api.registerTool({
    name: "boozle_create_notebook",
    description: "Create a new notebook in a Boozle workspace",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      name: Type.String({ description: "Notebook name" }),
      content: Type.Optional(Type.String({ description: "Initial markdown content" })),
      folder_id: Type.Optional(Type.String({ description: "Folder UUID to place notebook in" })),
    }),
    async execute(_id: string, params: { workspace_id: string; name: string; content?: string; folder_id?: string }) {
      const result = await client.createNotebook(
        params.workspace_id,
        params.name,
        params.content ?? "",
        params.folder_id ?? "",
      );
      return { content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }] };
    },
  });

  api.registerTool({
    name: "boozle_read_notebook",
    description: "Read a notebook's content from Boozle",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      notebook_id: Type.String({ description: "Notebook UUID" }),
    }),
    async execute(_id: string, params: { workspace_id: string; notebook_id: string }) {
      const result = await client.readNotebook(params.workspace_id, params.notebook_id);
      return { content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }] };
    },
  });

  api.registerTool({
    name: "boozle_update_notebook",
    description: "Update a notebook's name or content in Boozle",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      notebook_id: Type.String({ description: "Notebook UUID" }),
      content: Type.Optional(Type.String({ description: "New markdown content" })),
      name: Type.Optional(Type.String({ description: "New name" })),
    }),
    async execute(_id: string, params: { workspace_id: string; notebook_id: string; content?: string; name?: string }) {
      const result = await client.updateNotebook(
        params.workspace_id,
        params.notebook_id,
        params.content ?? "",
        params.name ?? "",
      );
      return { content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }] };
    },
  });

  api.registerTool({
    name: "boozle_delete_notebook",
    description: "Delete a notebook from Boozle",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      notebook_id: Type.String({ description: "Notebook UUID" }),
    }),
    async execute(_id: string, params: { workspace_id: string; notebook_id: string }) {
      await client.deleteNotebook(params.workspace_id, params.notebook_id);
      return { content: [{ type: "text" as const, text: "Notebook deleted." }] };
    },
  });
}
