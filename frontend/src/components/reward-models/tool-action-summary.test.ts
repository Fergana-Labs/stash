import { describe, expect, it } from "vitest";
import { toolActionSummary, toolExplanation } from "./tool-action-summary";

const summary = (tool_name: string, tool_input: Record<string, unknown> | null) => toolActionSummary({ tool_name, tool_input });

describe("tool action summaries", () => {
  it("prefers the agent's recorded title, then description, without exposing code", () => {
    expect(summary("js", { code: "await tab.click(315);", title: " Disable commit\nand deployment alerts ", description: "Different description" })).toBe("Disable commit and deployment alerts");
    expect(summary("exec", { input: "unreadable()", title: " ", description: "Inspect notification settings" })).toBe("Inspect notification settings");
  });

  it("summarizes wrapped calls in order and groups repeated actions", () => {
    const input = 'await Promise.all([tools.exec_command({cmd:"cat settings.json"}), tools.exec_command({cmd:"cat README.md"}), tools.exec_command({cmd:"rg notifications"})]);';
    expect(summary("exec", { input })).toBe("Read files · Search files");
    expect(summary("exec", { input: 'text(await tools.web__run({open:[{ref_id:"https://docs.github.com/en/integrations"}]}));' })).toBe("Read docs.github.com");
    expect(summary("exec", { input: 'await tools.mcp__apps__slack__slack_search_channels({keywords:["notifications"]});' })).toBe("Find Slack channels");
  });

  it("describes shell actions rather than matching command words in arguments", () => {
    expect(summary("exec_command", { cmd: "npx vitest run" })).toBe("Run tests");
    expect(summary("exec_command", { cmd: "cat vitest.config.ts" })).toBe("Read files");
    expect(summary("exec_command", { cmd: 'echo "git push"' })).toBe("Run a shell command");
    expect(summary("read_file", { path: "src/settings.ts" })).toBe("Read src/settings.ts");
    expect(summary("sleep", { duration_ms: 20000 })).toBe("Wait 20 seconds");
  });

  it("falls back for unknown tools and dynamic arguments without executing source", () => {
    expect(summary("js", { code: 'throw new Error("must not execute")' })).toBe("Run JavaScript");
    expect(summary("exec", { input: "await tools.exec_command({cmd: buildCommand()})" })).toBe("Run a shell command");
    expect(summary("lookup_order", null)).toBe("Use Lookup order");
    expect(summary("exec", { input: 'ALL_TOOLS.filter(t => t.name.includes("slack"))' })).toBe("Inspect available tools");
  });

  it("bounds long recorded summaries without changing the source input", () => {
    const input = { title: "x".repeat(300), code: "original\ncode" };
    expect(summary("js", input)).toHaveLength(160);
    expect(input.title).toHaveLength(300);
    expect(input.code).toBe("original\ncode");
  });
});

it("explains execution tools and keeps unknown tool identities intact", () => {
  expect(toolExplanation("js")).toContain("JavaScript execution tool");
  expect(toolExplanation("exec")).toContain("can call other tools");
  expect(toolExplanation("lookup_order")).toContain("Recorded tool: lookup_order");
});
