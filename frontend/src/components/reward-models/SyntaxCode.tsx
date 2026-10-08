import { Fragment, type ReactNode } from "react";
import type { RootContent } from "hast";
import { highlightCode } from "./trace-syntax";

export default function SyntaxCode({ text, language }: { text: string; language?: string }) {
  function render(node: RootContent, index: number): ReactNode {
    if (node.type === "text") return <Fragment key={index}>{node.value}</Fragment>;
    if (node.type === "element") return <span key={index} className={(node.properties.className as string[] | undefined)?.join(" ")}>{node.children.map(render)}</span>;
    return null;
  }
  const tree = highlightCode(text, language);
  return <pre className="trace-code m-0 overflow-x-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed"><code>{tree ? tree.children.map(render) : text}</code></pre>;
}
