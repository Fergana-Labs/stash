import type { OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";
import { textResult } from "../utils/tool-result.js";
/**
 * Notebook tools — list, create, read, update, delete.
 */

import { Type } from "@sinclair/typebox";
import type { OctopusClient } from "../octopus-client.js";

export function registerNotebookTools(
  api: OpenClawPluginApi,
  client: OctopusClient,
) {
  api.registerTool({
    name: "octopus_list_notebooks",
    description: "List notebooks in a Octopus workspace",
    label: "List notebooks in a Octopus workspace",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
    }),
    async execute(_id: string, params: { workspace_id: string }) {
      const result = await client.listNotebooks(params.workspace_id);
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_create_notebook",
    description: "Create a new notebook in a Octopus workspace",
    label: "Create a new notebook in a Octopus workspace",
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
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_read_notebook",
    description: "Read a notebook's content from Octopus",
    label: "Read a notebook's content from Octopus",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      notebook_id: Type.String({ description: "Notebook UUID" }),
    }),
    async execute(_id: string, params: { workspace_id: string; notebook_id: string }) {
      const result = await client.readNotebook(params.workspace_id, params.notebook_id);
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_update_notebook",
    description: "Update a notebook's name or content in Octopus",
    label: "Update a notebook's name or content in Octopus",
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
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_delete_notebook",
    description: "Delete a notebook from Octopus",
    label: "Delete a notebook from Octopus",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      notebook_id: Type.String({ description: "Notebook UUID" }),
    }),
    async execute(_id: string, params: { workspace_id: string; notebook_id: string }) {
      await client.deleteNotebook(params.workspace_id, params.notebook_id);
      return textResult("Notebook deleted.");
    },
  });
}
