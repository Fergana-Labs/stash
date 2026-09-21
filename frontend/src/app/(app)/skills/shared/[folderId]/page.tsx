import type { Metadata } from "next";
import SharedSkillClient from "./SharedSkillClient";

export const metadata: Metadata = { title: "Shared Skill - Stash" };

export default async function SharedSkillRoute({ params }: { params: Promise<{ folderId: string }> }) {
  const { folderId } = await params;
  return <SharedSkillClient key={folderId} folderId={folderId} />;
}
