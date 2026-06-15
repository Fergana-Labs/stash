import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Rendered-markdown view, same stack as the product app's renderer
// (react-markdown + GFM inside a `prose` article). Hook-free so it works
// in server components (read page) and client components (editor parity).
export default function MarkdownView({ content }: { content: string }) {
  return (
    <article className="prose prose-sm mx-auto max-w-[920px] px-6 py-8">
      <Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown>
    </article>
  );
}
