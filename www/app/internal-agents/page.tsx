import type { Metadata } from "next";
import Link from "next/link";

import SiteFooter from "../_components/SiteFooter";
import SiteHeader from "../_components/SiteHeader";
import CodePanel from "./CodePanel";

const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";
const SIGNUP_URL = `${APP_URL}/login?mode=register`;
const GITHUB_URL = "https://github.com/Fergana-Labs/stash";

export const metadata: Metadata = {
  alternates: { canonical: "/internal-agents" },
  title: "Internal agents · Stash",
  description:
    "Stash is memory for your agents that starts working with one prompt. Import your existing agent logs, and stop repeating yourself immediately.",
};

const GAINS = [
  ["Less explaining", "You stop repeating the same context. It is written down already, and the agent reads it first."],
  ["Useful on day one", "We import the logs you already have. The first run is better, not the hundredth."],
  ["Longer runs", "The agent checks in less, so it carries a longer task without a person in the loop."],
  ["Fewer tokens", "It reads one refined page instead of re-deriving the answer across a long transcript."],
  ["Lower latency", "A short, scoped read returns faster than a long context window or a wide search."],
  ["Find anything", "Search everything you and your agents have written or said before, in one place."],
];

const SHARING = [
  ["Everyone reads the same context", "A skill written from one person's session loads for the whole team. Nobody has to be told it exists."],
  ["Humans and agents edit the same files", "Pages are Markdown, HTML, CSV, and PDF. A teammate corrects a page, and the agent reads the correction on its next run."],
  ["Send a session as a link", "Share one session or a whole folder. The person who opens it sees the transcript and the files that came out of it."],
  ["Publish what is worth publishing", "Make a skill public and it gets a URL. Another team installs it with one command."],
];

const OWNERSHIP = [
  ["Open source", "MIT licensed. Read the code, fork it, and run the same thing we run."],
  ["Self-hostable, or managed", "Run the whole stack inside your own network, on your own Postgres. Or use our managed cloud and skip the operations work."],
  ["Plain files, no lock-in", "Pages, tables, and skills are ordinary files in formats you already use. You can take them with you."],
  ["Bring your own agents", "Claude Code, Codex, Cursor, OpenCode, Openclaw, and Hermes write into the same Stash. You are not tied to one harness or one model."],
];

const RESEARCH = [
  ["Blast radius", "The correct slice of history changes with the time, the project, and the person who asks."],
  ["Stability", "New information must not remove what is still correct, and quality must not fall as the store grows."],
  ["Native primitives", "Models are post-trained on bash and markdown. We serve memory through those, not a special API."],
  ["State of the art", "We have achieved SOTA results on LongMemEval and LoCoMo."],
];

export default function InternalAgentsPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <SiteHeader current="Internal agents" />

      <section className="px-5 pb-8 pt-14 text-center sm:px-7 md:pt-24">
        <div className="mx-auto max-w-[780px]">
          <a
            href={GITHUB_URL}
            className="inline-block border-b border-border pb-0.5 text-[14.5px] text-dim transition hover:border-brand hover:text-brand"
          >
            Open source · MIT licensed
          </a>
          <h1 className="mt-6 font-display text-[clamp(38px,5.4vw,64px)] font-medium leading-[1.05] tracking-[-0.03em] text-ink">
            Stop babysitting your <span className="text-brand">agents.</span>
          </h1>
          <p className="mx-auto mt-[22px] max-w-[52ch] text-[18px] leading-[1.6] text-dim">
            Stash is memory for your agents that starts working with one prompt. Import your
            existing agent logs, and stop repeating yourself immediately.
          </p>
          <div className="mt-[30px] flex flex-wrap justify-center gap-3">
            <Link
              href={SIGNUP_URL}
              className="inline-flex h-[46px] items-center rounded-[10px] bg-brand px-5 text-[15px] font-medium text-white transition hover:bg-brand-hover"
            >
              Sign up free
            </Link>
            <Link
              href="/docs/quickstart"
              className="inline-flex h-[46px] items-center rounded-[10px] border border-border px-5 text-[15px] font-medium text-ink transition hover:border-ink"
            >
              Set up for an agent
            </Link>
          </div>
        </div>
        <CodePanel />
      </section>

      <Section title="Right now, you are the memory.">
        <p className="mx-auto mt-[18px] max-w-[56ch] text-[17px] leading-[1.6] text-dim">
          Agents do not learn from feedback, and they do not learn from the mistakes they made last
          week. So a person carries the context between runs. You repeat the same corrections, and
          you watch the agent to catch the same errors.
        </p>
        <div className="mx-auto mt-11 grid max-w-[1060px] grid-cols-1 gap-x-14 text-left md:grid-cols-2">
          {GAINS.map(([title, body]) => (
            <div key={title} className="grid grid-cols-[16px_minmax(0,1fr)] gap-3 border-t border-border-subtle py-4">
              <i className="mt-[9px] block h-1.5 w-1.5 rounded-full bg-brand" />
              <div>
                <b className="block font-display text-[16.5px] font-medium tracking-[-0.02em] text-ink">
                  {title}
                </b>
                <span className="mt-1 block text-[15px] leading-[1.6] text-dim">{body}</span>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Import, refine, serve.">
        <div className="mx-auto mt-10 max-w-[1060px] border-t border-border-subtle text-left">
          <Step n="01" title="Import your existing logs">
            <p>
              Stash reads the sessions already on disk from Claude Code, Cursor, Codex, and
              OpenCode. New sessions stream in through one plugin.
            </p>
            <Terminal cap={["terminal", "stash cli"]}>
              <span className="text-brand">$</span>{" "}
              <span className="text-ink">stash import</span> ~/.claude/projects
              {"\n"}
              <span className="text-muted">412 sessions · 18.4M tokens</span>
              {"\n"}
              <span className="text-muted">capture is on for new runs</span>
            </Terminal>
          </Step>
          <Step n="02" title="Refine them using sleep-time compute">
            <p>
              Work that repeats becomes a skill: a folder with a <Code>SKILL.md</Code> that an agent
              installs and loads on the next run. The rest becomes a wiki of pages that your team
              and your agents both read.
            </p>
            <figure className="m-0">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/screens/drive.webp"
                alt="The Stash app: a file tree of Clips, Notes, Projects, and Travel next to an open page called weekly-review."
                className="block w-full rounded-[10px] border border-border-subtle"
              />
              <figcaption className="mt-2.5 font-mono text-[11.5px] text-muted">
                Pages and folders, written from sessions.
              </figcaption>
            </figure>
          </Step>
          <Step n="03" title="Serve as a virtual file system or MCP">
            <p>
              Your Stash mounts over MCP and the CLI. Agents run <Code>ls</Code>, <Code>find</Code>,
              and <Code>rg</Code> against it. There is no new API.
            </p>
            <Terminal cap={["claude-code", "stash cli"]}>
              <span className="text-brand">›</span> <span className="text-ink">stash vfs</span>{" "}
              &quot;rg &apos;rate-limit&apos; /&quot;
              {"\n"}
              <span className="text-muted">8 hits · files/gateway-limits.md</span>
              {"\n"}
              <span className="text-muted">{"        · sessions/sam:tue-14:22"}</span>
            </Terminal>
          </Step>
        </div>
      </Section>

      <Section title="One memory, shared by the whole team.">
        <p className="mx-auto mt-[18px] max-w-[56ch] text-[17px] leading-[1.6] text-dim">
          An agent session is not private work. When one engineer&apos;s agent works something out,
          every other agent and every teammate should be able to read it on the next run.
        </p>
        <TwoCol items={SHARING} />
      </Section>

      <section className="border-t border-border-subtle py-16 md:py-28">
        <div className="mx-auto max-w-[1180px] px-5 sm:px-7">
          <h2 className="max-w-[18ch] font-display text-[clamp(28px,3.6vw,46px)] font-medium leading-[1.06] tracking-[-0.028em] text-ink">
            Your data, and the intelligence built from it.
          </h2>
          <p className="mt-[18px] max-w-[58ch] text-[17px] leading-[1.6] text-dim">
            A memory layer accumulates value with every run. That value should accumulate inside
            something you own, not inside a vendor you rent.
          </p>
          <ol className="mt-8">
            {OWNERSHIP.map(([title, body], i) => (
              <li
                key={title}
                className="grid grid-cols-[44px_minmax(0,1fr)] items-baseline gap-x-4 gap-y-1 border-t border-border-subtle py-[22px] last:border-b lg:grid-cols-[62px_minmax(0,1fr)_minmax(0,1.25fr)] lg:gap-x-11"
              >
                <span className="font-mono text-[12px] text-muted">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <h3 className="font-display text-[clamp(19px,2vw,23px)] font-medium tracking-[-0.028em] text-ink">
                  {title}
                </h3>
                <p className="col-start-2 text-[15.5px] leading-[1.6] text-dim lg:col-start-3">
                  {body}
                </p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <Section title="Memory is not just a retrieval problem.">
        <p className="mx-auto mt-[18px] max-w-[56ch] text-[17px] leading-[1.6] text-dim">
          Vector search and knowledge graphs return things that look like the question. They do not
          decide what is still true, what applies here, or what to leave out. We treat recall as
          reasoning, and that is where our benchmark results come from.
        </p>
        <TwoCol items={RESEARCH} />
      </Section>

      <section className="border-t border-border-subtle py-20 text-center md:py-32">
        <div className="mx-auto max-w-[1180px] px-5 sm:px-7">
          <h2 className="mx-auto max-w-[16ch] font-display text-[clamp(32px,4.4vw,54px)] font-medium leading-[1.06] tracking-[-0.028em] text-ink">
            One prompt to start.
          </h2>
          <p className="mx-auto mt-[18px] max-w-[56ch] text-[17px] text-dim">
            Your agent will know you better in minutes.
          </p>
          <div className="mt-7 flex flex-wrap justify-center gap-3">
            <Link
              href={SIGNUP_URL}
              className="inline-flex h-[46px] items-center rounded-[10px] bg-brand px-5 text-[15px] font-medium text-white transition hover:bg-brand-hover"
            >
              Sign up free
            </Link>
            <Link
              href="/contact-sales"
              className="inline-flex h-[46px] items-center rounded-[10px] border border-border px-5 text-[15px] font-medium text-ink transition hover:border-ink"
            >
              Book a call
            </Link>
          </div>
        </div>
      </section>

      <SiteFooter />
    </main>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-border-subtle py-16 text-center md:py-28">
      <div className="mx-auto max-w-[1180px] px-5 sm:px-7">
        <h2 className="mx-auto max-w-[20ch] font-display text-[clamp(28px,3.6vw,46px)] font-medium leading-[1.06] tracking-[-0.028em] text-ink">
          {title}
        </h2>
        {children}
      </div>
    </section>
  );
}

function TwoCol({ items }: { items: string[][] }) {
  return (
    <div className="mx-auto mt-10 grid max-w-[1060px] grid-cols-1 gap-x-16 text-left md:grid-cols-2">
      {items.map(([title, body]) => (
        <div key={title} className="border-t border-border-subtle py-[18px]">
          <h3 className="text-[16px] font-medium text-ink">{title}</h3>
          <p className="mt-1.5 text-[15px] leading-[1.6] text-dim">{body}</p>
        </div>
      ))}
    </div>
  );
}

function Step({
  n,
  title,
  children,
}: {
  n: string;
  title: string;
  children: React.ReactNode;
}) {
  const [body, artifact] = children as React.ReactNode[];
  return (
    <div className="grid grid-cols-1 items-start gap-5 border-b border-border-subtle py-8 md:grid-cols-[74px_minmax(0,0.85fr)_minmax(0,1.15fr)] md:gap-x-14 md:py-11">
      <span className="font-mono text-[12px] text-muted">{n}</span>
      <div>
        <h3 className="font-display text-[clamp(20px,2.1vw,25px)] font-medium tracking-[-0.028em] text-ink">
          {title}
        </h3>
        <div className="mt-3 text-[15.5px] leading-[1.6] text-dim">{body}</div>
      </div>
      {artifact}
    </div>
  );
}

function Terminal({ cap, children }: { cap: [string, string]; children: React.ReactNode }) {
  return (
    <div className="overflow-hidden rounded-[10px] border border-border-subtle bg-white">
      <div className="flex justify-between border-b border-border-subtle px-3.5 py-2.5 font-mono text-[11.5px] text-muted">
        <span>{cap[0]}</span>
        <span>{cap[1]}</span>
      </div>
      <pre className="overflow-x-auto p-[18px] font-mono text-[12.5px] leading-[1.95] text-foreground">
        {children}
      </pre>
    </div>
  );
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded border border-border-subtle bg-surface px-1.5 py-0.5 font-mono text-[13px] text-ink">
      {children}
    </code>
  );
}
