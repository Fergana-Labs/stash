import type { OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";
import { textResult } from "../utils/tool-result.js";
/**
 * Memory store tools — create, list, push events, query, search.
 */

import { Type } from "@sinclair/typebox";
import type { BoozleClient } from "../boozle-client.js";

export function registerMemoryStoreTools(
  api: OpenClawPluginApi,
  client: BoozleClient,
) {
  api.registerTool({
    name: "boozle_create_memory_store",
    description: "Create a new memory store in a Boozle workspace",
    label: "Create a new memory store in a Boozle workspace",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      name: Type.String({ description: "Store name" }),
      description: Type.Optional(Type.String({ description: "Store description" })),
    }),
    async execute(_id: string, params: { workspace_id: string; name: string; description?: string }) {
      const result = await client.createHistory(
        params.workspace_id,
        params.name,
        params.description ?? "",
      );
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "boozle_list_memory_stores",
    description: "List memory stores in a Boozle workspace",
    label: "List memory stores in a Boozle workspace",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
    }),
    async execute(_id: string, params: { workspace_id: string }) {
      const result = await client.listHistories(params.workspace_id);
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "boozle_push_event",
    description: "Push an event to a Boozle memory store",
    label: "Push an event to a Boozle memory store",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      store_id: Type.String({ description: "Memory store UUID" }),
      agent_name: Type.String({ description: "Agent name" }),
      event_type: Type.String({ description: "Event type (e.g. tool_use, session_end, memory)" }),
      content: Type.String({ description: "Event content" }),
      tool_name: Type.Optional(Type.String({ description: "Tool name (for tool_use events)" })),
    }),
    async execute(_id: string, params: {
      workspace_id: string; store_id: string; agent_name: string;
      event_type: string; content: string; tool_name?: string;
    }) {
      const result = await client.pushEvent({
        workspaceId: params.workspace_id,
        storeId: params.store_id,
        agentName: params.agent_name,
        eventType: params.event_type,
        content: params.content,
        toolName: params.tool_name,
      });
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "boozle_query_events",
    description: "Query events from a Boozle memory store",
    label: "Query events from a Boozle memory store",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      store_id: Type.String({ description: "Memory store UUID" }),
      agent_name: Type.Optional(Type.String({ description: "Filter by agent name" })),
      event_type: Type.Optional(Type.String({ description: "Filter by event type" })),
      limit: Type.Optional(Type.Number({ description: "Max events (default: 50)" })),
    }),
    async execute(_id: string, params: {
      workspace_id: string; store_id: string; agent_name?: string;
      event_type?: string; limit?: number;
    }) {
      const result = await client.queryEvents({
        workspaceId: params.workspace_id,
        storeId: params.store_id,
        agentName: params.agent_name,
        eventType: params.event_type,
        limit: params.limit ?? 50,
      });
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "boozle_search_events",
    description: "Full-text search over events in a Boozle memory store",
    label: "Full-text search over events in a Boozle memory store",
    parameters: Type.Object({
      workspace_id: Type.String({ description: "Workspace UUID" }),
      store_id: Type.String({ description: "Memory store UUID" }),
      query: Type.String({ description: "Search query" }),
      limit: Type.Optional(Type.Number({ description: "Max results (default: 50)" })),
    }),
    async execute(_id: string, params: { workspace_id: string; store_id: string; query: string; limit?: number }) {
      const result = await client.searchEvents(
        params.workspace_id,
        params.store_id,
        params.query,
        params.limit ?? 50,
      );
      return textResult(JSON.stringify(result, null, 2));
    },
  });
}
