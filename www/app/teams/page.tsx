import type { Metadata } from "next";

import HomePage from "../_components/HomePage";

export const metadata: Metadata = {
  title: "Stash for teams · Long-running agents that compound",
  description:
    "Bring your own agent and give your team a workspace where every session compounds — continual learning, a shared data moat, and agents that take action, not just remember.",
};

export default function TeamsPage() {
  return <HomePage />;
}
