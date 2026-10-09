import { execFileSync } from "node:child_process";
import { expect, it } from "vitest";
import { traceConnectionCommands } from "./trace-connection";

it("shell-quotes custom source IDs without evaluating them", () => {
  const id = "Henry's $(printf injected) `printf injected` agent";
  const commands = traceConnectionCommands("https://example.com", "http", id);
  // Replace jq with a shell function to inspect its literal arguments; no API call.
  const jqLine = commands.split("\n").find((line) => line.startsWith("jq "))!.replace(/ \\$/, "");
  const args = execFileSync("/bin/sh", ["-c", `jq() { printf '%s\\n' "$@"; }; ${jqLine}`], { encoding: "utf8" }).split("\n");
  expect(args).toContain(id);
  expect(args).toContain('{format: "auto", data: ., source_id: $source_id}');
});

it("URL-encodes the OTLP header and leaves unspecified sources to automatic detection", () => {
  expect(traceConnectionCommands("https://example.com", "otel", " parts,west "))
    .toContain("X-Stash-Trace-Source=parts%2Cwest");
  expect(traceConnectionCommands("https://example.com", "otel", "")).not.toContain("X-Stash-Trace-Source");
  expect(traceConnectionCommands("https://example.com", "http", "")).not.toContain("source_id");
});
