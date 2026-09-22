"use client";

import DeveloperGate from "@/components/developer/DeveloperGate";
import { useDeveloperExperience } from "@/lib/developer-experience";
import DeveloperSkill from "../skills/page";

export default function DeveloperWiki() {
  return <DeveloperGate><WikiPage /></DeveloperGate>;
}

function WikiPage() {
  const { wiki } = useDeveloperExperience();
  if (!wiki) return <p>This workspace uses Skills.</p>;
  return <DeveloperSkill />;
}
