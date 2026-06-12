import type { Metadata } from "next";
import { redirect } from "next/navigation";

import CreateEditor from "../_components/CreateEditor";

export const metadata: Metadata = {
  title: "New page · Stash Pages",
  robots: { index: false },
};

type SearchParams = Promise<{ type?: string; visibility?: string; editable?: string }>;

// The editor screen the create wizard opens. Settings ride in the query
// string so a refresh keeps them; anything malformed goes back to the
// wizard rather than guessing.
export default async function NewPastePage({ searchParams }: { searchParams: SearchParams }) {
  const { type, visibility = "public", editable = "false" } = await searchParams;
  const validType = type === "markdown" || type === "html";
  const validVisibility = visibility === "public" || visibility === "unlisted";
  if (!validType || !validVisibility) redirect("/pages");

  return (
    <main className="min-h-screen bg-background text-foreground">
      <CreateEditor
        contentType={type}
        visibility={visibility}
        publicEdit={editable === "true"}
      />
    </main>
  );
}
