import type { SessionArtifact } from "@/lib/api";

export interface SessionFileRow {
  path: string;
  artifact?: SessionArtifact;
}

export function sessionFileRows(
  filesTouched: string[],
  artifacts: SessionArtifact[],
  cwd: string | null
): SessionFileRow[] {
  const artifactsByPath = new Map(
    artifacts.map((artifact) => [sessionRelativePath(artifact.file_path, cwd), artifact])
  );
  const rows = filesTouched.map((path) => ({
    path,
    artifact: artifactsByPath.get(sessionRelativePath(path, cwd)),
  }));
  const represented = new Set(rows.map((row) => sessionRelativePath(row.path, cwd)));

  for (const artifact of artifacts) {
    const path = sessionRelativePath(artifact.file_path, cwd);
    if (!represented.has(path)) rows.push({ path: artifact.file_path, artifact });
  }
  return rows;
}

function sessionRelativePath(path: string, cwd: string | null): string {
  const normalized = path.replaceAll("\\", "/").replace(/^\.\//, "");
  if (!cwd) return normalized;
  const normalizedCwd = cwd.replaceAll("\\", "/").replace(/\/$/, "");
  return normalized.startsWith(`${normalizedCwd}/`)
    ? normalized.slice(normalizedCwd.length + 1)
    : normalized;
}
