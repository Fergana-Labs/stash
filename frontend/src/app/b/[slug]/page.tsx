import { redirect } from "next/navigation";

// Legacy session-bundle URL. After the sharing-unification PR, all share
// surfaces (workspace, session, page, folder, file) resolve under
// /share/{token-or-slug}. /b/{slug} is now a thin 308 redirect for
// backward compat — bookmarks and old MCP citations keep working.

export default async function BundleRedirect({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  redirect(`/share/${slug}`);
}
