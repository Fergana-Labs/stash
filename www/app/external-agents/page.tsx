import type { Metadata } from "next";
import Link from "next/link";

import SiteHeader from "../_components/SiteHeader";

export const metadata: Metadata = {
  alternates: { canonical: "/external-agents" },
  title: "External agents · Stash docs",
  description:
    "Memory for the agents that answer your customers: capture production runs, refine them into context, and serve that context back before the next answer.",
};

const SIDEBAR: [string, [string, string][]][] = [
  [
    "External agents",
    [
      ["Overview", "#overview"],
      ["Why production agents need memory", "#problem"],
      ["The correction loop", "#loop"],
      ["Recall", "#recall"],
      ["Permission and isolation", "#isolation"],
      ["Audit", "#audit"],
    ],
  ],
  [
    "Internal agents",
    [
      ["Overview", "/internal-agents"],
      ["Plugins and capture", "/docs/quickstart"],
      ["Skills", "/docs/cli"],
    ],
  ],
  [
    "API",
    [
      ["Quickstart", "/docs/quickstart"],
      ["CLI reference", "/docs/cli"],
      ["MCP server", "/docs"],
      ["Virtual filesystem", "/docs"],
    ],
  ],
  [
    "Operate",
    [
      ["Self-hosting", "/docs/self-hosting"],
      ["Postgres", "/docs/self-hosting"],
      ["Retention and deletion", "/privacy"],
    ],
  ],
];

const TOC: [string, string, boolean][] = [
  ["Overview", "#overview", false],
  ["Why production agents need memory", "#problem", false],
  ["The correction loop", "#loop", false],
  ["What gets written", "#written", true],
  ["Recall", "#recall", false],
  ["Permission and isolation", "#isolation", false],
  ["Audit", "#audit", false],
  ["Next steps", "#next", false],
];

export default function ExternalAgentsPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="bg-inverted text-on-inverted-dim">
        <div className="flex flex-wrap items-center justify-center gap-3.5 px-5 py-2.5 text-[13.5px]">
          <span>Stash is state of the art on the standard memory benchmarks.</span>
          <Link
            href="/blog"
            className="rounded-full border border-white/15 px-3 py-0.5 text-[12.5px] text-on-inverted transition hover:border-brand hover:text-brand"
          >
            Read the method →
          </Link>
        </div>
      </div>

      <SiteHeader current="External agents" wide />

      <div className="grid grid-cols-1 items-start lg:grid-cols-[272px_minmax(0,1fr)] xl:grid-cols-[272px_minmax(0,1fr)_232px]">
        <aside className="sticky top-16 hidden h-[calc(100vh-4rem)] overflow-y-auto border-r border-border-subtle px-[18px] pb-16 pt-6 lg:block">
          {SIDEBAR.map(([group, items]) => (
            <div key={group} className="mb-6">
              <p className="mb-2 px-2.5 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
                {group}
              </p>
              {items.map(([label, href]) => (
                <Link
                  key={label + href}
                  href={href}
                  className={`block rounded-[7px] px-2.5 py-[7px] text-[14px] transition ${
                    label === "Overview" && href === "#overview"
                      ? "bg-brand-soft font-medium text-brand"
                      : "text-dim hover:bg-surface hover:text-ink"
                  }`}
                >
                  {label}
                </Link>
              ))}
            </div>
          ))}
        </aside>

        <article className="max-w-[840px] px-5 pb-24 pt-8 sm:px-8 lg:px-16">
          <div className="flex flex-wrap items-center gap-3.5 rounded-[10px] border border-border-subtle bg-white px-3.5 py-[11px] text-[14px] text-dim">
            <span className="font-mono text-brand">&gt;_</span>
            <span>Building with a coding agent?</span>
            <Link
              href="/docs/quickstart"
              className="ml-auto inline-flex h-8 items-center rounded-lg border border-border-subtle bg-surface px-3 font-mono text-[12.5px] text-ink transition hover:border-brand"
            >
              stash skills install stash-memory
            </Link>
          </div>

          <h1
            id="overview"
            className="mt-8 scroll-mt-24 font-display text-[40px] font-medium leading-[1.08] tracking-[-0.03em] text-ink"
          >
            External agents
          </h1>
          <p className="mt-2.5 text-[17px] text-dim">
            Memory for the agents that answer your customers.
          </p>

          <P>
            An external agent runs in production, in front of a customer. It answers a request,
            calls your tools, and closes the conversation. Stash captures those runs, refines them
            into context, and serves that context back before the next answer.
          </P>
          <P>
            This page explains why production agents need a memory layer, and what Stash does about
            it. For the agents your own team runs, see{" "}
            <Link
              href="/internal-agents"
              className="text-brand-ink underline decoration-brand/40 underline-offset-[3px]"
            >
              internal agents
            </Link>
            .
          </P>

          <H2 id="problem">Why production agents need memory</H2>
          <P>
            An agent in production repeats its errors. Every conversation starts with no record of
            the last one, so the same wrong answer comes back in a different ticket a week later.
          </P>
          <P>
            <b className="font-medium text-ink">The problem is harder than it looks:</b>
          </P>
          <ul className="mt-4 list-disc pl-5">
            <Li term="A prompt is not a memory store">
              corrections get appended to a system prompt until it is thousands of tokens long and
              nobody knows which line is still load-bearing.
            </Li>
            <Li term="Similarity is not relevance">
              “what did this customer agree to last spring” needs reasoning about time and scope,
              not the nearest vector.
            </Li>
            <Li term="Facts arrive disconnected">
              one run learns the part number, another learns the warranty rule. The agent has to
              join them to answer at all.
            </Li>
            <Li term="Context is not global">
              the same fact means different things for different customers, and one customer&apos;s
              context must never reach another one&apos;s answer.
            </Li>
          </ul>

          <div className="mt-6 flex gap-3 rounded-lg border border-border-subtle border-l-[3px] border-l-brand bg-white px-4 py-3.5 text-[14.5px]">
            <span className="font-mono text-brand">i</span>
            <span>
              Stash treats recall as a reasoning problem rather than a search problem. That
              distinction drives the whole architecture, and it is where our benchmark results come
              from.
            </span>
          </div>

          <H2 id="loop">The correction loop</H2>
          <P>
            Each production run produces a log. Stash refines the log into a document, and the next
            run reads the document before it answers. No prompt is edited and no deploy is needed.
          </P>
          <pre className="mt-5 overflow-x-auto rounded-[10px] bg-inverted px-5 py-[18px] font-mono text-[13px] leading-[1.9] text-[rgba(250,248,245,0.7)]">
            <span className="text-[rgba(250,248,245,0.36)]"># run 1841</span>
            {"\n"}
            <span className="text-[#FBF8F3]">request</span>   part for unit 44, under warranty
            {"\n"}
            <span className="text-[#FBF8F3]">answer</span>    <span className="text-[rgba(250,248,245,0.36)]">wrong part number returned</span>
            {"\n"}
            <span className="text-[#FBF8F3]">operator</span>  supplied the correct SKU
            {"\n\n"}
            <span className="text-[rgba(250,248,245,0.36)]"># refine</span>
            {"\n"}
            <span className="text-brand">→</span> <span className="text-[#FBF8F3]">parts/lookup-rules.md</span>{" "}
            <span className="text-[#6FCF97]">updated</span>
            {"\n"}
            <span className="text-brand">→</span> <span className="text-[#FBF8F3]">skill: warranty-check</span>{" "}
            <span className="text-[#6FCF97]">created</span>
            {"\n\n"}
            <span className="text-[rgba(250,248,245,0.36)]"># run 1842</span>
            {"\n"}
            <span className="text-brand">›</span> <span className="text-[#FBF8F3]">read</span> parts/lookup-rules.md
            {"\n"}
            <span className="text-[#6FCF97]">✓</span> correct part returned, no escalation
          </pre>

          <h3
            id="written"
            className="mt-8 scroll-mt-24 font-display text-[18px] font-medium tracking-[-0.02em] text-ink"
          >
            What gets written
          </h3>
          <P>
            A correction becomes a page. Work that repeats becomes a skill: a folder with a{" "}
            <Code>SKILL.md</Code> and the files that support it, which the agent loads on the next
            run.
          </P>

          <H2 id="recall">Recall</H2>
          <P>
            Recall returns the smallest set of facts that changes the answer. Two properties decide
            whether it is correct.
          </P>
          <table className="mt-5 w-full border-collapse bg-white text-[14.5px]">
            <thead>
              <tr>
                {["Property", "What it means", "What breaks without it"].map((h) => (
                  <th
                    key={h}
                    className="border border-border-subtle bg-surface px-3.5 py-2.5 text-left font-mono text-[11.5px] font-medium uppercase tracking-[0.1em] text-ink"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="border border-border-subtle px-3.5 py-2.5 align-top">
                  <b className="font-medium text-ink">Blast radius</b>
                </td>
                <td className="border border-border-subtle px-3.5 py-2.5 align-top">
                  The scope of history the agent may draw on, by customer, product, and time.
                </td>
                <td className="border border-border-subtle px-3.5 py-2.5 align-top">
                  The agent answers with a fact that was true for a different customer or a past
                  quarter.
                </td>
              </tr>
              <tr>
                <td className="border border-border-subtle px-3.5 py-2.5 align-top">
                  <b className="font-medium text-ink">Stability</b>
                </td>
                <td className="border border-border-subtle px-3.5 py-2.5 align-top">
                  New information lands without removing what is still correct, as the store grows.
                </td>
                <td className="border border-border-subtle px-3.5 py-2.5 align-top">
                  Quality falls month over month, and old corrections quietly stop applying.
                </td>
              </tr>
            </tbody>
          </table>

          <H2 id="isolation">Permission and isolation</H2>
          <P>
            Memory that crosses a user boundary is a security incident, not a bad answer. Stash
            scopes every memory to an owner and resolves permission at read time, using the access
            controls that databases have had for decades.
          </P>
          <ul className="mt-4 list-disc pl-5">
            <Li term="Scoped by default">a memory belongs to one owner. Sharing is explicit.</Li>
            <Li term="Resolved at read">the agent sees only what the caller is allowed to see.</Li>
            <Li term="Deletion propagates">
              removing a source removes what was derived from it.
            </Li>
          </ul>

          <H2 id="audit">Audit</H2>
          <P>
            Every run is legible after the fact: the context the agent read, the tools it called,
            and the answer it gave. Each change to the memory keeps its origin, so a correction can
            be traced to the run and the person it came from.
          </P>
          <P>
            Run Stash on your own Postgres, inside your own network. The code is MIT licensed, so
            nothing about the memory layer is a black box.
          </P>

          <H2 id="next">Next steps</H2>
          <div className="mt-6 grid grid-cols-1 gap-3.5 sm:grid-cols-2">
            {[
              ["Quickstart →", "Connect one production agent and see the first refined page.", "/docs/quickstart"],
              ["MCP server →", "Serve memory to any agent that speaks MCP.", "/docs"],
              ["Self-hosting →", "Run the whole stack on your own Postgres.", "/docs/self-hosting"],
              ["Internal agents →", "The same layer for the agents your team runs.", "/internal-agents"],
            ].map(([title, body, href]) => (
              <Link
                key={title}
                href={href}
                className="rounded-[10px] border border-border-subtle bg-white p-[18px] transition hover:border-brand"
              >
                <span className="font-display font-medium text-ink">{title}</span>
                <p className="mt-1.5 text-[14px] text-dim">{body}</p>
              </Link>
            ))}
          </div>

          <div className="mt-16 flex flex-wrap justify-between gap-3 border-t border-border-subtle pt-5 font-mono text-[11.5px] text-muted">
            <span>© {new Date().getFullYear()} Fergana Labs</span>
            <span>MIT licensed · self-hostable</span>
          </div>
        </article>

        <aside className="sticky top-16 hidden h-[calc(100vh-4rem)] overflow-y-auto px-5 pb-16 pt-10 xl:block">
          <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
            On this page
          </p>
          {TOC.map(([label, href, sub]) => (
            <a
              key={href + label}
              href={href}
              className={`block border-l-2 py-[5px] text-[13.5px] transition ${
                sub ? "pl-6 text-[13px]" : "pl-3"
              } ${
                label === "Overview"
                  ? "border-brand text-brand"
                  : "border-border-subtle text-dim hover:text-ink"
              }`}
            >
              {label}
            </a>
          ))}
        </aside>
      </div>
    </main>
  );
}

function H2({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h2
      id={id}
      className="mt-13 scroll-mt-24 border-b border-border-subtle pb-2.5 font-display text-[25px] font-medium tracking-[-0.02em] text-ink"
      style={{ marginTop: "52px" }}
    >
      {children}
    </h2>
  );
}

function P({ children }: { children: React.ReactNode }) {
  return <p className="mt-4 text-[15.5px] leading-[1.65]">{children}</p>;
}

function Li({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <li className="mt-2.5 text-[15.5px] leading-[1.65]">
      <b className="font-medium text-ink">{term}</b> — {children}
    </li>
  );
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded border border-border-subtle bg-surface px-1.5 py-0.5 font-mono text-[13px] text-ink">
      {children}
    </code>
  );
}
