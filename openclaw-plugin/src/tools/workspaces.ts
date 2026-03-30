import type { OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";
import { textResult } from "../utils/tool-result.js";
/**
 * Workspace tools — create, list, join, info, members.
 */

import { Type } from "@sinclair/typebox";
import type { BoozleClient } from "../boozle-client.js";

export function registerWorkspaceTools(
  api: OpenClawPluginApi,
  client: BoozleClient,
) {
  api.registerTool({
    name: "boozle_create_workspace",
    description: "Create a new Boozle workspace",
    label: "Create a new Boozle workspace",
    parameters: Type.Object({
      name: Type.String({ description: "Workspace name" }),
      description: Type.Optional(Type.String({ description: "Workspace description" })),
      is_public: Type.Optional(Type.Boolean({ description: "Whether the workspace is public" })),
    }),
    async execute(_id: string, params: { name: string; description?: string; is_public?: boolean }) {
      const result = await client.createWorkspace(
        params.name,
        params.description ?? "",
        params.is_public ?? false,
      );
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "boozle_list_workspaces",
    description: "List Boozle workspaces (your own or all public)",
    label: "List Boozle workspaces (your own or all public)",
    parameters: Type.Object({
      mine: Type.Optional(Type.Boolean({ description: "Only list your workspaces" })),
    }),
    async execute(_id: string, params: { mine?: boolean }) {
      const result = await client.listWorkspaces(params.mine ?? false);
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "boozle_join_workspace",
    description: "Join a Boozle workspace using an invite code",
    label: "Join a Boozle workspace using an invite code",
    parameters: Type.Object({
      invite_code: Type.String({ description: "Workspace invite code" }),
    }),
    async execute(_id: string, params: { invite_code: string }) {
      const result = await client.joinWorkspace(params.invite_code);
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "boozle_workspace_info",
    description: "Get details about a Boozle workspace",
    label: "Get details about a Boozle workspace",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
    }),
    async execute(_id: string, params: { workspace_id: string }) {
      const result = await client.workspaceInfo(params.workspace_id);
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "boozle_workspace_members",
    description: "List members of a Boozle workspace",
    label: "List members of a Boozle workspace",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
    }),
    async execute(_id: string, params: { workspace_id: string }) {
      const result = await client.workspaceMembers(params.workspace_id);
      return textResult(JSON.stringify(result, null, 2));
    },
  });
}
