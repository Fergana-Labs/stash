import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
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
      <Header />

      <section className="mx-auto max-w-[1200px] px-7 pb-10 pt-16">
        <p className="flex items-center font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
          <span className="mr-[10px] inline-block h-[6px] w-[6px] rounded-full bg-brand" />
          Blog
        </p>
        <h1 className="mt-5 text-balance font-display text-[clamp(36px,4.6vw,56px)] font-black leading-[1.02] tracking-[-0.035em] text-ink">
          Notes from the team<br />
          <span className="text-brand">building Stash.</span>
        </h1>
        <p className="mt-6 max-w-[640px] text-[17px] leading-[1.6] text-foreground">
          Writing on memory, research, and the messy human side of building
          products. From the team at{" "}
          <Link
            href="https://ferganalabs.com"
            className="font-medium text-brand underline underline-offset-4 transition hover:text-ink"
          >
            Fergana Labs
          </Link>{" "}
          behind Stash.
        </p>
      </section>

      <section className="mx-auto max-w-[1200px] px-7 pb-24">
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {POSTS.map((post) => (
            <PostCard key={post.href} post={post} />
          ))}
        </div>
      </section>
    </main>
  );
}

function PostCard({ post }: { post: Post }) {
  return (
    <Link
      href={post.href}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex flex-col rounded-xl border border-border-subtle bg-raised/40 p-6 transition hover:border-ink hover:bg-raised"
    >
      <h2 className="font-display text-[20px] font-black leading-[1.2] tracking-[-0.02em] text-ink">
        {post.title}
      </h2>
      <p className="mt-3 flex-1 text-[15px] leading-[1.55] text-dim">
        {post.blurb}
      </p>
      <div className="mt-5 flex items-center justify-between text-[13px] text-muted">
        <span>{post.author}</span>
        <span className="text-brand transition group-hover:translate-x-0.5">
          Read →
        </span>
      </div>
    </Link>
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
