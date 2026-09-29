import DocsShell, { type NavSection } from "../_components/DocsShell";

const NAV: NavSection[] = [
  {
    title: "Reward model fine-tuning",
    items: [
      { href: "/reward-model-fine-tuning", label: "Overview" },
      { href: "/reward-model-fine-tuning/trace-format", label: "Trace format" },
      { href: "/reward-model-fine-tuning/annotations", label: "Annotations" },
      { href: "/reward-model-fine-tuning/training", label: "Training" },
      { href: "/reward-model-fine-tuning/gepa", label: "GEPA" },
      { href: "/reward-model-fine-tuning/api", label: "API reference" },
    ],
  },
];

export default function RewardModelFineTuningLayout({ children }: { children: React.ReactNode }) {
  return (
    <DocsShell nav={NAV} label="Reward model fine-tuning">
      {children}
    </DocsShell>
  );
}
