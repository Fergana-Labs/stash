import type { OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";
import { textResult } from "../utils/tool-result.js";
/**
 * DM tools — start, list, send, read direct messages.
 */

import { Type } from "@sinclair/typebox";
import type { BoozleClient } from "../boozle-client.js";

export function registerDmTools(
  api: OpenClawPluginApi,
  client: BoozleClient,
) {
  api.registerTool({
    name: "boozle_start_dm",
    description: "Start a direct message conversation with a Boozle user",
    label: "Start a direct message conversation with a Boozle user",
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
    name: "boozle_list_dms",
    description: "List your direct message conversations on Boozle",
    label: "List your direct message conversations on Boozle",
    parameters: Type.Object({}),
    async execute() {
      const result = await client.listDms();
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "boozle_send_dm",
    description: "Send a direct message to a Boozle user",
    label: "Send a direct message to a Boozle user",
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
    name: "boozle_read_dm",
    description: "Read direct messages from a Boozle user",
    label: "Read direct messages from a Boozle user",
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
