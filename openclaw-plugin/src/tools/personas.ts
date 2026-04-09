import type { OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";
import { textResult } from "../utils/tool-result.js";
/**
 * Persona identity tools — create, list, rotate keys.
 */

import { Type } from "@sinclair/typebox";
import type { OctopusClient } from "../octopus-client.js";

export function registerPersonaTools(
  api: OpenClawPluginApi,
  client: OctopusClient,
) {
  api.registerTool({
    name: "octopus_create_persona",
    description: "Create a new Octopus persona identity",
    label: "Create a new Octopus persona identity",
    parameters: Type.Object({
      name: Type.String({ description: "Persona name (unique identifier)" }),
      display_name: Type.Optional(Type.String({ description: "Display name" })),
      description: Type.Optional(Type.String({ description: "Persona description" })),
    }),
    async execute(_id: string, params: { name: string; display_name?: string; description?: string }) {
      const result = await client.createPersona(
        params.name,
        params.display_name ?? "",
        params.description ?? "",
      );
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_list_personas",
    description: "List your Octopus persona identities",
    label: "List your Octopus persona identities",
    parameters: Type.Object({}),
    async execute() {
      const result = await client.listPersonas();
      return textResult(JSON.stringify(result, null, 2));
    },
  });

  api.registerTool({
    name: "octopus_rotate_persona_key",
    description: "Rotate the API key for a Octopus persona",
    label: "Rotate the API key for a Octopus persona",
    parameters: Type.Object({
      persona_id: Type.String({ description: "Persona UUID" }),
    }),
    async execute(_id: string, params: { persona_id: string }) {
      const result = await client.rotatePersonaKey(params.persona_id);
      return textResult(JSON.stringify(result, null, 2));
    },
  });
}
