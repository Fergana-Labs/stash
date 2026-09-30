// Design from Priyadarshan's trace viewer (projects/trace_viewer)
import {
  Bot,
  FilePen,
  FilePlus,
  FileText,
  Globe,
  ListChecks,
  MessageCircleQuestion,
  MousePointer2,
  Plug,
  Search,
  Sparkles,
  Terminal,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import type { ToolFamily } from "./trace-rows";

const ICONS: Record<ToolFamily, LucideIcon> = {
  shell: Terminal,
  read: FileText,
  edit: FilePen,
  write: FilePlus,
  search: Search,
  web: Globe,
  agent: Bot,
  ask: MessageCircleQuestion,
  task: ListChecks,
  skill: Sparkles,
  mcp: Plug,
  browser: MousePointer2,
  other: Wrench,
};

export default function ToolIcon({ family, size = 12 }: { family: ToolFamily; size?: number }) {
  const Icon = ICONS[family];
  return <Icon size={size} strokeWidth={1.75} aria-hidden />;
}
