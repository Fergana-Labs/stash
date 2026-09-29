import type { NavSection } from "./DocsShell";

// One sidebar for the whole docs site. Reward Models leads; the Stash docs
// follow at their existing /docs URLs, which other pages link to directly.
export const DOCS_NAV: NavSection[] = [
  {
    title: "Stash Reward Models",
    items: [
      { href: "/reward-models", label: "Overview" },
      { href: "/reward-models/trace-format", label: "Trace format" },
      { href: "/reward-models/annotations", label: "Annotations" },
      { href: "/reward-models/training", label: "Training" },
      { href: "/reward-models/gepa", label: "GEPA" },
      { href: "/reward-models/api", label: "API reference" },
    ],
  },
  {
    title: "Stash",
    items: [
      { href: "/docs", label: "Overview" },
      { href: "/docs/quickstart", label: "Quickstart" },
      { href: "/docs/concepts", label: "Concepts" },
      { href: "/docs/self-hosting", label: "Self-Hosting" },
    ],
  },
  {
    title: "Reference",
    items: [
      {
        href: "/docs/cli",
        label: "CLI",
        children: [
          { href: "/docs/cli#install", label: "Install" },
          { href: "/docs/cli#first-time-setup", label: "First-time setup" },
          { href: "/docs/cli#virtual-filesystem", label: "Virtual filesystem" },
          { href: "/docs/cli#authentication", label: "Authentication" },
          { href: "/docs/cli#files", label: "Files" },
          { href: "/docs/cli#sessions", label: "Sessions" },
          { href: "/docs/cli#memory", label: "Memory" },
          { href: "/docs/cli#sources-search", label: "Sources & search" },
          { href: "/docs/cli#tables", label: "Tables" },
          { href: "/docs/cli#uploaded-files", label: "Uploaded Files" },
          { href: "/docs/cli#skills", label: "Skills" },
          { href: "/docs/cli#mcp-servers", label: "MCP servers" },
          { href: "/docs/cli#keys", label: "Keys" },
          { href: "/docs/cli#streaming-hooks", label: "Streaming & hooks" },
        ],
      },
    ],
  },
  {
    title: "Project",
    items: [
      { href: "/docs/contributing", label: "Contributing" },
    ],
  },
];
