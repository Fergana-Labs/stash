import { redirect } from "next/navigation";

// The Integrations panel lives inline on /settings. Keep this path
// alive as a deep-link target (anything that linked here historically
// still resolves), but bounce through to the canonical location.
export default function IntegrationsRedirect() {
  redirect("/settings");
}
