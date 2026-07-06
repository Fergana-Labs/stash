import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Why hasn't there been any great consumer AI (still) · Stash",
  description:
    "When models stop getting smarter, context engineering becomes the battleground. A case for the inevitable AI memory infrastructure buildout.",
};

export default function WhyNoGreatConsumerAiPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <Header />

      <article className="mx-auto max-w-[720px] px-7 pb-24 pt-16">
        <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
          <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
          Blog
        </p>
        <h1 className="mt-5 text-balance font-display text-[clamp(32px,4.4vw,52px)] font-black leading-[1.04] tracking-[-0.035em] text-ink">
          Why hasn&rsquo;t there been any great consumer AI (still)
        </h1>
        <p className="mt-5 text-[14px] text-muted">By Henry Dowling · August 2025</p>

        <div className="prose prose-lg mt-10">
          <p className="text-[15px] italic text-dim">
            This is a blog post I wrote in August 2025 about why there haven&rsquo;t
            been any great consumer AI experiences yet. Almost a year later, this
            is still true, and the reasoning is the same!
          </p>

          <hr />

          <p>
            If you&rsquo;re trying to improve an AI response, there are really only
            two ways to do it: use a smarter model, or write a better prompt. So,
            what happens if LLMs stop getting smarter? We&rsquo;ll have to start
            focusing on the prompt a lot more.
          </p>
          <p>
            Most AI interactions today start with you explaining everything. We can
            basically break down any AI prompt into:
          </p>
          <blockquote>
            Prompt = Actual Question + Explaining Background Context{" "}
            <Fnref id="1" />
          </blockquote>
          <p>
            One obvious way to continue to improve the quality of AI interactions
            is to <em>automatically add</em> the background context, to save the
            user the trouble of typing it all out and including context that the
            user may forget or be too lazy to add.
          </p>
          <p>
            AI products downstream of OpenAI already know this&mdash;when everyone
            has the same intelligence, the battle is about who can do the best
            context engineering (ie adding the right background information to AI,
            either via writing prompts or automatically pasting in outside
            information).
          </p>

          <h2>Improving context quality would be a really good thing for consumer AI</h2>
          <p>
            Explaining the relevant context before an AI interaction can get
            annoying, especially if you&rsquo;ve already written it down somewhere
            else. This information usually isn&rsquo;t a secret. What model car you
            drive, the link to the repo you&rsquo;re working on, the names of your
            friends: all this info is easy to find from your search history, email,
            personal notes, etc.
          </p>
          <p>
            AI interactions would be so much easier if every prompt you wrote was
            hydrated with context from these (easily accessible) sources.
          </p>

          <h2>AI&rsquo;s Google Ads moment</h2>
          <p>
            Here&rsquo;s what the future will look like: each person will have a
            consolidated memory store that aggregates facts worth remembering about
            the user from their online activity.
          </p>
          <p>
            This memory store will act as context-injecting middleware, ensuring
            that every message sent between human and AI will come with the perfect
            background context already added. This will lead to much more relevant,
            and ultimately magical AI interactions.
          </p>
          <p>
            This is basically exactly what happened with personalized advertising
            in the 2010s. Last decade, we built out massive infrastructure that
            pulls information from every corner of a user&rsquo;s online footprint
            and consolidate it to improve ad relevance. <Fnref id="2" /> An
            industrial-scale AI memory infrastructure buildout in the service of
            background context feels inevitable.
          </p>

          <h2>Model providers probably won&rsquo;t own the memory store</h2>
          <p>
            Sounds like a data moat. Who has access to the background context
            dataset? Not model providers, for the most part. It&rsquo;s highly
            balkanized:
          </p>
          <ul>
            <li>notes you scribble to yourself</li>
            <li>browsing and search history</li>
            <li>content you watch on tiktok and other platforms</li>
            <li>discord servers and group chats</li>
            <li>calendars, emails, files, code repos, etc</li>
          </ul>
          <p>
            A new company, sitting on some store of high-quality personal context
            data, will have to create this.
          </p>

          <h2>But wait, what if models do keep getting smarter?</h2>
          <p>
            These trends actually pretty much hold even in the world where AI does
            get a lot smarter. (I opted to focus on the &ldquo;what if ai not
            smarter&rdquo; case for clickbait, haha). Let&rsquo;s examine the
            principles underlying the arguments made in this post and show that
            they still apply in the world where AI gets much smarter.
          </p>
          <p>
            <strong>Response Quality = Intelligence + Context Quality.</strong>{" "}
            This will still hold&mdash;it&rsquo;s a fact about any AI product
            regardless of intelligence. Incremental gains will be achievable by
            increasing Intelligence or context quality.
          </p>
          <p>
            In fact, the relationship between Intelligence and Context Quality is
            likely convex; i.e. the smarter a model is, the more productive an
            improvement to Context Quality is.
          </p>
          <p>
            <strong>
              The most important personal context lies outside of intelligence
              providers.
            </strong>{" "}
            This is clearly still true; you could argue as AI intelligence improves
            it gives the winning player a chance at becoming the &ldquo;front door
            to the internet&rdquo;, but Google already is yet still lacks a lot of
            important context (personal notes, content consumption, text messages).
          </p>
          <p>
            <strong>AI model costs will go down.</strong> This may not hold true
            for all applications, but I suspect it <em>will</em> for consumer AI.
          </p>
          <p>
            We need to ask ourselves: is intelligence the bottleneck for any
            consumer AI use cases currently?
          </p>
          <p>
            For the largest consumer AI use cases (search for products and
            services, AI companion, cheating on homework), AI already works great.
            In fact, people complained when OpenAI upgraded ChatGPT to use more
            intelligent GPT-5 because it had fewer of the sycophantic qualities of
            4o.
          </p>

          <h2>Postscript: Beyond on-demand chat</h2>
          <p>
            In five years, we&rsquo;ll think it&rsquo;s crazy that we used to have
            to start every AI interaction by explaining everything. In ten years,
            we&rsquo;ll think it&rsquo;s crazy that we ever had to
            &ldquo;prompt&rdquo; AI at all. With high-enough-quality context, AI
            should be able to answer your question before you even ask it. Like
            personalized ads today, in the future AI will be able to read your
            mind.
          </p>
          <ul>
            <li>
              If it can see you&rsquo;re stuck on a bug, it texts you what
              you&rsquo;re missing.
            </li>
            <li>
              When you start to get hungry, you look at your phone to see a text w/
              lunch options
            </li>
            <li>
              If you&rsquo;re booking a vacation, it does deep research in the
              background to pre-empt your questions.
            </li>
          </ul>
          <p>
            As compute costs decrease (if models can&rsquo;t get more intelligent,
            then costs have to go down), we&rsquo;ll be able to invest more in
            precomputing responses to likely prompts creating these magical
            interactions.
          </p>

          <hr />

          <ol className="text-[14px] text-dim">
            <li id="fn-1">
              This framing comes from Letta&rsquo;s great Sleep Time Compute paper.
            </li>
            <li id="fn-2">
              Aside: we expected this massive consolidation of information by a few
              key players (we called it &ldquo;Big Data&rdquo;) to fundamentally
              change the way society functioned, but it turned out to mostly just
              enable better ads. Will personal information for AI be different? I
              think so&mdash;AI excels at creating value out of aggregated
              information from disparate sources. (Credit to this observation goes
              to my friend spot lemma.)
            </li>
          </ol>
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

function Fnref({ id }: { id: string }) {
  return (
    <a
      href={`#fn-${id}`}
      className="font-medium text-brand no-underline align-super text-[12px]"
    >
      [{id}]
    </a>
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
