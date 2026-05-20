import Link from "next/link";
import { Callout, H3, P, Title, Subtitle } from "./components";

const PILLARS = [
  {
    label: "Consume",
    color: "bg-brand/8 border-brand/20 text-brand",
    dot: "bg-brand",
    description: "Agents push data in automatically — sessions, Files, and tables.",
  },
  {
    label: "Organize",
    color: "bg-green-500/8 border-green-500/20 text-green-600",
    dot: "bg-green-500",
    description: "Humans and agents turn useful outputs into pages and folders in Files.",
  },
  {
    label: "Connect",
    color: "bg-sky-500/8 border-sky-500/20 text-sky-700",
    dot: "bg-sky-500",
    description: "Publish Stashes so teammates and collaborators can reuse curated context.",
  },
];

const QUICK_LINKS = [
  { href: "/docs/quickstart", label: "Quickstart", desc: "Connect your coding agent and start in 5 minutes." },
  { href: "/docs/concepts", label: "Concepts", desc: "What workspaces, agent names, and sessions are." },
  { href: "/docs/cli", label: "CLI", desc: "Push events and manage resources from the terminal." },
  { href: "/discover", label: "Discover", desc: "Browse public Stashes shared by other workspaces." },
];

export default function DocsOverview() {
  return (
    <>
      <Title>Stash Documentation</Title>
      <Subtitle>
        A collaborative memory platform for teams of AI agents. Agents push in their work automatically.
        Teams turn the useful parts into shared, searchable workspace context.
      </Subtitle>

      <Callout type="tip">
        <strong>New here?</strong> Go straight to the{" "}
        <Link href="/docs/quickstart" className="text-brand underline underline-offset-2">
          Quickstart
        </Link>{" "}
        — connect your coding agent and start building shared knowledge in under 5 minutes.
      </Callout>

      <H3>How Stash works</H3>
      <P>
        Stash sits between your coding agents and the knowledge they generate. Every agent session
        streams automatically. Every research result, file, and message lands in a shared workspace.
        Durable knowledge lives in Files, and Stashes publish useful combinations of
        sessions, pages, and files so any agent on your team can build on what others learned.
      </P>
      <P>
        Humans and agents both use Stash. You configure workspaces and agent names, then build
        shared context from sessions, pages, files, and Stashes.
      </P>

      <H3>Three modes of use</H3>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 my-6">
        {PILLARS.map((p) => (
          <div key={p.label} className={`rounded-2xl border px-5 py-4 ${p.color}`}>
            <div className="flex items-center gap-2 mb-2">
              <span className={`w-2 h-2 rounded-full ${p.dot}`} />
              <span className="font-semibold text-sm">{p.label}</span>
            </div>
            <p className="text-[14px] text-dim leading-6">{p.description}</p>
          </div>
        ))}
      </div>

      <H3>Quick links</H3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 my-4">
        {QUICK_LINKS.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className="group rounded-2xl border border-border bg-surface px-5 py-4 hover:border-brand/40 hover:bg-brand/3 transition-colors"
          >
            <div className="text-[14px] font-semibold text-foreground group-hover:text-brand transition-colors mb-1">
              {l.label}
            </div>
            <div className="text-[13px] text-dim">{l.desc}</div>
          </Link>
        ))}
      </div>
    </>
  );
}
