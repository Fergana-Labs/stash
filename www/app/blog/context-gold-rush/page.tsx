import type { Metadata } from "next";
import Link from "next/link";

import SiteFooter from "../../_components/SiteFooter";
import SiteHeader from "../../_components/SiteHeader";
import { POSTS, blogPostingJsonLd } from "../_lib/posts";

export const metadata: Metadata = {
  alternates: { canonical: "/blog/context-gold-rush" },
  title: "The context gold rush: why everyone is building the same thing · Stash",
  description:
    "Context graph, company brain, LLM wiki — a map of who is building the context layer, the patterns that have converged, and the pieces still missing before any of it reaches mass adoption.",
};

const X_POST = "https://x.com/samzliu/status/2080210797465379147";

export default function ContextGoldRushPage() {
  const post = POSTS["context-gold-rush"];

  return (
    <main className="min-h-screen bg-background text-foreground">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(blogPostingJsonLd(post)) }}
      />
      <SiteHeader current="Blog" />

      <article className="mx-auto max-w-[720px] px-7 pb-24 pt-16">
        <h1 className="text-balance font-display text-[clamp(32px,4.4vw,52px)] font-medium leading-[1.06] tracking-[-0.03em] text-ink">
          The context gold rush: why everyone is building the same thing
        </h1>
        <p className="mt-5 text-[14px] text-muted">
          By {post.author.name} ·{" "}
          <time dateTime={post.datePublished}>{post.byline}</time>
        </p>
        <p className="mt-2 text-[14px] text-muted">
          Originally published on <Lnk href={X_POST}>X</Lnk>.
        </p>

        <div className="prose prose-lg mt-10">
          <p>
            You either die building product or live long enough to do context management.
            Whether you call it a context graph, company brain, or LLM wiki, it seems that many
            start-ups and larger companies alike are building the same thing: a place to store
            data and context for tomorrow&rsquo;s agentic workforce. This is one of the four
            main ideas apparently left in AI: research lab, RL environment, infrastructure, or
            context management.
          </p>
          <p>
            From an ecosystem perspective, a context management product checks all the boxes for
            a high growth start-up or internal innovation team:
          </p>
          <ul>
            <li>
              <strong>Jevon&rsquo;s paradox (timing).</strong> Lowering the cost — time,
              friction, labour — of producing code and writing will cause an explosion of
              text-based data that our current tools (Slack, Notion, GitHub) are not designed to
              handle. We are still on the early part of that curve as agent adoption penetrates
              the wider economy.
            </li>
            <li>
              <strong>Self-improvement (vision).</strong> There&rsquo;s an enticing vision of an
              autonomous self-improving system where agents become better and better over time
              without human intervention. Capturing and managing context is a big part of what we
              believe will enable that capability. It is also a narrative that is sellable to
              executives: develop your own context layer now, or your competitors will and you
              will never catch up.
            </li>
            <li>
              <strong>Data sovereignty (tailwinds).</strong> Companies and governments are
              becoming increasingly worried about the frontier labs training on their internal
              data. An external, trusted party to store and manage that data will become
              increasingly important.
            </li>
            <li>
              <strong>Context moat (business model).</strong> The previous generation of SaaS was
              built on moats and monopoly power, much of it driven by high switching costs: once
              you are embedded in a company, it is extremely hard for them to switch off.
              Managing a company&rsquo;s context has all the same properties. For some business
              models — Harvey, for instance — you can develop a context moat by servicing
              customers. This is Nadella&rsquo;s reverse information paradox.
            </li>
            <li>
              <strong>Model capability saturation (tech edge and competition).</strong>{" "}
              There&rsquo;s a growing belief that models can do anything we want as long as they
              have the right context. As frontier models have started to discover new math, there
              is a sense that we have saturated the intelligence needed for most tasks. The
              bottleneck, then, is context. That makes it one of the few big areas of opportunity
              left that will not be commoditized by better models, and it sits largely outside
              the labs&rsquo; main strike zone.
            </li>
          </ul>

          <h2>All roads lead to Rome</h2>
          <p>
            It&rsquo;s clear that something like a company brain is needed. What&rsquo;s striking
            is how similar the products can seem, even when they started from vastly different
            places. Part of this is agents collapsing product into a singularity: a coding agent
            is fundamentally not that different from a marketing agent or an email agent. And so
            it goes across the stack. Another big part is that the space is still early, with
            lots of players trying to lay claim to a fuzzy field.
          </p>

          <img
            src="/blog/context-landscape.webp"
            width={1200}
            height={676}
            loading="lazy"
            alt="A collage of marketing headlines from context and memory companies: company brain, context layer, agent memory, context engine - nearly interchangeable claims across a dozen different products"
            className="mx-auto w-full rounded-xl border border-border-subtle"
          />
          <p className="text-[14px] italic text-muted">A dozen companies, one claim. The marketing copy converged faster than the products did.</p>
          <ul>
            <li>
              <strong>Personal knowledge base.</strong> A GitHub repo, gbrain, Claude Code plus
              Obsidian. A folder of markdown files that serves as skills and memory for your
              agents. Where people start when experimenting. They fail when trying to expand to
              an entire team.
            </li>
            <li>
              <strong>Agent memory.</strong> Letta, Honcho, Engram Lab. Per-agent memory layers
              that scale vertically in time. These companies tend to be research focused on
              building super long-horizon agents, split between those who believe in token space
              and those who believe in weight space.
            </li>
            <li>
              <strong>Observability tools.</strong> Braintrust, Raindrop. They capture the traces
              your external, production agents emit. The outputs tend to be dashboards and evals
              rather than an accumulating data store for future agents. Not directly playing
              here, but a natural place where the data accumulates.
            </li>
            <li>
              <strong>Agent dev tools.</strong> Entire, Mintlify. A similar service to
              observability tools, except for your internal coding agents. The output is a set of
              docs so that your coding agents produce less slop and run for longer.
            </li>
            <li>
              <strong>Data moat builders.</strong> Applied Compute, Prime Intellect. They sell
              enterprises on a vision of custom models and a context layer hyper-specific to
              their workflows. Part research lab, part AI context consulting firm, part GPU
              provider: own the customer relationship end to end and be a one-stop shop.
            </li>
            <li>
              <strong>Companies reinventing themselves.</strong> Notion, ClickUp, Airbyte, Glean,
              PromptQL. Established in related areas, and now joining the context gold rush.
            </li>
            <li>
              <strong>AI employee.</strong> Viktor, Lindy. Starting at the level of individual
              users, on the premise that they are well positioned to capture context and build a
              PLG motion that maps context across entire orgs.
            </li>
            <li>
              <strong>Vertical AI-native service companies.</strong> Too many to count. By
              building custom end-to-end workflows, they too build up an accumulating context
              layer, solving their customers&rsquo; pain points better than any horizontal
              player.
            </li>
            <li>
              <strong>Company brain.</strong> Stash (full disclosure — this is us), Sentra,
              Hyperspell, Supermemory. All relatively early start-ups, started to natively solve
              the org-level context layer problem. The bet is that attacking this problem from
              day one, rather than moving into it laterally, is how the category gets won.
            </li>
          </ul>
          <p>
            And this doesn&rsquo;t count the frontier labs doing similar work across their FDE
            and product teams, or related players like Hydra and Pinecone expanding vertically up
            from infrastructure, Exa moving from web search to enterprise search, agent
            orchestration companies building memory into their products, or integration companies
            like Composio that connect to existing context and sources of truth. All of them
            could move laterally into context management if the opportunity appears. An open
            question: as models get smarter, are integrations all you need?
          </p>
          <p>
            There is likely space for many of these companies to thrive. Despite the similar
            marketing copy, they are probably not competitors — they go after different customers
            with different use cases at different parts of the stack.
          </p>

          <h2>What has converged</h2>
          <p>A few patterns show up almost everywhere:</p>
          <ul>
            <li>
              <strong>Markdown files and a filesystem.</strong> Agents are post-trained on them,
              so they need no translation layer.
            </li>
            <li>
              <strong>Hybrid retrieval.</strong> Semantic search combined with keyword search for
              the best results.
            </li>
            <li>
              <strong>Dreaming and sleep-time compute.</strong> Separate the agent doing the work
              — a Claude Code session, a workflow agent — from the agent acting as custodian over
              the knowledge base. The sleep-time agent indexes, de-dups, and updates.
            </li>
            <li>
              <strong>External connections.</strong> Pull from as many external sources as
              possible: Granola, email, calendar, Slack, CRM. Treat these as raw data sources
              that your sleep-time agents read but do not edit over, and inherit the sharing
              scopes of those connections so isolation and permissioning stay simple.
            </li>
          </ul>
          <p>
            An important note: the current implementation of these patterns will go out of date
            as the industry evolves. We hosted a company brain and memory event a few weeks ago
            and found that most people believe the current paradigms will not stick around.
          </p>

          <h2>What&rsquo;s missing</h2>
          <p>
            We are still very early, and several key components of mass adoption are missing.
          </p>
          <ul>
            <li>
              <strong>Combining structured and unstructured data.</strong> A clean ontology
              between all the different data types. Should data be structured as database tables
              or as a filesystem? How do you deal with unstructured data such as Slack channels?
              What happens when some of the memory is stored in weights rather than pure text?
              Each type has different permission models, shapes, and update cadences. Humans
              blend these seamlessly; agents need more guidance.
            </li>
            <li>
              <strong>Data ingestion everywhere.</strong> Company brains only become useful past a
              tipping point of information inside them. Otherwise it is more efficient to go to
              each source directly. That requires ingesting every format from PDFs to database
              tables, which makes sales cycles long through security reviews and heavy
              integration work.
            </li>
            <li>
              <strong>Data access and controls.</strong> Making sure the right people access the
              right information and the wrong people cannot. Each architecture has its own
              trade-offs. Do you provision each agent a user? What is shared between teams versus
              private? Can you build guard rails that actually prevent leakage?
            </li>
            <li>
              <strong>Good evals.</strong> Does a company brain actually make your team more
              productive, or is it a productivity nerd&rsquo;s dream? What makes one
              implementation measurably better than another? Memory is inherently a long-horizon
              problem, so rollouts on evals get expensive and hard to run.
            </li>
            <li>
              <strong>Stability over long timeframes.</strong> Put another way, we need to solve
              continual learning. We need to trust that adding another skill or data source will
              not dilute the performance of the existing ones, and that knowledge bases will not
              slopify over time. Context rot is still a very real problem.
            </li>
            <li>
              <strong>Blast radius.</strong> Our internal name for how retrieved information is
              bounded by scope: time, context, prioritization. It is becoming clear that pure
              retrieval is not sufficient for good memory, and we will need better ways to instil
              common sense about which pieces of information matter more.
            </li>
          </ul>

          <h2>The killer use case</h2>
          <p>
            This is the big one. For all the hype around context graphs and company brains, the
            clear business case and ROI are still being developed. The metrics have not caught up
            to the technology and the vision. A few emerging hypotheses are working okay so far:
          </p>
          <ul>
            <li>
              <strong>Retrieve information.</strong> The original Glean use case: find information
              across scattered datasets and sources of truth.
            </li>
            <li>
              <strong>Automate workflows.</strong> Have agents do the repetitive, boring tasks —
              and more of them as time goes on.
            </li>
            <li>
              <strong>Cost and latency savings.</strong> Memory and context layers have been shown
              to decrease token costs substantially.
            </li>
            <li>
              <strong>Better agent performance.</strong> Have your agents complete tasks they
              could not have completed otherwise.
            </li>
          </ul>
          <p>
            These are the questions we spend our time on. If you are building or thinking about
            your own brain, we would love to chat — see{" "}
            <Link href="/internal-agents">internal agents</Link> for the agents your team runs,{" "}
            <Link href="/external-agents">external agents</Link> for the ones your customers use,
            or <Link href="/contact-sales">book a call</Link>.
          </p>
        </div>
      </article>

      <SiteFooter />
    </main>
  );
}

function Lnk({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-brand underline underline-offset-4 transition hover:text-ink"
    >
      {children}
    </a>
  );
}
