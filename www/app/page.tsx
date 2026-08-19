import type { Metadata } from "next";

import HomePage from "./_components/HomePage";

const title = "Stash · Agents That Learn From the Real World";
const description =
  "Stash is an applied AI lab building continual learning. We refine raw agent logs into context any agent can read, and use the same logs to train models that improve with every run.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: "/" },
  openGraph: { title, description, type: "website", url: "/" },
  twitter: { card: "summary_large_image", title, description },
};

const SITE = "https://www.joinstash.ai";

// Served in the initial HTML (not injected client-side) because AI crawlers and
// Google's structured-data parser do not execute our JavaScript.
const jsonLd = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": `${SITE}#organization`,
      name: "Stash",
      legalName: "Fergana Labs",
      url: SITE,
      logo: `${SITE}/logo.png`,
      description,
      sameAs: [
        "https://x.com/ferganalabs",
        "https://github.com/Fergana-Labs",
        "https://github.com/Fergana-Labs/stash",
      ],
      contactPoint: {
        "@type": "ContactPoint",
        contactType: "sales",
        email: "sam@joinstash.ai",
        url: `${SITE}/contact-sales`,
      },
    },
    {
      "@type": "WebSite",
      "@id": `${SITE}#website`,
      url: SITE,
      name: "Stash",
      description,
      publisher: { "@id": `${SITE}#organization` },
      inLanguage: "en",
    },
    {
      "@type": "WebPage",
      "@id": `${SITE}#webpage`,
      url: SITE,
      name: title,
      description,
      isPartOf: { "@id": `${SITE}#website` },
      about: { "@id": `${SITE}#software` },
      primaryImageOfPage: { "@type": "ImageObject", url: `${SITE}/opengraph-image` },
    },
    {
      "@type": "SoftwareApplication",
      "@id": `${SITE}#software`,
      name: "Stash",
      applicationCategory: "DeveloperApplication",
      applicationSubCategory: "AI agent memory",
      operatingSystem: "Web, macOS, Linux, Windows",
      url: SITE,
      description,
      softwareHelp: { "@type": "WebPage", url: `${SITE}/docs` },
      license: "https://opensource.org/licenses/MIT",
      publisher: { "@id": `${SITE}#organization` },
    },
  ],
};

export default function Page() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <HomePage />
    </>
  );
}
