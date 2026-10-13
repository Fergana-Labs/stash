"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { EvalPageFrame } from "@/components/evals/eval-ui";
import CreateEval from "@/components/evals/CreateEval";

export default function NewEvalPage() {
  const router = useRouter();
  useBreadcrumbs([{ label: "Evals", href: "/reward-models/evals" }, { label: "New eval" }], "new-eval");
  return <EvalPageFrame><Link href="/reward-models/evals" className="mb-4 inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" />Back to evals</Link><h1 className="mb-5 text-lg font-semibold tracking-tight">Create an eval</h1><CreateEval onCreated={(id) => router.push(`/reward-models/evals/${id}`)} /></EvalPageFrame>;
}
