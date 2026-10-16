"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { stageWizardMessage } from "@/components/wizard/wizard-navigation";
export default function Page() {
  const router = useRouter();
  const [error, setError] = useState("");
  useEffect(() => {
    void apiFetch<{ session_id: string }>("/api/v1/taste/resume-wizard", {
      method: "POST",
    })
      .then((r) => {
        const key = `website-eval-resumed:${r.session_id}`;
        if (!sessionStorage.getItem(key)) {
          sessionStorage.setItem(key, "true");
          stageWizardMessage(r.session_id, {
            id: Date.now(),
            kind: "event",
            text: "Continue in this eval wizard using the existing recovered website examples. Use clear feedback automatically and show a brief evidence summary inline. Do not collect new data or launch training or optimization in this resume step.",
          });
        }
        router.replace(`/reward-models/wizard/${r.session_id}`);
      })
      .catch((e) => setError(String(e)));
  }, [router]);
  return (
    <p role={error ? "alert" : "status"} className="p-8 text-sm">
      {error || "Opening your eval wizard…"}
    </p>
  );
}
