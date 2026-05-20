// Curated public Stash slugs surfaced as starter templates during onboarding.
//
// These need to exist as public, discoverable Stashes in prod (and dev) for
// Step 2 to render anything. If the slug list is empty (or the server returns
// 404 for all of them), Step 2 renders an empty state and is skippable.
//
// To add a template: publish a public Stash, copy its slug, and append here.

export type OnboardingTemplate = {
  slug: string;
  title: string;
  description: string;
};

export const ONBOARDING_TEMPLATES: OnboardingTemplate[] = [
  {
    slug: "engineering-handbook-starter",
    title: "Engineering handbook starter",
    description: "Coding conventions, on-call playbook, and incident template.",
  },
  {
    slug: "product-brief-template",
    title: "Product brief template",
    description: "Problem framing, success metrics, and rollout checklist.",
  },
  {
    slug: "sales-discovery-playbook",
    title: "Sales discovery playbook",
    description: "Discovery questions, qualification rubric, and call notes.",
  },
];
