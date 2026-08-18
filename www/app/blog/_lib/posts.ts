// Author and date facts for the posts hosted on this site, in one place so the
// visible byline and the BlogPosting markup can never drift apart.

export type Author = {
  name: string;
  url: string;
  sameAs: string[];
};

export const AUTHORS: Record<string, Author> = {
  "Sam Liu": {
    name: "Sam Liu",
    url: "https://samzliu.substack.com",
    sameAs: ["https://x.com/samzliu", "https://samzliu.substack.com"],
  },
  "Henry Dowling": {
    name: "Henry Dowling",
    url: "https://henrydowling.com",
    sameAs: ["https://x.com/henrytdowling", "https://henrydowling.com"],
  },
};

export type Post = {
  slug: string;
  headline: string;
  description: string;
  author: Author;
  // ISO 8601. Month precision where that is all the byline claims — schema.org
  // accepts it, and inventing a day would be a fact we do not have.
  datePublished: string;
  byline: string;
};

export const POSTS: Record<string, Post> = {
  "why-no-great-consumer-ai": {
    slug: "why-no-great-consumer-ai",
    headline: "Why hasn't there been any great consumer AI (still)",
    description:
      "When models stop getting smarter, context engineering becomes the battleground. A case for the inevitable AI memory infrastructure buildout.",
    author: AUTHORS["Henry Dowling"],
    datePublished: "2025-08",
    byline: "August 2025",
  },
  "how-to-build-a-company-brain": {
    slug: "how-to-build-a-company-brain",
    headline:
      "Giving yourself superpowers: Advice on building a simple company brain",
    description:
      "An opinionated take on the right way to build a company brain — integrations, retrieval, memory, and privacy — so your AI agents can do real knowledge work.",
    author: AUTHORS["Henry Dowling"],
    datePublished: "2026-06",
    byline: "June 2026",
  },
  "three-dimensions-agent-memory-store": {
    slug: "three-dimensions-agent-memory-store",
    headline: "Three Dimensions That Matter To An Agent Memory Store",
    description:
      "An opinionated take on three key decisions memory builders need to make: retrieval, structure, and knowledge graphs.",
    author: AUTHORS["Henry Dowling"],
    datePublished: "2026-07-03",
    byline: "July 2026",
  },
  "open-questions-in-memory": {
    slug: "open-questions-in-memory",
    headline: "Open Questions in Memory, and Our Predictions",
    description:
      "The questions we argue about most with others building memory — labs vs startups, weight vs token space, retrieval vs blast radius, benchmarks — and where we think each one lands.",
    author: AUTHORS["Sam Liu"],
    datePublished: "2026-07-29",
    byline: "July 2026",
  },
};

const SITE = "https://www.joinstash.ai";

export function blogPostingJsonLd(post: Post) {
  return {
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    headline: post.headline,
    description: post.description,
    datePublished: post.datePublished,
    mainEntityOfPage: `${SITE}/blog/${post.slug}`,
    author: {
      "@type": "Person",
      name: post.author.name,
      url: post.author.url,
      sameAs: post.author.sameAs,
    },
    publisher: {
      "@type": "Organization",
      name: "Stash",
      url: SITE,
      logo: { "@type": "ImageObject", url: `${SITE}/logo.png` },
    },
  };
}
