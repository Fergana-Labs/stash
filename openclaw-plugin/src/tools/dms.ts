import type { OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";
import { textResult } from "../utils/tool-result.js";
/**
 * DM tools — start, list, send, read direct messages.
 */

import { Type } from "@sinclair/typebox";
import type { OctopusClient } from "../octopus-client.js";

export function registerDmTools(
  api: OpenClawPluginApi,
  client: OctopusClient,
) {
  api.registerTool({
    name: "octopus_start_dm",
    description: "Start a direct message conversation with a Octopus user",
    label: "Start a direct message conversation with a Octopus user",
    parameters: Type.Object({
      user_id: Type.Optional(Type.String({ description: "User UUID" })),
      username: Type.Optional(Type.String({ description: "Username" })),
    }),
    async execute(_id: string, params: { user_id?: string; username?: string }) {
      const result = await client.startDm(params.user_id ?? "", params.username ?? "");
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_list_dms",
    description: "List your direct message conversations on Octopus",
    label: "List your direct message conversations on Octopus",
    parameters: Type.Object({}),
    async execute() {
      const result = await client.listDms();
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_send_dm",
    description: "Send a direct message to a Octopus user",
    label: "Send a direct message to a Octopus user",
    parameters: Type.Object({
      content: Type.String({ description: "Message content" }),
      user_id: Type.Optional(Type.String({ description: "User UUID" })),
      username: Type.Optional(Type.String({ description: "Username" })),
    }),
    async execute(_id: string, params: { content: string; user_id?: string; username?: string }) {
      const result = await client.sendDm(
        params.content,
        params.user_id ?? "",
        params.username ?? "",
      );
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_read_dm",
    description: "Read direct messages from a Octopus user",
    label: "Read direct messages from a Octopus user",
    parameters: Type.Object({
      user_id: Type.Optional(Type.String({ description: "User UUID" })),
      username: Type.Optional(Type.String({ description: "Username" })),
      limit: Type.Optional(Type.Number({ description: "Max messages (default: 20)" })),
      after: Type.Optional(Type.String({ description: "Cursor for pagination" })),
    }),
    async execute(_id: string, params: { user_id?: string; username?: string; limit?: number; after?: string }) {
      const result = await client.readDm(
        params.user_id ?? "",
        params.username ?? "",
        params.limit ?? 20,
        params.after ?? "",
      );
      return textResult(JSON.stringify(result, null, 2));
    },
  });
}
