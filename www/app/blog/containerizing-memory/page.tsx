import type { Metadata } from "next";
import Link from "next/link";

import SiteFooter from "../../_components/SiteFooter";
import SiteHeader from "../../_components/SiteHeader";
import { POSTS, blogPostingJsonLd } from "../_lib/posts";

export const metadata: Metadata = {
  alternates: { canonical: "/blog/containerizing-memory" },
  title:
    "Containerizing memory: the real barrier to continual learning and enterprise AI adoption · Stash",
  description:
    "The shipping container standardized freight and the world's economy followed. Agent memory has no such standard yet, and that missing consistency is why enterprise agent adoption has been mixed.",
};

const X_POST = "https://x.com/samzliu/status/2075437170198991344";

export default function ContainerizingMemoryPage() {
  const post = POSTS["containerizing-memory"];

  return (
    <main className="min-h-screen bg-background text-foreground">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(blogPostingJsonLd(post)) }}
      />
      <SiteHeader current="Blog" />

      <article className="mx-auto max-w-[720px] px-7 pb-24 pt-16">
        <h1 className="text-balance font-display text-[clamp(32px,4.4vw,52px)] font-medium leading-[1.06] tracking-[-0.03em] text-ink">
          Containerizing memory: the real barrier to continual learning and enterprise AI
          adoption
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
            London. The year is 1500. Your mission, should you choose to accept it, is to abandon
            your life in the present to live as King or Queen. All that glory, wealth, and power.
            And yet you likely said no. This is a testament to the extraordinary difference in
            quality of life and material wealth between a commoner today and a king of yesteryear.
            There is no shortage of proposed catalysts. The steam engine. The scientific method.
            Plumbing. Controversially, capitalism.
          </p>
          <p>I submit another one for your consideration.</p>
          <p>
            Not just the shipping container, but the idea of consistency it represents. Before,
            cargo moved as a chaos of barrels, crates, and sacks. Each a different size and shape.
            Each hand-loaded by armies of dockworkers. Each port of call a week of wrestling the
            ship&rsquo;s hold into order. It was slow, expensive, and ripe for breakage or theft.
            After, the world&rsquo;s freight collapsed into an interchangeable steel box of
            agreed-upon dimensions: liftable by any crane, stackable on any ship, latchable to any
            truck. Shipping costs fell so low that they effectively stopped mattering.
          </p>

          <img
            src="/blog/shipping-container.webp"
            width={1192}
            height={894}
            loading="lazy"
            alt="A single blue shipping container standing in a yard, with stacks of more containers behind it"
            className="mx-auto w-full rounded-xl border border-border-subtle"
          />
          <p className="text-[14px] italic text-muted">One agreed-upon steel box. Liftable by any crane, stackable on any ship, latchable to any truck.</p>
          <p>
            And so it goes with the entire story of the industrial revolution and beyond. Flat
            planes and lathes gave us precision manufacturing, making the steam engine viable.
            Standardized screws made mass assembly of anything from furniture to firearms
            possible. In later years, ISO standards in everything from the dimensions of a credit
            card to the format of a date became the hidden foundation modern society is built on.
            The descendants of those precision flat planes make it possible to manufacture
            transistors so small that more than ten thousand fit across a human hair.
          </p>
          <p>
            The very aspects of modern society we often blame for stripping us of our humanity —
            the monotonous job on the assembly line, the identical product stamped out a million
            times, the cookie-cutter big box store — are also the very things that created our
            comfort today.
          </p>

          <h2>Why consistency is so important</h2>
          <p>
            The underlying reason consistency is so powerful is that it produces reliable and
            predictable outputs, which can then be safely built on top of. You cannot construct a
            building on a foundation that is constantly changing shape. Stacking complexity is
            only possible when the layer beneath is stable enough to be ignored. Standardization
            means you only have to focus on the specific problem you are solving, because you
            trust that the other problems are handled. Ironically, standardizing a process creates
            more freedom by enabling greater possibilities. Every complex system in the world,
            from financial markets to supply chains to the internet, is a stack of things that
            coordinated to be predictable enough that the next layer up could stop worrying.
            Without it we would be stuck with only what one person can solve alone, instead of
            having an entire civilization&rsquo;s efforts compound.
          </p>
          <p>
            There is an additional benefit: scalability. For manufacturing and shipping,
            standardization enabled huge economies of scale through rapid assembly lines and
            massive container ships. Standardization is how you get more output for less input,
            because fewer decisions have to be made. You decide once and it scales across
            everything. Otherwise decisions constantly have to be remade, with inconsistencies
            causing cascading changes.
          </p>

          <img
            src="/blog/shipping-containers-stacked.webp"
            width={780}
            height={312}
            loading="lazy"
            alt="A wall of stacked shipping containers in many colours, filling the frame"
            className="mx-auto w-full rounded-xl border border-border-subtle"
          />
          <p className="text-[14px] italic text-muted">Standardization is how you get more output for less input. You decide once, and it scales across everything.</p>
          <p>
            There is a crucial caveat: pure consistency is not the whole answer. Computers are the
            clear example. Code is perfectly consistent — it executes exactly as written, every
            single time. But not until LLMs and agents did we seriously believe computers could
            automate most office work. The answer to this tension can be found in hammer swings.
            In the 1920s Nikolai Bernstein studied expert blacksmiths and found that they are{" "}
            <em>less</em> consistent in their swings than mediocre blacksmiths.
          </p>
          <img
            src="/blog/bernstein-blacksmith.webp"
            width={768}
            height={307}
            loading="lazy"
            alt="Bernstein's motion study of a blacksmith: dotted traces showing the arc of the arm and hammer across repeated strikes, each path slightly different"
            className="mx-auto w-full rounded-xl border border-border-subtle"
          />
          <p className="text-[14px] italic text-muted">Bernstein&rsquo;s motion study. The expert&rsquo;s swings vary; the blades do not.</p>

          <p>
            The magic isn&rsquo;t consistency alone. It also involves feedback loops. This is one
            of the other pillars behind the remarkable precision of modern manufacturing: control
            systems that self-correct on target. This works for thermostats, for transistor
            manufacturing, and increasingly for reasoning tasks too. That tacit, correcting
            intelligence is exactly what a modern AI model does. Where normal code is rigid and
            unflinching, agents can adapt and self-heal when something goes wrong — which is
            likely why we see reliability increase with intelligence. They are better at getting
            back on track. This verification and self-correction loop is the core technique behind
            state-of-the-art methods on benchmarks like ARC-AGI. Note, though, that the outputs
            are still consistent. The expert blacksmith produces better blades because the blades
            themselves are more consistent, even if the swings are not.
          </p>

          <h2>How this applies to AI</h2>
          <p>
            In the age of agents, the input we spend is tokens, which are proxies for the scarce
            resources of capital, time, and energy. When an agent can call a well-defined API to
            access data, that is enormously cheaper than having it reason its way through a
            workaround each time. This hints at a core principle for working with agents: speak in
            their native language. Labs have spent hundreds of millions training agents to be good
            at manipulating a specific set of formats — HTML, markdown, JSON. Using anything else
            is an uphill battle, forcing the agent to use its improvisation skills rather than its
            memorization.
          </p>
          <p>
            Think of the agent as a 4x4 off-roader that can grind across snow, marshes, and rocks.
            Although it can go anywhere, it is still faster on a highway than in the mud. The
            intelligence of the model is the off-road capability. More of it means it can go
            further off the beaten path — but you still want to build the road.
          </p>
          <p>
            The failure mode is that we have been relying on the feedback cycle, the
            agent&rsquo;s intelligence, for far too long. As long as models kept improving, we
            felt we were headed in the right direction. But the rapid pace of model improvement
            hid the shaky foundation. This is the core reason agent adoption in enterprises has
            been mixed. For a small team, occasional downtime and instability is fine. For a large
            organization with millions of customers, it is unacceptable. Consistency and feedback
            have to work in tandem; one cannot live at the expense of the other. Without
            consistency there is no reliability, and without reliability there is nothing solid
            for the next layer to stand on. We are then all craftsmen making singular objects
            rather than building industrial-scale systems.
          </p>
          <p>
            There are early attempts to industrialize this. On the weight-space side, LoRA gave us
            small, snap-on modules to fine-tune models, remarkably sample- and cost-efficient for
            how much they improve performance on specific problems. But each adapter is welded to
            one base model, so every time a smarter model ships you relearn the adaptation from
            scratch. Ramp Labs&rsquo; PorTAL is an early attempt at solving this, porting a LoRA
            module onto an entirely new model by refitting only a thin per-base converter on a
            handful of examples. On the orchestration side, managed agents and hosted MCP servers
            are trying to turn the disposable, break-prone session into something durable and
            shared.
          </p>

          <h2>A vision for the future</h2>
          <p>
            We believe the future takes these lessons from the industrial revolution by focusing
            on modularity, made possible by consistent interfaces and feedback loops. Three
            pictures of what that could look like:
          </p>
          <h3>The Matrix: portable memory</h3>
          <p>
            &ldquo;I know kung fu.&rdquo; Memory will be modular, independent cartridges that can
            be loaded into an agent at will. When loaded, it gives the agent a set of memories
            representing capabilities — a specific writing style, company SOPs — or information,
            such as regulations on the maintenance of aircraft parts. This modularity also solves
            the data isolation and security problem agents face when deploying across orgs: we can
            selectively choose what information an agent has access to and remembers. Skills are an
            early example, but suffer from context pollution and token space limits. The Cartridges
            paper and PorTAL are steps in the right direction.
          </p>
          <h3>The docking port: self-healing connections</h3>
          <p>
            PorTAL has a second property that matters just as much as portability: the
            adapter&rsquo;s link to a new model is self-building. Today, agents&rsquo; connections
            to tools and data constantly break. Think about how spacecraft dock. A small probe
            makes contact first, establishing a fragile, low-throughput connection. Only once that
            holds does the mechanism latch and draw the two craft into a rigid, high-bandwidth
            seal that astronauts can pass through. Agents are built for exactly this manoeuvre.
            The probe is the model reading the docs and fumbling through a first API call. Over
            time the agent hardens that path by writing dedicated code highways to replace the
            improvised per-call reasoning, and repairs the pathway on its own when a schema drifts
            or an endpoint changes.
          </p>
          <h3>Build-A-Bear: modular agents</h3>
          <p>
            Take Anthropic&rsquo;s principle of separating the brain from the hands to its logical
            conclusion. Have universal interfaces between models, tools, execution environment,
            memory, and orchestration. Any agent could then be built through simple choices, the
            way you would at a Build-A-Bear workshop: select a brain, a heart, and a body.
          </p>
          <p>
            If any of this resonates, Stash is working to make this vision a reality. See{" "}
            <Link href="/internal-agents">internal agents</Link> for the agents your team runs,{" "}
            <Link href="/external-agents">external agents</Link> for the ones your customers use,
            or <Link href="/contact-sales">book a call</Link>.
          </p>

          <h2>References</h2>
          <ul>
            <li>
              Ben Geist / Ramp Labs, &ldquo;PorTAL: Portable Task Adapters for LLMs&rdquo; —{" "}
              <Lnk href="https://x.com/RampLabs/article/2072381992285647280">portable, base-agnostic task adapters</Lnk>
            </li>
            <li>
              Eyuboglu et al., &ldquo;Cartridges: Lightweight and General-Purpose Long Context
              Representations via Self-Study&rdquo; (HazyResearch) —{" "}
              <Lnk href="https://arxiv.org/abs/2506.06266">arXiv:2506.06266</Lnk>
            </li>
            <li>
              Anthropic, <Lnk href="https://www.anthropic.com/engineering/managed-agents">Managed Agents</Lnk> — a step
              toward durable, modular runtimes
            </li>
            <li>
              Bernstein&rsquo;s principle,{" "}
              <Lnk href="https://brettworks.com/2022/01/14/notes-on-practice-as-repetition-without-repetition/">
                repetition without repetition
              </Lnk>{" "}
              — the blacksmith&rsquo;s non-identical strokes
            </li>
            <li>
              Marc Levinson,{" "}
              <Lnk href="https://press.princeton.edu/books/paperback/9780691136400/the-box">The Box</Lnk> — the shipping
              container as an engine of standardization
            </li>
          </ul>
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
