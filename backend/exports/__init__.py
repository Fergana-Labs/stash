"""Local export tasks (PDF, PPTX).

Each format registers itself with the exporter registry at import time.
Adding a new format = drop a new file + register it.

Google Slides export lives under `integrations/google/exporters/` since
it talks to a third-party API and reuses the user's Google OAuth token.
"""

from ..integrations.registry import register_exporter

register_exporter("pdf", "backend.exports.pdf.export_pdf")
register_exporter("pptx", "backend.exports.pptx.export_pptx")

# Side-effect import to register the gslides exporter task too.
from ..integrations.google.exporters import slides  # noqa: F401,E402
