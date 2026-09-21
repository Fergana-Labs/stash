import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { getSharedSkillContents } from "@/lib/api";
import SharedSkillClient from "./SharedSkillClient";

vi.mock("@/hooks/useAuth", () => ({ useAuth: () => ({ user: { id: "recipient" }, loading: false }) }));
const router = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/api", () => ({ getSharedSkillContents: vi.fn() }));
afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

it("opens a shared Skill through the recipient endpoint without requiring the owner's scope", async () => {
  vi.mocked(getSharedSkillContents).mockResolvedValue({ folder_id: "shared", folder_name: "Team playbook", contents: {
    pages: [{id: "instructions", name: "SKILL.md", folder_path: [], content_type: "markdown", content_markdown: "---\nname: Team playbook\ndescription: Deploy safely.\n---\nRun the checks.", content_html: "", html_layout: "responsive", updated_at: "2026-09-21"}],
    files: [], tables: [], subfolders: [],
  }});
  render(<SharedSkillClient folderId="shared" />);
  expect(await screen.findByText("Run the checks.")).toBeInTheDocument();
  expect(getSharedSkillContents).toHaveBeenCalledWith("shared");
  expect(screen.getByRole("link", { name: "SKILL.md" })).toHaveAttribute("href", "/p/instructions");
});

it("shows access denial instead of an empty Skill", async () => {
  vi.mocked(getSharedSkillContents).mockRejectedValue(new Error("Not allowed to read this folder"));
  render(<SharedSkillClient folderId="private" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Not allowed to read this folder");
});
