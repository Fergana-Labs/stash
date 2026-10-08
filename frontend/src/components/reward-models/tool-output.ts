export interface OutputRun {
  text: string;
  offset: number | null;
  sourceLength?: number;
}

/** Add display whitespace without rewriting values or losing quote offsets in the original output. */
export function toolOutputRuns(content: string): OutputRun[] {
  if (!/^[\s]*[\[{"]/.test(content)) {
    // Codex wraps structured results in "Script completed … Output:" text.
    const embedded = /\n(?=[ \t]*(?:\{"|\[\{))/.exec(content);
    if (embedded) {
      const start = embedded.index + 1;
      return [{ text: content.slice(0, start), offset: 0 }, ...toolOutputRuns(content.slice(start)).map((run) => ({ ...run, offset: run.offset === null ? null : start + run.offset }))];
    }
    return [{ text: content, offset: 0 }];
  }
  const tokens = [...content.matchAll(/"(?:\\.|[^"\\])*"|[{}\[\],:]|[^\s{}\[\],:]+/g)];
  const runs: OutputRun[] = [];
  let depth = 0;
  const line = () => runs.push({ text: `\n${"  ".repeat(depth)}`, offset: null });
  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i][0];
    const previous = i > 0 ? tokens[i - 1][0] : null;
    const next = i + 1 < tokens.length ? tokens[i + 1][0] : null;
    if (previous !== null && !/^[{}\[\],:]$/.test(previous) && !/^[{}\[\],:]$/.test(token)) {
      const offset = tokens[i - 1].index + previous.length;
      runs.push({ text: content.slice(offset, tokens[i].index), offset });
    }
    if (token === "}" || token === "]") {
      depth = Math.max(0, depth - 1);
      if (previous !== "{" && previous !== "[") line();
    }
    if (token.startsWith('"') && token.endsWith('"')) {
      // Decode JSON strings into readable output. Keep escape boundaries mapped
      // to their original bytes so selecting output still anchors a valid quote.
      const body = token.slice(1, -1);
      for (const part of body.matchAll(/\\u[dD][89abAB][\da-fA-F]{2}\\u[dD][c-fC-F][\da-fA-F]{2}|\\u[\da-fA-F]{4}|\\.|[^\\]+/g)) {
        let text = part[0];
        if (text.startsWith("\\")) { try { text = JSON.parse(`"${text}"`) as string; } catch { /* Keep malformed recorded escapes verbatim. */ } }
        runs.push({ text, offset: tokens[i].index + 1 + part.index, sourceLength: part[0].length });
      }
    } else runs.push({ text: token, offset: tokens[i].index });
    if (token === "{" || token === "[") {
      depth++;
      if (next !== "}" && next !== "]") line();
    } else if (token === ",") line();
    else if (token === ":") runs.push({ text: " ", offset: null });
  }
  return runs;
}
