"use client";

import { useRouter } from "next/navigation";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { EvalPageFrame } from "@/components/evals/eval-ui";
import CreateEval from "@/components/evals/CreateEval";

export default function NewEvalPage() {
  const router = useRouter();
  useBreadcrumbs([{ label: "Evals", href: "/reward-models/evals" }, { label: "New eval" }], "new-eval");
  return <EvalPageFrame title="Create an eval"><CreateEval onCreated={(id) => router.push(`/reward-models/evals/${id}`)} /></EvalPageFrame>;
}
