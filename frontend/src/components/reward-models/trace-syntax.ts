import { common, createLowlight } from "lowlight";
import type { Element, Root, RootContent } from "hast";

const syntax = createLowlight(common);
export function codeLanguage(text: string, key = "", tool = ""): string | undefined {
  if (/^(cmd|command|shell)$/i.test(key)) return "bash";
  if (/^(code|input)$/i.test(key) && /(?:^|__)(js|exec)$/.test(tool)) return "javascript";
  if (/\b(?:const|let|var)\s+\w+\s*=|\bawait\s+(?:tools|cua|page|tab)\./.test(text)) return "javascript";
  if (/^\s*(?:from \w+ import|import \w+|def \w+\()/m.test(text)) return "python";
  if (/^\s*[\[{]/.test(text)) { try { JSON.parse(text); return "json"; } catch { /* Not JSON. */ } }
  return undefined;
}

export function highlightCode(text: string, language?: string): Root | null {
  if (!language || !syntax.registered(language)) return null;
  return syntax.highlight(language, text);
}

/** Assign exact source positions before annotation mapping, including repeated tokens. */
export function rehypeTraceSyntax({ source }: { source: string }) {
  return (tree: Root) => {
    function visit(node: Root | Element) {
      if (node.type === "element" && node.tagName === "code") {
        const text = node.children.map((child) => child.type === "text" ? child.value : "").join("");
        const classes = node.properties.className as string[] | undefined;
        const language = classes?.find((name) => name.startsWith("language-"))?.slice(9) ?? codeLanguage(text);
        const highlighted = highlightCode(text, language);
        const start = node.position?.start.offset;
        const offset = start === undefined ? -1 : source.indexOf(text, start);
        if (highlighted && offset >= 0) {
          let cursor = offset;
          function position(child: RootContent) {
            const begin = cursor;
            if (child.type === "text") cursor += child.value.length;
            else if (child.type === "element") child.children.forEach(position);
            child.position = { start: { line: 1, column: 1, offset: begin }, end: { line: 1, column: 1, offset: cursor } };
          }
          highlighted.children.forEach(position);
          node.children = highlighted.children as Element["children"];
          node.properties.className = [...classes ?? [], "trace-code"];
        }
      } else for (const child of node.children) if (child.type === "element") visit(child);
    }
    visit(tree);
  };
}
