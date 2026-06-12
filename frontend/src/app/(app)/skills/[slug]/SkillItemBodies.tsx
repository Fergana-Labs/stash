"use client";

import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import HtmlPageView from "../../../../components/workspace/HtmlPageView";
import type { PublicSkillPage } from "../../../../lib/api";

// Read-only page renderer for the ?skill= fallback views — viewers who can't
// reach the workspace endpoint read the page body from the public-skill
// contents payload instead.
export function PageBody({ page }: { page: PublicSkillPage }) {
  if (page.content_type === "html") {
    return (
      <HtmlPageView
        html={page.content_html || ""}
        title={page.name}
        layout={page.html_layout}
      />
    );
  }
  return (
    <div className="markdown-content">
      <Markdown remarkPlugins={[remarkGfm]}>{page.content_markdown || ""}</Markdown>
    </div>
  );
}
