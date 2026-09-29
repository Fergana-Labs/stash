import DocsShell from "../_components/DocsShell";
import { DOCS_NAV } from "../_components/docs-nav";

export default function RewardModelsLayout({ children }: { children: React.ReactNode }) {
  return (
    <DocsShell nav={DOCS_NAV} label="Documentation">
      {children}
    </DocsShell>
  );
}
