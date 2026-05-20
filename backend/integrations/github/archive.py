"""Resolve git host URLs to a zip archive URL + auth header.

Supports GitHub, GitLab, Bitbucket, and any URL ending in `.zip`.

Returns enough info for the importer task to do a single streaming GET:
- the archive URL (post-host-detection, ready to fetch)
- a dict of headers to send (typically an Authorization)
- the host kind (for logging / error messages)
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, urlparse


@dataclass
class ResolvedArchive:
    archive_url: str
    headers: dict[str, str]
    host_kind: str  # 'github' | 'gitlab' | 'bitbucket' | 'generic'


class UnsupportedHostError(ValueError):
    pass


def _parse_owner_repo(path: str) -> tuple[str, str] | None:
    parts = [p for p in path.strip("/").split("/") if p]
    if len(parts) < 2:
        return None
    # tolerate trailing `.git` or extra path segments
    repo = parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return parts[0], repo


def resolve_archive_url(
    url: str,
    ref: str | None,
    *,
    github_token: str | None = None,
    pat: str | None = None,
) -> ResolvedArchive:
    """Resolve `url` to an archive URL + auth headers.

    `github_token` is the user's connected GitHub OAuth token (preferred
    for github.com). `pat` is a manually-entered personal access token
    (used for any host when supplied; never persisted).
    """
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()

    if url.lower().endswith(".zip"):
        headers = {}
        if pat:
            headers["Authorization"] = f"Bearer {pat}"
        return ResolvedArchive(archive_url=url, headers=headers, host_kind="generic")

    if host == "github.com" or host.endswith(".github.com"):
        owner_repo = _parse_owner_repo(parsed.path)
        if owner_repo is None:
            raise UnsupportedHostError("github.com URL must include /owner/repo")
        owner, repo = owner_repo
        ref_seg = f"/{quote(ref)}" if ref else ""
        archive_url = f"https://api.github.com/repos/{owner}/{repo}/zipball{ref_seg}"
        token = github_token or pat
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return ResolvedArchive(archive_url=archive_url, headers=headers, host_kind="github")

    if host == "gitlab.com" or host.endswith(".gitlab.com"):
        # GitLab needs the project path URL-encoded: owner/repo → owner%2Frepo
        project = parsed.path.strip("/")
        if project.endswith(".git"):
            project = project[:-4]
        if not project or "/" not in project:
            raise UnsupportedHostError("gitlab.com URL must include /owner/repo")
        encoded = quote(project, safe="")
        ref_q = f"?sha={quote(ref)}" if ref else ""
        archive_url = f"https://gitlab.com/api/v4/projects/{encoded}/repository/archive.zip{ref_q}"
        headers = {}
        if pat:
            headers["PRIVATE-TOKEN"] = pat
        return ResolvedArchive(archive_url=archive_url, headers=headers, host_kind="gitlab")

    if host == "bitbucket.org" or host.endswith(".bitbucket.org"):
        owner_repo = _parse_owner_repo(parsed.path)
        if owner_repo is None:
            raise UnsupportedHostError("bitbucket.org URL must include /workspace/repo")
        ws, repo = owner_repo
        ref_seg = quote(ref) if ref else "HEAD"
        archive_url = f"https://bitbucket.org/{ws}/{repo}/get/{ref_seg}.zip"
        headers = {}
        if pat:
            # Bitbucket app password — sent as basic auth username:app_password.
            # PAT-as-bearer also works on recent Bitbucket Cloud.
            headers["Authorization"] = f"Bearer {pat}"
        return ResolvedArchive(archive_url=archive_url, headers=headers, host_kind="bitbucket")

    raise UnsupportedHostError(
        "paste a github.com / gitlab.com / bitbucket.org URL, or a direct .zip archive URL"
    )
