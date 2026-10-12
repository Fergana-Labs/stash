"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imLoadExample } from "@/lib/intuition-api";
import { Spinner } from "./im-ui";

/** Creates a bundled, pre-graded example model and opens it. */
export default function LoadExampleButton({
  slug,
  name,
  variant = "outline",
  size = "default",
  children = "Load example",
}: {
  slug: string;
  name?: string;
  variant?: "outline" | "default";
  size?: "default" | "sm";
  children?: React.ReactNode;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  async function load() {
    setBusy(true);
    try {
      const detail = await imLoadExample(slug);
      toast.success(`Loaded “${detail.model.name}”`);
      router.push(`/reward-models/intuitions/${detail.model.id}`);
    } catch (e) {
      toast.error(errorMessage(e));
      setBusy(false);
    }
  }
  return (
    <Button variant={variant} size={size} onClick={() => void load()} disabled={busy} aria-label={name ? `Load example: ${name}` : undefined}>
      {busy ? <Spinner /> : <Sparkles />}
      {children}
    </Button>
  );
}
