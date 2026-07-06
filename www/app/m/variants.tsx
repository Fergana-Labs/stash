import {
  FilesViz,
  SourcesViz,
  StashViz,
  StreamViz,
  type HowItWorksStep,
} from "../_components/HomePage";

export type VariantCopy = {
  headline: string;
  subhead: string;
  how: { title: string; subtitle: string; steps: HowItWorksStep[] };
};

// Message test: one X ad per slug points at /m/<slug>. Each page is a complete
// landing page whose hero and "How it works" tell the story of the single
// message under test; the shared sections stay constant so conversion
// differences measure the message. The signup CTA leads to /m/<slug>/signup;
// submissions email the team tagged with the slug.
export const VARIANTS: Record<string, VariantCopy> = {
  drive: {
    headline: "The Drive for your AI agents.",
    subhead:
      "Markdown, HTML, sessions, and skills — a virtual file system your agents work in.",
    how: {
      title: "Markdown. HTML. File system.",
      subtitle: "A Drive built for how agents work.",
      steps: [
        {
          n: "01",
          pill: "Files",
          title: "Agent-native files.",
          body: "Markdown, HTML, dashboards — even AI-native slide decks. And when an agent builds an HTML page, you edit the result visually in a WYSIWYG editor, no markup required.",
          viz: <FilesViz />,
        },
        {
          n: "02",
          pill: "VFS",
          title: "A virtual file system.",
          body: "Your agents traverse the Drive the way they traverse code — ls, find, and rg over pages, sessions, and tables through the CLI and MCP.",
          viz: <StreamViz />,
        },
        {
          n: "03",
          pill: "Sharing",
          title: "Provenance and sharing.",
          body: "Every file links back to the agent session that produced it. Share any slice with your team as one link — native collaboration, no export step.",
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
      title: "Connect. Index. Query.",
      subtitle: "Every source, one Stash.",
      steps: [
        {
          n: "01",
          pill: "Sources",
          title: "Connect your sources once.",
          body: "GitHub, Drive, Gmail, Notion, Slack, Gong, Jira and more — one easy connection per source, and every agent you run can read them.",
          viz: <SourcesViz />,
        },
        {
          n: "02",
          pill: "Index",
          title: "We index everything.",
          body: "Semantic embeddings plus a knowledge-graph file tree — a hybrid index built for how agents retrieve, kept in sync as your sources change.",
          viz: <FilesViz />,
        },
        {
          n: "03",
          pill: "Query",
          title: "Agents query anything, on demand.",
          body: "The Gong call, the PR, and the doc in one query — through the CLI and MCP, from any agent you run.",
          viz: <StreamViz />,
        },
      ],
    },
  },
  assistant: {
    headline: "An AI assistant that lives in Slack and email.",
    subhead:
      "Ask it anything, right where you work — it knows everything your company has connected.",
    how: {
      title: "Ask. Act. Remember.",
      subtitle: "An assistant that gets things done.",
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
          pill: "Act",
          title: "It does the work.",
          body: "It sends emails, updates docs, and pulls data from Jira — taking action across your tools, not just answering questions about them.",
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
