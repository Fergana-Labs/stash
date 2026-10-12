"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Sparkles } from "lucide-react";
import { toast } from "sonner";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imLoadExample } from "@/lib/intuition-api";
import { Spinner } from "./im-ui";

/** Creates the bundled, pre-graded demo model and opens it. */
export default function LoadExampleButton({ variant = "outline", asMenuItem = false }: { variant?: "outline" | "default"; asMenuItem?: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  async function load() {
    setBusy(true);
    try {
      const detail = await imLoadExample();
      toast.success(`Loaded “${detail.model.name}”`);
      router.push(`/reward-models/models/sandbox/${detail.model.id}`);
    } catch (e) {
      toast.error(errorMessage(e));
      setBusy(false);
    }
  }
  if (asMenuItem) return <DropdownMenuItem disabled={busy} onSelect={() => void load()}><Sparkles />Load example</DropdownMenuItem>;
  return (
    <Button variant={variant} onClick={() => void load()} disabled={busy}>
      {busy ? <Spinner /> : <Sparkles />}
      Load example
    </Button>
  );
}
