import type { OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";
import { textResult } from "../utils/tool-result.js";
/**
 * Workspace tools — create, list, join, info, members.
 */

import { Type } from "@sinclair/typebox";
import type { OctopusClient } from "../octopus-client.js";

export function registerWorkspaceTools(
  api: OpenClawPluginApi,
  client: OctopusClient,
) {
  api.registerTool({
    name: "octopus_create_workspace",
    description: "Create a new Octopus workspace",
    label: "Create a new Octopus workspace",
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
    name: "octopus_list_workspaces",
    description: "List Octopus workspaces (your own or all public)",
    label: "List Octopus workspaces (your own or all public)",
    parameters: Type.Object({
      mine: Type.Optional(Type.Boolean({ description: "Only list your workspaces" })),
    }),
    async execute(_id: string, params: { mine?: boolean }) {
      const result = await client.listWorkspaces(params.mine ?? false);
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_join_workspace",
    description: "Join a Octopus workspace using an invite code",
    label: "Join a Octopus workspace using an invite code",
    parameters: Type.Object({
      invite_code: Type.String({ description: "Workspace invite code" }),
    }),
    async execute(_id: string, params: { invite_code: string }) {
      const result = await client.joinWorkspace(params.invite_code);
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_workspace_info",
    description: "Get details about a Octopus workspace",
    label: "Get details about a Octopus workspace",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
    }),
    async execute(_id: string, params: { workspace_id: string }) {
      const result = await client.workspaceInfo(params.workspace_id);
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_workspace_members",
    description: "List members of a Octopus workspace",
    label: "List members of a Octopus workspace",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
    }),
    async execute(_id: string, params: { workspace_id: string }) {
      const result = await client.workspaceMembers(params.workspace_id);
      return textResult(JSON.stringify(result, null, 2));
    },
  });
}
