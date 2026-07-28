"""Uploading an HTML file has to bring its pictures with it.

An exported report points at its images by relative path. Uploading only the
markup leaves each one pointing at a path that exists on the author's disk and
nowhere else, so the page renders with broken images. The upload rewrites those
references to the files' permanent download route — the one route that also
serves a viewer holding a public link.
"""

from pathlib import Path

from cli.main import _upload_html_with_assets


class FakeClient:
    """Records uploads and hands back predictable file ids."""

    def __init__(self):
        self.uploads: list[tuple[str, str | None]] = []
        self.sent_html = ""
        self._next = 0

    def upload_file(self, path: str, folder_id: str | None = None) -> dict:
        name = Path(path).name
        self.uploads.append((name, folder_id))
        if name.endswith(".html"):
            self.sent_html = Path(path).read_text()
        self._next += 1
        return {"id": f"file-{self._next}", "name": name, "kind": "file"}


def _write(tmp_path: Path, html: str) -> Path:
    (tmp_path / "chart.png").write_bytes(b"\x89PNG fake")
    report = tmp_path / "report.html"
    report.write_text(html)
    return report


def test_relative_image_is_uploaded_and_rewritten(tmp_path: Path) -> None:
    report = _write(tmp_path, '<img src="chart.png">')
    client = FakeClient()

    page = _upload_html_with_assets(client, report)

    # The picture went up, and the markup now points at it rather than at a
    # path that only exists on the author's machine.
    assert ("chart.png", None) in client.uploads
    assert page["asset_file_ids"] == ["file-1"]
    assert client.sent_html == '<img src="/api/v1/me/files/file-1/download">'
    # The page is named from the filename, so the rewritten copy keeps it.
    assert ("report.html", None) in client.uploads


def test_svg_and_css_references_are_followed(tmp_path: Path) -> None:
    (tmp_path / "logo.svg").write_text("<svg/>")
    report = tmp_path / "report.html"
    report.write_text(
        '<svg><image href="logo.svg"/></svg><div style="background: url(logo.svg)"></div>'
    )
    client = FakeClient()

    page = _upload_html_with_assets(client, report)

    # One upload for the one file, even though it's referenced twice and
    # through two different syntaxes.
    assert [n for n, _ in client.uploads if n == "logo.svg"] == ["logo.svg"]
    assert page["asset_file_ids"] == ["file-1"]


def test_remote_and_data_urls_are_left_alone(tmp_path: Path) -> None:
    report = _write(
        tmp_path,
        '<img src="https://cdn.example/a.png">'
        '<img src="data:image/png;base64,AAAA">'
        '<a href="#section">jump</a>',
    )
    client = FakeClient()

    page = _upload_html_with_assets(client, report)

    assert page["asset_file_ids"] == []
    assert [n for n, _ in client.uploads] == ["report.html"]


def test_missing_asset_does_not_fail_the_upload(tmp_path: Path) -> None:
    """A reference to a file the author didn't ship is their problem to fix —
    it must not cost them the upload."""
    report = tmp_path / "report.html"
    report.write_text('<img src="nope.png">')
    client = FakeClient()

    page = _upload_html_with_assets(client, report)

    assert page["asset_file_ids"] == []
    assert [n for n, _ in client.uploads] == ["report.html"]


def test_assets_already_uploaded_are_reused(tmp_path: Path) -> None:
    """A directory upload sends the pictures first; the HTML pass must point at
    those rows instead of uploading a second copy of every image."""
    report = _write(tmp_path, '<img src="chart.png">')
    client = FakeClient()
    known = {(tmp_path / "chart.png").resolve(): "/api/v1/me/files/existing/download"}

    page = _upload_html_with_assets(client, report, folder_id="folder-1", known_assets=known)

    assert [n for n, _ in client.uploads] == ["report.html"]
    assert page["asset_file_ids"] == []
