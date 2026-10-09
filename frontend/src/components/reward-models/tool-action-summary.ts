import type { RmStep } from "@/lib/types";
import { toolFamily, toolLabel } from "./trace-rows";

function short(value: unknown, max = 160): string | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const text = value.replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function shellAction(command: string): string {
  if (/^(?:(?:npx|uv run|python3? -m)\s+)?(?:vitest|pytest|jest)\b|^(?:npm|pnpm|yarn) (?:run )?test\b/.test(command.trim())) return "Run tests";
  if (/^(?:(?:npx|uv run)\s+)?(?:eslint|ruff|tsc)\b/.test(command.trim())) return "Check code quality";
  if (/^gh pr create\b/.test(command.trim())) return "Create a pull request";
  if (/^git push\b/.test(command.trim())) return "Push repository changes";
  if (/^git (?:status|diff|log)\b/.test(command.trim())) return "Inspect repository changes";
  if (/^(?:rg|grep|find)\b/.test(command.trim())) return "Search files";
  if (/^(?:cat|sed|head|tail)\b/.test(command.trim())) return "Read files";
  if (/^ls\b/.test(command.trim())) return "List files";
  if (/^pwd\b/.test(command.trim())) return "Check the working directory";
  return "Run a shell command";
}

function action(name: string, input: Record<string, unknown>): string {
  const lower = name.toLowerCase();
  const bare = lower.split(/__|\./).at(-1)!;
  const path = short(input.file_path ?? input.path);
  const query = short(input.query ?? input.q ?? input.pattern);
  if (/slack.*search.*channel/.test(lower)) return "Find Slack channels";
  if (/slack.*search/.test(lower)) return "Search Slack messages";
  if (/slack.*read_channel/.test(lower)) return "Read Slack messages";
  if (/clock.*curr_time/.test(lower)) return "Check the current time";
  if (bare === "sleep") return typeof input.duration_ms === "number" ? `Wait ${input.duration_ms / 1000} seconds` : "Wait";
  if (bare === "view_image") return "Inspect an image";
  if (/request_user_input|ask_user|askuserquestion/.test(bare)) return "Ask the user a question";
  if (/spawn_agent/.test(bare)) return "Delegate work to a subagent";
  if (/wait_agent/.test(bare)) return "Wait for subagent results";
  if (typeof input.cmd === "string" || typeof input.command === "string") return shellAction(String(input.cmd ?? input.command));
  if (bare === "exec_command" || bare === "bash" || bare === "shell") return "Run a shell command";
  if (bare === "apply_patch") return "Edit files";
  if (/web.*run/.test(lower) || toolFamily(name) === "web") {
    const searches = Array.isArray(input.search_query) ? input.search_query : [];
    if (query || searches.length) return query ? `Search the web for ${query}` : "Search the web";
    const url = short(input.url ?? input.ref_id);
    if (url) { try { return `Read ${new URL(url).hostname}`; } catch { /* Use the general action. */ } }
    return "Read web pages";
  }
  switch (toolFamily(bare)) {
    case "read": return path ? `Read ${path}` : "Read a file";
    case "edit": return path ? `Edit ${path}` : "Edit files";
    case "write": return path ? `Write ${path}` : "Write a file";
    case "search": return query ? `Search for ${query}` : "Search files";
    case "agent": return "Delegate work to a subagent";
    case "task": return "Update the task plan";
    case "skill": return "Load a skill";
    case "browser": return "Interact with the browser";
    default: return `Use ${toolLabel(name)}`;
  }
}

/** Read literal arguments in a recorded tool wrapper, without evaluating its code. */
function literalArguments(source: string): Record<string, unknown> {
  const input: Record<string, unknown> = {};
  for (const key of ["cmd", "command", "path", "file_path", "query", "q", "url", "ref_id"]) {
    const match = source.match(new RegExp(`\\b${key}["']?\\s*:\\s*("(?:\\\\.|[^"\\\\])*")`));
    if (match) { try { input[key] = JSON.parse(match[1]); } catch { /* Unknown syntax gets a general action. */ } }
  }
  return input;
}

/** Describe the recorded action, never infer whether it succeeded from the result. */
export function toolActionSummary(step: Pick<RmStep, "tool_name" | "tool_input">): string {
  const input = step.tool_input ?? {};
  const recorded = short(input.title) ?? short(input.description);
  if (recorded) return recorded;
  const name = step.tool_name ?? "tool";
  if (/^(?:exec|js)$/.test(name.toLowerCase())) {
    const source = typeof input.input === "string" ? input.input : typeof input.code === "string" ? input.code : "";
    const calls = [...source.matchAll(/\btools\.([\w]+)\s*\(/g)];
    const actions = [...new Set(calls.map((call, index) => action(call[1], literalArguments(source.slice(call.index, calls[index + 1]?.index)))))];
    if (actions.length) return short(actions.join(" · "))!;
    if (/\bALL_TOOLS\b/.test(source)) return "Inspect available tools";
    return name.toLowerCase() === "js" ? "Run JavaScript" : "Run a script";
  }
  return short(action(name, input))!;
}

export function toolExplanation(name: string | null): string {
  const bare = name?.toLowerCase().split(/__|\./).at(-1);
  if (bare === "js") return "JavaScript execution tool. Runs the code input; title describes the action.";
  if (bare === "exec") return "Script execution tool. Runs the input script, which can call other tools.";
  if (toolFamily(name) === "shell") return "Shell execution tool. Runs a command and returns its output.";
  if (toolFamily(name) === "read") return "File reading tool. Returns the contents of the requested file.";
  if (toolFamily(name) === "edit" || toolFamily(name) === "write") return "File editing tool. Applies the changes specified in its inputs.";
  if (toolFamily(name) === "search") return "Search tool. Finds content matching the supplied query or pattern.";
  if (toolFamily(name) === "browser") return "Browser tool. Performs the requested action in a browser.";
  return `Recorded tool: ${name ?? "unknown"}. Expand the step to inspect its inputs and output.`;
}
