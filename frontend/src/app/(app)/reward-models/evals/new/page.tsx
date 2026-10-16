"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { errorMessage } from "@/components/reward-models/rm-text";
import { wzCreate } from "@/lib/wizard-api";

/** Every eval is created through the wizard: start a conversation and open it. */
export default function NewEvalPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    wzCreate()
      .then((session) => router.replace(`/reward-models/wizard/${session.id}`))
      .catch((e) => setError(errorMessage(e)));
  }, [router]);
  return <p role={error ? "alert" : "status"} className="p-6 text-sm text-muted-foreground">{error || "Starting a new eval…"}</p>;
}
