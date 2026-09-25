"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { useAuth } from "@/hooks/useAuth";
import { getSharedSkillContents, type SharedSkillContents } from "@/lib/api";
import { loginPathWithNext } from "@/lib/loginRedirect";
import { SKILL_MD, stripFrontmatter } from "@/lib/localSkill";

export default function SharedSkillClient({ folderId }: { folderId: string }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [data, setData] = useState<SharedSkillContents | null>(null);
  const [error, setError] = useState("");
  const userId = user?.id;

  useEffect(() => {
    if (loading) return;
    if (!userId) {
      router.replace(loginPathWithNext(`/shared-skills/${folderId}`));
      return;
    }
    let cancelled = false;
    getSharedSkillContents(folderId)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((cause) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "Could not load this Skill.");
        }
      });
    return () => { cancelled = true; };
  }, [folderId, loading, router, userId]);

  if (error) return <p role="alert" className="p-6 text-error">{error}</p>;
  if (!data) return <p className="p-6 text-muted-foreground">Loading Skill…</p>;
  const instructions = data.contents.pages.find(
    (page) => page.name === SKILL_MD && page.folder_path.length === 0,
  );
  if (!instructions) return <p role="alert" className="p-6 text-error">This Skill is missing its SKILL.md.</p>;
  const files = [
    ...data.contents.pages.map((page) => ({ ...page, href: `/p/${page.id}` })),
    ...data.contents.files.map((file) => ({ ...file, href: `/f/${file.id}` })),
    ...data.contents.tables.map((table) => ({ ...table, href: `/tables/${table.id}` })),
  ];

  return (
    <div className="flex-1 overflow-y-auto px-6 py-8">
      <div className="mx-auto max-w-3xl space-y-6">
        <h1 className="text-2xl font-semibold">{data.folder_name}</h1>
        <div className="prose prose-sm max-w-none dark:prose-invert">
          <Markdown remarkPlugins={[remarkGfm]}>
            {stripFrontmatter(instructions.content_markdown)}
          </Markdown>
        </div>
        <section>
          <h2 className="mb-3 text-base font-semibold">Skill files</h2>
          <ul className="divide-y divide-border rounded-lg border border-border">
            {files.map((file) => (
              <li key={file.id}>
                <Link href={file.href} className="block px-4 py-3 text-sm hover:bg-raised">
                  {[...file.folder_path, file.name].join("/")}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
