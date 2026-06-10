import type { Metadata } from "next";
import { notFound } from "next/navigation";

import {
  FilesViz,
  StashViz,
  StreamViz,
} from "../../_components/HomePage";
import VariantLanding, { type VariantCopy } from "../_components/VariantLanding";

// Message test: one X ad per slug points here. Each page is a complete
// landing page whose hero and "How it works" tell the story of the single
// message under test; the shared sections (logos, comparisons, features,
// closing CTA) stay constant so conversion differences measure the message.
// Survey submissions email the team tagged with the slug; submissions ÷ ad
// clicks ranks the messages.
const VARIANTS: Record<string, VariantCopy> = {
  drive: {
    headline: "The Drive for your AI agents.",
    subhead:
      "Markdown, HTML, sessions, and skills — a virtual file system your agents work in.",
    showHeroFunnel: true,
    how: {
      title: "Sessions. Files. Stashes.",
      subtitle: "One Drive, two kinds of writer.",
      steps: [
        {
          n: "01",
          pill: "Sessions",
          title: "Everything lands automatically.",
          body: "Every agent run flows in — prompts, tool calls, artifacts, plan files. Nothing evaporates when the session closes.",
          viz: <StreamViz />,
        },
        {
          n: "02",
          pill: "Files",
          title: "A real file system for agents.",
          body: "Markdown, HTML, tables, folders — agents ls, find, and rg the whole tree through the CLI and MCP. And when an agent builds an HTML page, you edit the result visually in a WYSIWYG editor.",
          viz: <FilesViz />,
        },
        {
          n: "03",
          pill: "Stashes",
          title: "Share any slice.",
          body: "Bundle pages and sessions into one link. Publish to the world, share with collaborators, or fork an external Stash into your own Drive.",
          viz: <StashViz />,
        },
      ],
    },
  },
  wiki: {
    headline: "A wiki your agents read and write.",
    subhead:
      "Shared pages your team and your agents keep current — together, in real time.",
    how: {
      title: "Write. Edit. Share.",
      subtitle: "One wiki, two kinds of writer.",
      steps: [
        {
          n: "01",
          pill: "Agents",
          title: "Agents write the pages.",
          body: "Plans, ADRs, runbooks, and research notes land as real pages — kept current by the agents doing the work, not by whoever remembers to update the wiki.",
          viz: <StreamViz />,
        },
        {
          n: "02",
          pill: "Humans",
          title: "Your team edits alongside.",
          body: "Real-time editing in the browser — Markdown and WYSIWYG HTML. When an agent writes a page, your teammate sees it appear.",
          viz: <FilesViz />,
        },
        {
          n: "03",
          pill: "Shared",
          title: "Every agent reads the same wiki.",
          body: "Agents browse it like a filesystem through the CLI and MCP. Your agent already knows what mine figured out yesterday.",
          viz: <StashViz />,
        },
      ],
    },
  },
  connect: {
    headline: "Connect your agents to all your data sources.",
    subhead:
      "GitHub, Drive, Gmail, Notion, Slack, Gong and more — one place your agents can query everything.",
    how: {
      title: "Connect. Query. Land.",
      subtitle: "Every source, one workspace.",
      steps: [
        {
          n: "01",
          pill: "Sources",
          title: "Connect your sources once.",
          body: "GitHub, Drive, Gmail, Notion, Slack, Gong and more. One connection, and every agent you run can read them — no per-tool plumbing.",
          viz: <StreamViz />,
        },
        {
          n: "02",
          pill: "Query",
          title: "Agents query everything.",
          body: "Semantic and keyword search across every connected source through the CLI and MCP — the Gong call, the PR, and the doc in one query.",
          viz: <FilesViz />,
        },
        {
          n: "03",
          pill: "Output",
          title: "The answers land back.",
          body: "What your agents produce — docs, tables, reports — is saved in the same workspace, shareable as a link your team can open.",
          viz: <StashViz />,
        },
      ],
    },
  },
  assistant: {
    headline: "An AI assistant that lives in Slack and email.",
    subhead:
      "Ask it anything, right where you work — it knows everything your company has connected.",
    how: {
      title: "Connect. Ask. Remember.",
      subtitle: "An assistant with the full picture.",
      steps: [
        {
          n: "01",
          pill: "Slack",
          title: "Add it to Slack.",
          body: "Mention it in any channel and it answers from your company's actual data — docs, code, calls, and past conversations.",
          viz: <StreamViz />,
        },
        {
          n: "02",
          pill: "Knowledge",
          title: "It knows what you've connected.",
          body: "GitHub, Drive, Gmail, Notion, Gong and more. One assistant with the full picture, not another silo.",
          viz: <FilesViz />,
        },
        {
          n: "03",
          pill: "Memory",
          title: "It remembers.",
          body: "Every question, answer, and doc adds to a shared brain your whole team — and all your agents — can use.",
          viz: <StashViz />,
        },
      ],
    },
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
  return <VariantLanding variant={variant} copy={copy} />;
}
