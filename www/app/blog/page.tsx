import type { Metadata } from "next";
import Link from "next/link";

import SiteFooter from "../_components/SiteFooter";
import SiteHeader from "../_components/SiteHeader";

export const metadata: Metadata = {
  alternates: { canonical: "/blog" },
  title: "Blog · Stash",
  description:
    "Writing on memory, research, and the messy human side of building products from the team at Fergana Labs.",
};

type Post = {
  title: string;
  blurb: string;
  href: string;
  author: string;
};

const POSTS: Post[] = [
  {
    title: "The context gold rush: why everyone is building the same thing",
    blurb:
      "Context graph, company brain, LLM wiki — a map of who is building the context layer, the patterns that have converged, and what is still missing before any of it reaches mass adoption.",
    href: "/blog/context-gold-rush",
    author: "Sam Liu",
  },
  {
    title:
      "Containerizing memory: the real barrier to continual learning and enterprise AI adoption",
    blurb:
      "The shipping container standardized freight and the world economy followed. Agent memory has no such standard yet, and that missing consistency is why enterprise adoption has been mixed.",
    href: "/blog/containerizing-memory",
    author: "Sam Liu",
  },
  {
    title: "Open Questions in Memory, and Our Predictions",
    blurb:
      "The questions we argue about most with others building memory — labs vs startups, weight vs token space, retrieval vs blast radius, benchmarks — and where we think each one lands.",
    href: "/blog/open-questions-in-memory",
    author: "Sam Liu",
  },
  {
    title: "Giving yourself superpowers: Advice on building a simple company brain",
    blurb:
      "An opinionated take on the right way to build a company brain — integrations, retrieval, memory, and privacy — so your AI agents can do real knowledge work.",
    href: "/blog/how-to-build-a-company-brain",
    author: "Henry Dowling",
  },
  {
    title: "Why hasn't there been any great consumer AI (still)",
    blurb:
      "When models stop getting smarter, context engineering becomes the battleground — and the case for an inevitable AI memory infrastructure buildout.",
    href: "/blog/why-no-great-consumer-ai",
    author: "Henry Dowling",
  },
  {
    title: "Three Dimensions That Matter To An Agent Memory Store",
    blurb:
      "An opinionated take on three key decisions memory builders need to make: retrieval, structure, and knowledge graphs.",
    href: "/blog/three-dimensions-agent-memory-store",
    author: "Henry Dowling",
  },
  {
    title: "Agents are Octopuses",
    blurb:
      "Collaborative agent systems with shared memory as a new paradigm beyond swarms and assembly lines.",
    href: "https://samzliu.substack.com/p/agents-are-octopuses",
    author: "Sam Liu",
  },
  {
    title: "I Dropped Out of My PhD",
    blurb: "Choosing the start-up life over the academic path.",
    href: "https://samzliu.substack.com/p/i-dropped-out-of-my-phd",
    author: "Sam Liu",
  },
  {
    title: "Why Context Windows Won't Save Us",
    blurb: "Why raw context length is not a substitute for true memory in AI.",
    href: "https://samzliu.substack.com/p/why-context-windows-wont-save-us",
    author: "Sam Liu",
  },
  {
    title: "In Praise of Mess",
    blurb: "Embracing creative disorder as a feature, not a bug.",
    href: "https://samzliu.substack.com/p/in-praise-of-mess",
    author: "Sam Liu",
  },
  {
    title: "Why memory is critical",
    blurb: "Why memory is critical in building useful AI products.",
    href: "https://henrydowling.com/background-context.html",
    author: "Henry Dowling",
  },
  {
    title: "Techniques to improve coding agent velocity",
    blurb:
      "Strategies for making coding agents more autonomous and effective.",
    href: "https://henrydowling.com/agent-velocity.html",
    author: "Henry Dowling",
  },
  {
    title: "When it Wraps, it Rhymes",
    blurb: "Predicting the future of AI by looking at the past.",
    href: "https://x.com/samzliu/status/2021341001655423487",
    author: "Sam Liu",
  },
  {
    title: "The Real Bitter Lesson",
    blurb: "The nuances behind the classic refrain.",
    href: "https://x.com/samzliu/status/2034712919871819830",
    author: "Sam Liu",
  },
];

export default function BlogPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <SiteHeader current="Blog" />

      <section className="mx-auto max-w-[1180px] px-5 pb-8 pt-16 sm:px-7 md:pt-24">
        <h1 className="font-display text-[clamp(38px,5vw,60px)] font-medium leading-[1.06] tracking-[-0.028em] text-ink">
          Writing
        </h1>
        <p className="mt-6 max-w-[54ch] text-[18px] leading-[1.6] text-dim">
          Notes on memory, continual learning, and what we find while building Stash. From the team
          at{" "}
          <Link
            href="https://ferganalabs.com"
            className="text-brand underline decoration-brand/40 underline-offset-4 transition hover:text-ink"
          >
            Fergana Labs
          </Link>
          .
        </p>
      </section>

      <section className="mx-auto max-w-[1180px] px-5 pb-24 sm:px-7">
        {POSTS.map((post) => (
          <PostRow key={post.href} post={post} />
        ))}
      </section>

      <SiteFooter />
    </main>
  );
}

function PostRow({ post }: { post: Post }) {
  const isExternal = post.href.startsWith("http");
  return (
    <Link
      href={post.href}
      target={isExternal ? "_blank" : undefined}
      rel={isExternal ? "noopener noreferrer" : undefined}
      className="group grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-5 border-t border-border-subtle py-5 last:border-b"
    >
      <span>
        <span className="font-display text-[19px] font-medium tracking-[-0.02em] text-ink transition group-hover:text-brand">
          {post.title}
        </span>
        <p className="mt-1.5 max-w-[62ch] text-[15px] leading-[1.6] text-dim">{post.blurb}</p>
      </span>
      <span className="text-right font-mono text-[11.5px] uppercase tracking-[0.08em] text-muted">
        {post.author}
      </span>
    </Link>
  );
}
