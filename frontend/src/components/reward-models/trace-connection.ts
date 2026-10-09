/** Keep arbitrary source IDs literal when pasted into a shell. */
function shellQuote(value: string): string {
  return "'" + value.replaceAll("'", "'\"'\"'") + "'";
}

export function traceConnectionCommands(apiBase: string, method: "otel" | "http", sourceId: string): string {
  const id = sourceId.trim();
  if (method === "otel") return `export OTEL_EXPORTER_OTLP_ENDPOINT=${apiBase}/api/v1/rm/otel
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer%20<your API key>${id ? `,X-Stash-Trace-Source=${encodeURIComponent(id)}` : ""}"

opentelemetry-instrument python agent.py`;

  return `export STASH_API_KEY="<your API key>"

jq -Rs ${id ? `--arg source_id ${shellQuote(id)} '{format: "auto", data: ., source_id: $source_id}'` : "'{format: \"auto\", data: .}'"} traces.jsonl \\
  | curl --fail-with-body "${apiBase}/api/v1/rm/traces/import" \\
      -H "Authorization: Bearer $STASH_API_KEY" \\
      -H "Content-Type: application/json" \\
      --data-binary @-`;
}
