import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Three Dimensions That Matter To An Agent Memory Store · Stash",
  description:
    "An opinionated take on three key decisions memory builders need to make: retrieval, injection policy, and what to store.",
};

export default function ThreeDimensionsPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <Header />

      <article className="mx-auto max-w-[720px] px-7 pb-24 pt-16">
        <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
          <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
          Blog
        </p>
        <h1 className="mt-5 text-balance font-display text-[clamp(32px,4.4vw,52px)] font-black leading-[1.04] tracking-[-0.035em] text-ink">
          Three Dimensions That Matter To An Agent Memory Store
        </h1>
        <p className="mt-5 text-[14px] text-muted">By Henry Dowling</p>

        <div className="prose prose-lg mt-10">
          <p>
            There are a lot of different approaches to building memory for coding
            agents (see <Lnk>here</Lnk>, <Lnk>here</Lnk>, <Lnk>here</Lnk>,{" "}
            <Lnk>here</Lnk>, <Lnk>here</Lnk>, <Lnk>here</Lnk>, <Lnk>here</Lnk>,{" "}
            <Lnk>here</Lnk>, <Lnk>here</Lnk>, <Lnk>here</Lnk>, <Lnk>here</Lnk>,{" "}
            <Lnk>here</Lnk>, <Lnk>here</Lnk>, <Lnk>here</Lnk>, <Lnk>here</Lnk>,{" "}
            <Lnk>here</Lnk>, <Lnk>here</Lnk>, <Lnk>here</Lnk>, <Lnk>here</Lnk>,{" "}
            <Lnk>here</Lnk>, <Lnk>here</Lnk>, <Lnk>here</Lnk>, <Lnk>here</Lnk>,
            and <Lnk>here</Lnk> for some example implementations.)
          </p>
          <p>
            In this article, I&rsquo;m going to give my opinionated stance on how
            you should approach this problem, examining three key decisions that
            memory builders need to make. This article is kinda a grab bag.
          </p>

          <h2>TLDR</h2>
          <p>
            Use semantic retrieval and grep to retrieve memories over some form of
            structured knowledge base, and do not use knowledge graphs. Generally,
            the agent should request memories rather than force-feeding them. You
            should store organization-specific knowledge in your memory store&mdash;not
            personal preferences and not information generally available on the
            internet.
          </p>

          <h2>Dimension 1: Retrieval</h2>
          <p>
            How do we structure the data so that it&rsquo;s easy to retrieve? Here
            are the most common approaches:
          </p>
          <ul>
            <li>
              <strong>Semantic retrieval</strong> (specifically, vector
              embeddings) is the most common naive approach that people use to
              build agent memory. Here&rsquo;s a <Lnk>thread</Lnk> talking about
              common patterns. It&rsquo;s great and you should incorporate it.
            </li>
            <li>
              <strong>Grep over filesystem</strong> is also much-talked-about
              (here&rsquo;s an <Lnk>example</Lnk>, here&rsquo;s the supermemory
              founder <Lnk>talking about it</Lnk>, here&rsquo;s a vercel{" "}
              <Lnk>blog</Lnk> about this). It&rsquo;s great and you should
              incorporate it. This feels spiritually the most
              &ldquo;bitter-lesson-pilled&rdquo; (hence the refrain
              &ldquo;filesystem + grep is all you need&rdquo;).
            </li>
            <li>
              <strong>Knowledge graphs</strong> are a popular and enticing
              approach. Mem0&rsquo;s entity linking is an example of this
              approach. Shortly I will argue that you should not incorporate a
              knowledge graph into your memory system.
            </li>
            <li>
              <strong>LLM Wiki</strong> (<Lnk>source</Lnk>) is the idea of
              structuring your codebase/organization&rsquo;s memory as a
              collection of documents that an AI continually maintains / cleans
              up. It&rsquo;s very promising and you should use it. Here&rsquo;s a
              more formal academic <Lnk>paper</Lnk> advocating for this approach.
            </li>
            <li>
              <strong>Subagent summary</strong>&mdash;take a large piece of stored
              text and summarizing it with several smaller subagents in parallel.
              This <Lnk>paper</Lnk> on &ldquo;agentic mapreduce&rdquo; is an
              example.
            </li>
          </ul>

          <p>
            <strong>Q: Which ones should I use?</strong>
          </p>
          <p>A: All of the above except knowledge graphs.</p>
          <p>
            If you&rsquo;re building on the Claude Agent SDK your agent will have
            grep and subagent summary out of the box.
          </p>
          <p>
            Here&rsquo;s a summary of why it&rsquo;s necessary to include each of
            the above four components:
          </p>
          <ul>
            <li>
              <strong>Grep over filesystem</strong> is the gold standard for agent
              memory. It plays to what agents are already posttrained to be great
              at&mdash;writing bash commands, understanding filesystems, and
              iteratively using tools. E.g. &ldquo;why did we decide to bump the
              rate limit on our API gateway&rdquo; &rarr;{" "}
              <code>grep -n &quot;rate&quot; src/scheduler/gateway/server.py | head -20</code>
            </li>
            <li>
              <strong>Semantic retrieval</strong> is helpful to agents looking for
              answers to semantic questions that aren&rsquo;t easy to grep for.
              E.g. &ldquo;where do we constrain our users&rsquo; ability to
              configure their pipeline?&rdquo;
            </li>
            <li>
              <strong>Curated LLM Wiki</strong> &rarr; Essentially indexes your
              filesystem to make grepping easier. E.g. you don&rsquo;t want to
              have many redundant entries for &ldquo;caching strategy&rdquo; in
              your filesystem. Additionally allows the memory to evolve based on
              your organization&rsquo;s needs over time.
            </li>
            <li>
              <strong>Agentic Mapreduce</strong> &rarr; Useful for
              &ldquo;summary&rdquo; queries. E.g. what are the most common ways our
              past 1000 customers have churned?
            </li>
          </ul>

          <p>
            <strong>Q: Why shouldn&rsquo;t I use a knowledge graph?</strong>
          </p>
          <p>
            First, I&rsquo;ll claim that you shouldn&rsquo;t use a knowledge graph
            as your <em>primary</em> way of representing memory.
          </p>
          <p className="text-[14px] italic text-muted">
            Any similarity to actual persons living or dead is purely coincidental
          </p>
          <p>
            Most knowledge graph implementations store facts, and memory != facts.
            Here&rsquo;s an illustrative example: Suppose my friend Joy texted me
            &ldquo;I broke up with Dylan&hellip;&rdquo;
          </p>
          <p>
            The way a knowledge graph would update in response to this information
            is to...
          </p>
          <ul>
            <li>
              Change the edge between Joy and Dylan from &ldquo;couple&rdquo; to
              &ldquo;exes&rdquo;
            </li>
            <li>
              Maybe write to the &ldquo;Joy&rdquo; / &ldquo;Dylan&rdquo; nodes
              something to the effect of &ldquo;recently had a breakup&rdquo;
            </li>
          </ul>
          <p>
            But there&rsquo;s so much semantic information in that text that
            wasn&rsquo;t captured! The &ldquo;...&rdquo; indicates that
            there&rsquo;s probably some spicy tea. The fact that the text was
            short, and came out of the blue indicates that maybe she had been
            expecting it or knows that I had been expecting it. Sam Whitmore makes
            this point very convincingly in her <Lnk>talk</Lnk> on memory last
            year (at the 2:05 mark)
          </p>
          <p>
            Second, I&rsquo;ll claim that even in addition to another way of
            representing memory (e.g. a document store), a knowledge graph is still
            not worth using in your product. Here&rsquo;s some empirical evidence:
            Mem0 tried graph memory and was only able to squeeze out a{" "}
            <Lnk>2% performance gain</Lnk> on benchmarks. This <Lnk>paper</Lnk>{" "}
            tried it and found that while token costs go down, so does performance.
            Similarly, in this <Lnk>paper</Lnk>, some researchers found that
            between a simple retrieval-based memory, and a simple retrieval-based
            memory augmented with a graph, the retrieval-based memory actually
            performed worse.
          </p>

          <h2>Dimension 2: Memory Injection Policy</h2>
          <p>
            Should the agent ask for things to be added to its memory, or should
            things be added to the agent&rsquo;s memory proactively?
          </p>
          <ul>
            <li>
              <strong>Pull</strong> the agent asks for memory based on a query (via
              semantic search, asking a subagent to summarize, etc), and then
              receives a result. Eg <Lnk>Letta</Lnk>
            </li>
            <li>
              <strong>Push</strong> relevant memories are proactively added to the
              agent&rsquo;s context without any explicit request on the part of
              the agent. Eg most 2023-era RAG systems
            </li>
          </ul>
          <p className="text-[14px] italic text-muted">
            In Letta&rsquo;s original MemGPT paper, the LLM decides when to pull
            memory into its context.
          </p>
          <p>
            <strong>
              Q: We should never push to memory, because pushing irrelevant stuff
              into memory will cause context rot, right?
            </strong>
          </p>
          <p>
            A: I don&rsquo;t think these are quite the same thing! LLMs are able to
            do great things under long context windows&mdash;consider that{" "}
            <em>coding agents</em> routinely hit 1M context and they are the main
            workhorse for AI productivity.
          </p>
          <p>
            So really, the problem is that if you add <em>irrelevant</em> context,
            LLM performance decreases. But the success of coding agents suggests to
            us that it&rsquo;s totally possible to do great work with relevant
            context, if you&rsquo;re smart.
          </p>
          <p>
            <strong>
              Q: Okay, that&rsquo;s a neat fun fact, but why would I ever want to
              push? That&rsquo;s not very bitter-lesson-pilled! Just let the agent
              decide.
            </strong>
          </p>
          <p>
            Yes, generally it&rsquo;s better to let the coding agent manage its own
            resources! But you really do have to push sometimes. Here&rsquo;s an
            example of a time where you&rsquo;d want to push memory:
          </p>
          <ul>
            <li>
              The user has previously mentioned that <code>curl</code> isn&rsquo;t
              working on their local network, and they need to use{" "}
              <code>wget</code> instead
            </li>
            <li>
              The agent tries to use <code>curl</code>.
            </li>
          </ul>
          <p>
            No reasonable agent would think to check whether there have been
            historical problems with <code>curl</code> before using it. But also,
            clearly a desideratum of any reasonable memory system would be that the
            agent is able to remember this fact. So, this fact needs to be pushed
            to the agent. This example comes from a friend of mine, who presents an
            extremely interesting version of the &ldquo;push&rdquo; approach{" "}
            <Lnk>here</Lnk>.
          </p>
          <p>
            Also, I would push back on &ldquo;push&rdquo; being inherently not
            bitter-lesson-pilled. What if we RL&rsquo;d a memory injector in tandem
            with an agent on a task? That would be very bitter-lesson-pilled.
          </p>
          <p>
            A few additional thoughts on push versus pull: (1) if you are pushing
            memory, you should probably push as a user message rather than as part
            of the system prompt, so as to save money on prompt caching (2) instead
            of pushing a full &ldquo;memory&rdquo; to an agent&rsquo;s context
            window, it may be a better idea to push a lightweight &ldquo;title&rdquo;
            of the memory, and to allow the agent to decide whether or not to
            double click into any of the memories based on their title&mdash;analogous
            to how skills work.
          </p>

          <h2>
            Dimension 3: What to store: Transcripts vs commentary on transcripts vs
            LLM wiki
          </h2>
          <p>
            A good general policy is: &ldquo;Store everything that you would
            consider <code>company knowledge</code>&rdquo;.
          </p>
          <p>
            Here are some things that many people like to put in their memory
            store:
          </p>
          <ul>
            <li>Context from various knowledge resources (eg Slack, Granola)</li>
            <li>Their codebase</li>
            <li>
              Things that the agent decides to write to memory (eg a persistent
              &ldquo;notebook&rdquo;)
            </li>
            <li>Past conversation transcripts</li>
          </ul>
          <p>
            Here are some other, less talked about things that you might consider
            adding to memory:
          </p>
          <p>
            <strong>
              Q: Should you include your collaborator&rsquo;s conversation
              transcripts
            </strong>
          </p>
          <p>
            A: Yes, if they&rsquo;ll let you! Here&rsquo;s a <Lnk>post</Lnk> that
            explains the benefits of this in greater detail&mdash;tldr you can make
            your agents 48% more efficient on a team of 2 by sharing transcripts in
            memory.
          </p>
          <p>
            <strong>
              Q: Should you include facts about the world in your agent&rsquo;s
              memory store? Eg: should there be an entry for &ldquo;potato&rdquo;?
              Seems like that would be a useful thing to remember, but also
              it&rsquo;s already in the weights of any llm.
            </strong>
          </p>
          <p>
            A: Sometimes! Here&rsquo;s an analogy that might be helpful: imagine
            that wikipedia is what&rsquo;s outside of your agent&rsquo;s memory,
            and your company has an internal wiki. If your organization has a
            specific insight on ACME corp (eg &ldquo;they&rsquo;re our number one
            competitor&rdquo;) that wouldn&rsquo;t be ACME corp&rsquo;s wikipedia
            page, then you should &ldquo;fork&rdquo; wikipedia and create your own
            page for ACME corp, which is stored in agent memory.
          </p>
          <p>
            <strong>
              Q: Should you include secrets in your agent&rsquo;s memory store? Eg:
              Cursor API key
            </strong>
          </p>
          <p>
            A: Nope. Authenticating your agent is a separate task from your agent
            remembering things. A better model is to keep secrets in a separate
            server that stores authentication info for the agent (here&rsquo;s a
            nice <Lnk>article</Lnk> on a common design pattern)
          </p>
          <p>
            <strong>
              Q: Should you include user preferences in your agent&rsquo;s memory
              store? Eg: &ldquo;Please return all your responses in spanish&rdquo;
            </strong>
          </p>
          <p>
            A: Nope. That should go in a user-scoped file like{" "}
            <code>~/.claude/CLAUDE.md</code> or <code>CLAUDE.local.md</code>. The
            reasoning here is that we expect agent memory to become multiplayer
            soon, and agent memory should encode org-level preferences (eg:
            &ldquo;we always make reports &lt;2k words&rdquo;) rather than
            user-level preferences.
          </p>

          <hr />
          <p className="text-[14px] text-muted">
            Thanks to Sam Liu and Bryan Houlton for comments on this article!
          </p>
        </div>

        <div className="mt-12">
          <Link
            href="/blog"
            className="text-[14px] font-medium text-brand underline underline-offset-4 transition hover:text-ink"
          >
            &larr; Back to blog
          </Link>
        </div>
      </article>
    </main>
  );
}

function Lnk({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-medium text-brand underline underline-offset-4">
      {children}
    </span>
  );
}

function Header() {
  return (
    <header className="sticky top-0 z-30 border-b border-border-subtle bg-background/85 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-7">
        <Link
          href="/"
          className="font-display text-[20px] font-black tracking-[-0.03em] text-ink"
        >
          stash
        </Link>
        <nav className="flex items-center gap-5 text-[14px] text-dim">
          <Link href="/discover" className="transition hover:text-ink">
            Discover
          </Link>
          <Link href="/docs" className="transition hover:text-ink">
            Docs
          </Link>
          <Link href="/blog" className="text-ink">
            Blog
          </Link>
          <Link href="/contact-sales" className="transition hover:text-ink">
            Contact sales
          </Link>
          <Link
            href="/login"
            className="hidden h-10 items-center rounded-lg border border-border bg-background px-[18px] text-[14px] font-medium text-ink transition hover:border-ink sm:inline-flex"
          >
            Sign in
          </Link>
        </nav>
      </div>
    </header>
  );
}
