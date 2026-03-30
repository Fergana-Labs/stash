import type { OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";
import { textResult } from "../utils/tool-result.js";
/**
 * Chat tools — create, list, send, read, search messages.
 */

import { Type } from "@sinclair/typebox";
import type { BoozleClient } from "../boozle-client.js";

export function registerChatTools(
  api: OpenClawPluginApi,
  client: BoozleClient,
) {
  api.registerTool({
    name: "boozle_create_chat",
    description: "Create a new chat in a Boozle workspace",
    label: "Create a new chat in a Boozle workspace",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      name: Type.String({ description: "Chat name" }),
      description: Type.Optional(Type.String({ description: "Chat description" })),
    }),
    async execute(_id: string, params: { workspace_id: string; name: string; description?: string }) {
      const result = await client.createChat(
        params.workspace_id,
        params.name,
        params.description ?? "",
      );
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "boozle_list_chats",
    description: "List chats in a Boozle workspace",
    label: "List chats in a Boozle workspace",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
    }),
    async execute(_id: string, params: { workspace_id: string }) {
      const result = await client.listChats(params.workspace_id);
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "boozle_send_message",
    description: "Send a message to a Boozle chat",
    label: "Send a message to a Boozle chat",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      chat_id: Type.String({ description: "Chat UUID" }),
      content: Type.String({ description: "Message content" }),
    }),
    async execute(_id: string, params: { workspace_id: string; chat_id: string; content: string }) {
      const result = await client.sendMessage(
        params.workspace_id,
        params.chat_id,
        params.content,
      );
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "boozle_read_messages",
    description: "Read messages from a Boozle chat",
    label: "Read messages from a Boozle chat",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      chat_id: Type.String({ description: "Chat UUID" }),
      limit: Type.Optional(Type.Number({ description: "Max messages to return (default: 20)" })),
      after: Type.Optional(Type.String({ description: "Cursor for pagination" })),
    }),
    async execute(_id: string, params: { workspace_id: string; chat_id: string; limit?: number; after?: string }) {
      const result = await client.readMessages(
        params.workspace_id,
        params.chat_id,
        params.limit ?? 20,
        params.after ?? "",
      );
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "boozle_search_messages",
    description: "Search messages in a Boozle chat",
    label: "Search messages in a Boozle chat",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      chat_id: Type.String({ description: "Chat UUID" }),
      query: Type.String({ description: "Search query" }),
      limit: Type.Optional(Type.Number({ description: "Max results (default: 20)" })),
    }),
    async execute(_id: string, params: { workspace_id: string; chat_id: string; query: string; limit?: number }) {
      const result = await client.searchMessages(
        params.workspace_id,
        params.chat_id,
        params.query,
        params.limit ?? 20,
      );
      return textResult(JSON.stringify(result, null, 2));
    },
  });
}
