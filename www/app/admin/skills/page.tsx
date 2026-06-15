import type { Metadata } from "next";

import SkillsAdminClient, { type ImportedRepo } from "./SkillsAdminClient";

export const metadata: Metadata = {
  title: "Discover Skills · Admin",
  robots: { index: false, follow: false },
};

const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3456";

export default async function SkillsAdminPage() {
  const token = process.env.ADMIN_PASSWORD;
  if (!token) {
    return <ErrorShell body="ADMIN_PASSWORD env var is not set on the www server." />;
  }

  const res = await fetch(`${apiUrl}/api/v1/admin/discover-skills`, {
    headers: { "X-Admin-Token": token },
    cache: "no-store",
  });
  if (!res.ok) {
    return <ErrorShell body={await res.text()} />;
  }
  const { repos } = (await res.json()) as { repos: ImportedRepo[] };

  return <SkillsAdminClient repos={repos} />;
}

function ErrorShell({ body }: { body: string }) {
  return (
    <main className="min-h-screen bg-gray-50">
      <div className="mx-auto max-w-[720px] px-7 py-20">
        <h1 className="text-2xl font-semibold text-gray-800">Discover Skills</h1>
        <pre className="mt-4 whitespace-pre-wrap rounded-md border border-gray-200 bg-white p-4 font-mono text-[12px] text-gray-600">
          {body}
        </pre>
      </div>
    </main>
  );
}
