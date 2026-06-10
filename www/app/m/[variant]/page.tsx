import type { Metadata } from "next";
import { notFound } from "next/navigation";

import PaintedDoorPage, {
  type PaintedDoorCopy,
} from "../_components/PaintedDoorPage";

// Painted-door message test: one X ad per slug points here. Each page is
// built around the single message under test — hero, three proof points
// written for that message, and the lead survey. Submissions email the team
// tagged with the slug; submissions ÷ ad clicks ranks the messages.
const VARIANTS: Record<string, PaintedDoorCopy> = {
  drive: {
    headline: "The Drive for your AI agents.",
    subhead:
      "Markdown, HTML, sessions, and skills — a virtual file system your agents work in.",
    bullets: [
      {
        title: "Everything lands in one place",
        body: "Every doc, transcript, and artifact your agents produce is saved automatically. Nothing evaporates when the session closes.",
      },
      {
        title: "A real file system for agents",
        body: "Agents ls, find, and rg the whole workspace through the CLI and MCP server. One addressable tree of pages, sessions, and tables.",
      },
      {
        title: "Humans see everything",
        body: "Browse and edit your agents' files in the browser, in real time. No black-box memory, no export step.",
      },
    ],
  },
  wiki: {
    headline: "A wiki your agents read and write.",
    subhead:
      "Shared pages your team and your agents keep current — together, in real time.",
    bullets: [
      {
        title: "Agents write pages, not black-box memory",
        body: "Plans, ADRs, runbooks, and research notes that stay current because the agents doing the work update them.",
      },
      {
        title: "Your team edits alongside",
        body: "Humans and agents edit the same pages at the same time. When an agent writes, your teammate sees it appear.",
      },
      {
        title: "Every agent reads the same wiki",
        body: "Shared context across teammates and tools — your agent already knows what mine figured out yesterday.",
      },
    ],
  },
  connect: {
    headline: "Connect your agents to all your data sources.",
    subhead:
      "GitHub, Drive, Gmail, Notion, Slack, Gong and more — one place your agents can query everything.",
    bullets: [
      {
        title: "One connection, every source",
        body: "Connect a source once and every agent you run can read it. No per-tool plumbing, no copy-paste context.",
      },
      {
        title: "Works with the agents you already use",
        body: "Claude Code, Cursor, Codex, and anything that speaks MCP. Plugins stream sessions in automatically.",
      },
      {
        title: "Search by meaning",
        body: "Semantic and keyword search across everything connected — your agent finds the Gong call, the PR, and the doc in one query.",
      },
    ],
  },
  assistant: {
    headline: "An AI assistant that lives in Slack and email.",
    subhead:
      "Ask it anything, right where you work — it knows everything your company has connected.",
    bullets: [
      {
        title: "Answers in Slack",
        body: "Mention it in any channel and it answers from your company's actual data — docs, code, calls, and past conversations.",
      },
      {
        title: "Backed by everything you've connected",
        body: "GitHub, Drive, Gmail, Notion, Gong and more. One assistant with the full picture, not another silo.",
      },
      {
        title: "It remembers",
        body: "Every question, answer, and doc adds to a shared brain your whole team — and all your agents — can use.",
      },
    ],
  },
};

export function generateStaticParams() {
  return Object.keys(VARIANTS).map((variant) => ({ variant }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ variant: string }>;
}): Promise<Metadata> {
  const { variant } = await params;
  const copy = VARIANTS[variant];
  if (!copy) return {};
  return {
    title: `Stash · ${copy.headline}`,
    robots: { index: false },
  };
}

export default async function VariantPage({
  params,
}: {
  params: Promise<{ variant: string }>;
}) {
  const { variant } = await params;
  const copy = VARIANTS[variant];
  if (!copy) notFound();
  return <PaintedDoorPage variant={variant} copy={copy} />;
}
