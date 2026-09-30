export interface OutputRun {
  text: string;
  offset: number | null;
}

/** Add display whitespace without rewriting values or losing quote offsets in the original output. */
export function toolOutputRuns(content: string): OutputRun[] {
  if (!/^[\s]*[\[{]/.test(content)) return [{ text: content, offset: 0 }];
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
    runs.push({ text: token, offset: tokens[i].index });
    if (token === "{" || token === "[") {
      depth++;
      if (next !== "}" && next !== "]") line();
    } else if (token === ",") line();
    else if (token === ":") runs.push({ text: " ", offset: null });
  }
  return runs;
}
