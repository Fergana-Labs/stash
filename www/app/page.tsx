import type { Metadata } from "next";

import HomePage from "./_components/HomePage";

const title = "Stash · Verifiers for the Next Era of AI Scaling";
const description =
  "Stash is a platform enabling verifiers for non-deterministic domains and long horizon agents.";

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
        contactType: "general inquiries",
        email: "sam@joinstash.ai",
        url: SITE,
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
      about: { "@id": `${SITE}#organization` },
      primaryImageOfPage: { "@type": "ImageObject", url: `${SITE}/opengraph-image` },
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
