import type { Metadata } from "next";

import HomePage from "./_components/HomePage";

const title = "Stash · The Company Brain for Your AI Agents and Team";
const description =
  "Stash is the company brain for AI agents — it connects your tools, captures every session, and serves one searchable context graph agents and teams share.";

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
      alternateName: ["Stash AI", "Stash Memory", "Stash by Fergana Labs"],
      legalName: "Fergana Labs",
      url: SITE,
      logo: `${SITE}/logo.png`,
      description,
      sameAs: [
        "https://x.com/ferganalabs",
        "https://www.linkedin.com/company/ferganalabs",
        "https://github.com/Fergana-Labs",
        "https://github.com/Fergana-Labs/stash",
        "https://pypi.org/project/stashai/",
        "https://ferganalabs.com",
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
      alternateName: ["Stash AI", "Stash Memory"],
      applicationCategory: "DeveloperApplication",
      applicationSubCategory: "AI agent memory",
      operatingSystem: "Web, macOS, Linux, Windows",
      url: SITE,
      description,
      softwareHelp: { "@type": "WebPage", url: `${SITE}/docs` },
      license: "https://opensource.org/licenses/MIT",
      publisher: { "@id": `${SITE}#organization` },
      offers: [
        {
          "@type": "Offer",
          name: "Free",
          price: "0",
          priceCurrency: "USD",
          description: "Two connected sources, unlimited pages, sessions, and tables.",
          url: `${SITE}/#pricing`,
        },
        {
          "@type": "Offer",
          name: "Pro",
          price: "20",
          priceCurrency: "USD",
          description: "Unlimited connected sources, per user / month.",
          url: `${SITE}/#pricing`,
        },
      ],
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
