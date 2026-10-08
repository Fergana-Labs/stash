import type { Metadata } from "next";

import SiteFooter from "../../_components/SiteFooter";
import SiteHeader from "../../_components/SiteHeader";
import { POSTS, blogPostingJsonLd } from "../_lib/posts";

export const metadata: Metadata = {
  alternates: { canonical: "/blog/agent-traces-are-the-new-oil" },
  title: "Agent traces are the new oil · Stash",
  description:
    "Agent traces are the currency AI companies transact over, yet most enterprises deploying agents treat them as disposable logs. Why traces matter, why extracting value from them is hard, and why they are the new oil.",
};

const X_POST = "https://x.com/samzliu/status/2103613396625367437";

export default function AgentTracesAreTheNewOilPage() {
  const post = POSTS["agent-traces-are-the-new-oil"];

  return (
    <main className="min-h-screen bg-background text-foreground">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(blogPostingJsonLd(post)) }}
      />
      <SiteHeader current="Blog" />

      <article className="mx-auto max-w-[720px] px-7 pb-24 pt-16">
        <h1 className="text-balance font-display text-[clamp(32px,4.4vw,52px)] font-medium leading-[1.06] tracking-[-0.03em] text-ink">
          Agent traces are the new oil
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
            Agent traces are quickly becoming the new currency that AI companies across the stack
            use to transact over. Allegations of Chinese open source distillation attacks are an
            instance of the immense value that traces hold: acquire them at any cost, beg, borrow,
            or steal be damned. However, most companies today aren&rsquo;t properly leveraging
            this critical asset.
          </p>
          <p>
            In the ChatGPT era, agent conversation transcripts only involved back-and-forth
            messages between the LLM and the user. Then with the rise of agents, we added tool
            calls and reasoning to the mix. The record of user messages, agent internal
            reasoning, tool calls, and agent responses is an agent trace. These are critically
            different from their predecessors, conversation transcripts. As long-horizon agents
            come into play, more and more of the trace is dominated by the agent&rsquo;s actions
            rather than user messages. We have seen a huge growth in attention on agent traces due
            to three compounding factors that have taken shape over the last year:
          </p>
          <ul>
            <li>
              RL means that current training is largely done over on-policy rollouts (i.e.
              traces) instead of pre-training data.
            </li>
            <li>
              Long-horizon agents with more tokens and actions per run mean traces have become
              more valuable.
            </li>
            <li>Agents are being deployed more broadly across organizations.</li>
          </ul>

          <img
            src="/blog/openrouter-agent-tokens.webp"
            width={1552}
            height={448}
            loading="lazy"
            alt="Line chart of weekly agent token volume on OpenRouter, rising from 0.4T tokens in December 2024 to over 30T by June 2026, with the steepest growth after December 2025."
            className="mx-auto w-full rounded-xl border border-border-subtle"
          />
          <img
            src="/blog/metr-task-length.webp"
            width={2324}
            height={1060}
            loading="lazy"
            alt="METR chart of the length of software tasks different LLMs can complete 50% of the time, growing exponentially from seconds for GPT-2 to many hours for Claude Opus 4.6 and Claude Mythos Preview."
            className="mx-auto w-full rounded-xl border border-border-subtle"
          />

          <h2>The under-appreciated asset</h2>
          <p>
            The right traces in sufficient quantities make up the backbone of most AI companies
            today. They contain the plethora of information needed to move AI forward: reasoning,
            tool calls, retrieved information, errors, outputs, and human feedback. For companies
            that are building AI, these traces fuel the arms race of ever-improving models and
            agents.
          </p>
          <ul>
            <li>
              <strong>For data vendors:</strong> the right traces annotated by human experts or
              generated against RL environments can make you a small fortune if you sell them to
              frontier labs.
            </li>
            <li>
              <strong>For frontier labs:</strong> a competitor&rsquo;s traces can help your model
              catch up, while properly annotated ones in the right domains push your model to new
              frontiers.
            </li>
            <li>
              <strong>For the application layer:</strong> the traces from production systems can
              help identify bugs or user experience issues, while the traces produced by eval
              systems help you hill-climb against north star metrics.
            </li>
          </ul>
          <p>
            For users and enterprises deploying agents, however, traces are largely ignored and
            under-appreciated. They are seen as logs, to be filed away for monitoring and
            compliance if they are stored at all. (Here&rsquo;s a quick reminder that Claude Code
            automatically deletes your sessions after 30 days unless you set it otherwise!)
            However, as agents do more and more work within enterprises, these traces are no
            longer disposable logs. They become the operational work of the company itself.
          </p>

          <h2>What does a trace mean to you?</h2>
          <p>
            If you&rsquo;re deploying agents, there are three main ways in which traces remain
            useful beyond the original task the agent is assigned:
          </p>

          <h3>Operational excellence</h3>
          <ul>
            <li>Understand token spend and latency.</li>
            <li>Measure ROI of workflows.</li>
            <li>Diagnose why an agent failed.</li>
            <li>
              Discover uses that customers invented but the product team did not anticipate.
            </li>
          </ul>

          <h3>Safety guardrails</h3>
          <ul>
            <li>
              The{" "}
              <Lnk href="https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/">
                Hugging Face incident
              </Lnk>{" "}
              is a warning signal for what can happen without robust guardrails.
            </li>
            <li>
              As multi-agent systems scale, we will need better ways to keep tabs on the sheer
              volume of data. OpenAI reportedly used 10k agents running in parallel on their
              solution to the{" "}
              <Lnk href="https://openai.com/index/navier-stokes-solution/">
                Navier-Stokes problem
              </Lnk>
              .
            </li>
            <li>
              As agents are given more power (calling APIs, interacting with customers directly,
              spending money, etc.), it&rsquo;s important to limit downside exposure.
            </li>
          </ul>

          <h3>Continuous improvement</h3>
          <ul>
            <li>
              Successful traces contain reusable playbooks and procedures that should spread
              across a team or organization. Even failed traces contain human feedback, correct
              work, and other learnings that can be put to use.
            </li>
            <li>
              Today, improving agents and models from traces is relegated to companies at the
              cutting edge that can afford a post-training team.
            </li>
            <li>
              Tomorrow, it will be important for every company to own their own intelligence to
              avoid vendor lock-in and maintain their competitive positioning against other
              companies with the same base models.
            </li>
          </ul>

          <h2>Why extracting value from traces is hard</h2>
          <p>
            The relatively simple nature of traces is deceptive. They seem like just a log of
            what your agent has done, but actually making use of them effectively in production
            proves challenging:
          </p>
          <ul>
            <li>
              <strong>The data is unstructured.</strong> There is usually a mix of prose, JSON
              schemas, tool calls, user messages, code, and even images. Making sense of how
              everything is connected is a non-trivial task.
            </li>
            <li>
              <strong>There is a huge volume of data.</strong> Agents can produce tokens much
              faster than humans can, and ingesting all of those tokens with yet another LLM is
              prohibitively expensive, usually representing a meaningful fraction of the cost it
              took to produce those tokens in the first place. Classification-focused models like
              Jev may change the equation here, however.
            </li>
            <li>
              <strong>The feedback is messy.</strong> Success and failure may be hard to determine
              from the trace alone. Users may not give any feedback at all, or give implicit
              feedback such as not continuing the session.
            </li>
            <li>
              <strong>Long-horizon credit assignment is hard.</strong> A task may have failed but
              contain mostly correct decisions except at the end, or have succeeded but with a lot
              of failed intermediary steps that shouldn&rsquo;t have been taken. It&rsquo;s
              unclear what decision in a long trace led to success or failure.
            </li>
            <li>
              <strong>The judgements are qualitative.</strong> Most insights we would want to pull
              from a trace are judgement calls which require more &ldquo;feel&rdquo; than typical
              verifiable signals can provide (e.g. is this safe to run? is this what the user
              intended?).
            </li>
            <li>
              <strong>Interpretability could get worse.</strong> Neuralese, recurrent
              transformers, and closed-source models refusing to provide reasoning traces all
              point to an emerging world where the reasoning of the models that power agents
              becomes more opaque over time.
            </li>
          </ul>

          <h2>The new oil</h2>
          <p>
            There&rsquo;s an analogy that&rsquo;s especially pertinent here.{" "}
            <Lnk href="https://www.forbes.com/sites/perryrotella/2012/04/02/is-data-the-new-oil/">
              In the 2010s
            </Lnk>
            , companies were scrambling to build cloud infrastructure, data lakes, and
            ontologies. The hope was that amassing this wealth of data in one place would enable
            the organization to more effectively leverage it to optimize operations, drive
            customer value, dissolve silos, and support advanced analytics.
          </p>
          <p>
            Today, we are seeing a new trend around agent traces and{" "}
            <Lnk href="https://foundationcapital.com/ideas/context-graphs-ais-trillion-dollar-opportunity">
              context graphs
            </Lnk>{" "}
            that rhymes with the past. Companies increasingly want to own their own intelligence
            and avoid{" "}
            <Lnk href="https://www.linkedin.com/posts/satyanadella_the-reverse-information-paradox-activity-7482090659898630144-J4sB">
              the reverse information paradox
            </Lnk>
            . In a world where agents automate most of a business and everyone has access to the
            same models, your competitive advantage is only as good as your ability to build your
            own proprietary layer of intelligence that improves over time from experience.
          </p>
          <p>
            This is similar to the institutional knowledge that lives in employees&rsquo; minds,
            except the minds of tomorrow are electronic. The medium for that knowledge is the
            agent traces. They will contain the history of a company&rsquo;s operations, what good
            looks like, and how it makes decisions, becoming a new strategic layer for
            businesses. And like big data and oil that came before, it only gains value through
            extraction, refinement, and distribution.
          </p>
          <p>
            If you are thinking through how to make use of agent traces, please{" "}
            <Lnk href="https://x.com/samzliu">reach out</Lnk>!
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
