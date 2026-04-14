/** Helper to create a properly typed AgentToolResult from text. */
export function textResult(text: string) {
  return {
    content: [{ type: "text" as const, text }],
    details: null,
  };
}
