import { redirect } from "next/navigation";

// Workspace settings were merged into the unified account settings page — a
// user has one active workspace, so settings live in one place now.
export default function WorkspaceSettingsRedirect() {
  redirect("/settings");
}
