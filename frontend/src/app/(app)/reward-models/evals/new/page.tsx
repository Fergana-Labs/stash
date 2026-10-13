"use client";

import { useRouter } from "next/navigation";
import { useBreadcrumbs } from "@/components/BreadcrumbContext";
import { RmPage } from "@/components/reward-models/rm-ui";
import CreateEval from "@/components/evals/CreateEval";

export default function NewEvalPage() {
  const router = useRouter();
  useBreadcrumbs([{ label: "Evals", href: "/reward-models/evals" }, { label: "New eval" }], "new-eval");
  return <RmPage title="Create an eval"><CreateEval onCreated={(id) => router.push(`/reward-models/evals/${id}`)} /></RmPage>;
}
