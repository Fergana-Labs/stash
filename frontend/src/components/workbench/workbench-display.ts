/** Keep evaluator branding out of product copy, including saved legacy errors. */
export function workbenchError(error: string): string {
  return error
    .replace(/TYPESAFE_API_KEY is not configured; Jev grading is unavailable/gi, "Automatic evaluation is not configured on the server")
    .replace(/\bJev\b/gi, "Evaluator");
}

/** A display-only projection. Recorded evidence and the API payload stay intact. */
export function workbenchDetails(value: unknown): { value: unknown; omittedMetadata: boolean } {
  let omittedMetadata = false;
  function display(item: unknown): unknown {
    if (Array.isArray(item)) return item.map(display);
    if (!item || typeof item !== "object") return item;
    return Object.fromEntries(Object.entries(item).flatMap(([key, entry]) => {
      if ((key === "provider" && entry === "jev") || (key === "model" && typeof entry === "string" && /^jev(?:-|$)/i.test(entry))) {
        omittedMetadata = true;
        return [];
      }
      // These fields contain recorded/user-authored evidence, not evaluator metadata.
      if (["state", "context_events", "actions", "examples", "content", "text", "prompt", "criteria", "interpretation"].includes(key)) {
        return [[key, entry]];
      }
      if (key.endsWith("error") && typeof entry === "string") return [[key, workbenchError(entry)]];
      return [[key, display(entry)]];
    }));
  }
  const result = display(value);
  return { value: result, omittedMetadata };
}
