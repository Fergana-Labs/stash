const GITHUB_URL = "https://github.com/Fergana-Labs/stash";

export default function SiteFooter() {
  return (
    <footer className="border-t border-border-subtle">
      <div className="mx-auto flex max-w-[1180px] flex-wrap items-center justify-between gap-3 px-5 py-6 font-mono text-[11.5px] text-muted sm:px-7">
        <span>© {new Date().getFullYear()} Fergana Labs</span>
        <span className="flex gap-4">
          <a href={GITHUB_URL} className="transition hover:text-ink">
            GitHub
          </a>
          <a href="/privacy" className="transition hover:text-ink">
            Privacy
          </a>
          <a href="/terms" className="transition hover:text-ink">
            Terms
          </a>
          <span>MIT licensed · self-hostable</span>
        </span>
      </div>
    </footer>
  );
}
