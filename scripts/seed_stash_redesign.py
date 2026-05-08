"""Seed sample data for the stash redesign.

Idempotent: drops + recreates the demo stash on every run. Uploads real
files to the configured S3 (MinIO in local dev).

Run:
    DATABASE_URL=postgresql://octopus:octopus@localhost:5432/octopus \\
        python scripts/seed_stash_redesign.py
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg

# Make backend importable so we can call storage_service.upload_file.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Load backend/.env so S3 creds are visible. The storage_service module reads
# S3_* env vars at import time, so dotenv must run before that import.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / "backend" / ".env")

from backend.services import storage_service  # noqa: E402

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://octopus:octopus@localhost:5432/octopus"
)

SAM_ID = UUID("fc4d8f89-8d5f-41d6-91b8-5a8c965bbac0")
HENRY_ID = UUID("a0000000-0000-0000-0000-000000000099")
STASH_ID = UUID("d0000000-0000-0000-0000-000000000001")
STASH2_ID = UUID("d0000000-0000-0000-0000-000000000002")

NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------

NARRATIVE_DECK = """# Acme — Series A

Reinventing how mid-market teams handle accounts payable.

---

# The problem

AP teams at companies between $20M and $500M ARR live in a swamp of
PDF invoices, ad-hoc Slack approvals, and one-off ERP integrations.

- 4-7 day average invoice cycle
- 20% of approvals lost in DM threads
- $250B/yr in late-payment penalties (US, 2025)

---

# Our wedge

A one-click invoice-to-approval flow. Drop a PDF → an agent extracts
fields, routes to the right approver, and posts to NetSuite/QuickBooks
without anyone touching a form.

---

# Traction

- 32 paying customers, all between $20M-$200M ARR
- $1.4M ARR · 18% MoM net revenue growth (last 6 months)
- 92% gross margin
- Net retention 138%

---

# Team

- **Karri Ojala** (CEO) — ex-Stripe billing, MIT '14
- **Sam Liu** (CTO) — ex-Vercel infra, ML systems
- **Mei Tanaka** (Design) — ex-Linear, ex-Notion
- 4 eng, 2 GTM. All in NYC.

---

# The ask

$8M Series A at $48M post.

- 18 months runway → 8x ARR ($1.4M → $11M)
- Build the GL-side agent (NetSuite, QBO, Sage)
- Hire 4 eng, 2 AE, 1 design

Lead investor target: a fund that can write a $5M+ check and
go to $20M+ in B.
"""

INVESTOR_FAQ = """# Investor FAQ

## What's your ARR right now?
$1.4M as of April 2026, growing 18% MoM net new for the last 6 months.

## What's the wedge?
Invoice-to-approval. PDFs in, posted journal entries out, no human
touches a form. We ship with audit-grade citations as a first-class
output — that beats horizontal AI breadth in regulated buys.

## Why now?
Mid-market AP just unlocked dedicated AI procurement budget. The 9-month
legal-tech procurement cycle collapsed to weeks once an AI committee
showed up.

## What's churn?
1.2% monthly logo churn over the last 6 months. Net retention 138%.
The 138% is real — usage-based billing on volume tiers, not seat
expansion.

## Who's a competitor?
- **Tipalti** — incumbent, 12-month implementations, no AI agent surface
- **Stampli** — closer, but they're an OCR play not an agent play
- **Vendor.co** (stealth, ex-Tesseract folks) — in fundraising mode,
  not yet shipping
"""

CUSTOMER_QA = """# Customer Q&A

## "Replaced 4 paralegals with Acme on the discovery side. It saved us $380K this year."
— Maya Chen, GC at Reed Smith. From #customer-discovery, 2026-04-22.

## "We tried Tipalti for 14 months. Acme replaced it in 3 weeks."
— David Park, CFO at Lumio. From #pricing-objections, 2026-04-30.

## "The audit citations are the whole reason we trust the output."
— Sarah Wu, Controller at Greenline. From #due-diligence-prep, 2026-05-01.
"""

BOARD_LETTER = """# Q1 2026 Board Letter

Hi all,

Q1 closed at $1.4M ARR (vs. plan of $1.2M, +17%). Net retention is
138% on a 19-customer cohort that has now been on the platform for
12+ months. New logo gross margin held at 92%.

## Hires
- Joel Park (Sr. Eng, ex-Stripe)
- Mei Tanaka (Design Lead, ex-Linear)
- Two AE candidates in late-stage interviews

## Risk we're watching
Vendor.co (stealth, well-funded ex-Tesseract team) is the only
competitor we'd worry about if they shipped tomorrow. They haven't.
We have a 9-12 month head start and a real moat in the audit-citation
output format that's now embedded in 18 of 32 customers' SOC 2 reports.

## The ask
We start the Series A process in May. Target $8M at $48M post. Karri
will run point; please intro to: Sequoia (Roelof), a16z (Martin),
Founders Fund (Trae), Greylock (Sarah), Index (Mark).

— Karri
"""

ARR_FORECAST_CSV = """month,segment,new_arr,churn,net_new
2025-11,SMB,42000,3200,38800
2025-11,Mid-Market,118000,1900,116100
2025-11,Enterprise,0,0,0
2025-12,SMB,56000,3800,52200
2025-12,Mid-Market,141000,2200,138800
2025-12,Enterprise,80000,0,80000
2026-01,SMB,68000,4400,63600
2026-01,Mid-Market,164000,2700,161300
2026-01,Enterprise,120000,0,120000
2026-02,SMB,71000,5100,65900
2026-02,Mid-Market,182000,3100,178900
2026-02,Enterprise,140000,0,140000
2026-03,SMB,78000,5800,72200
2026-03,Mid-Market,210000,3400,206600
2026-03,Enterprise,180000,0,180000
2026-04,SMB,84000,6300,77700
2026-04,Mid-Market,238000,3900,234100
2026-04,Enterprise,220000,0,220000
"""

COHORT_CSV = """cohort,month_0,month_1,month_2,month_3,month_6,month_12
2024-Q4,100,98,97,95,94,113
2025-Q1,100,99,98,97,95,121
2025-Q2,100,98,98,96,98,138
2025-Q3,100,99,98,98,102,
2025-Q4,100,99,99,98,,
2026-Q1,100,99,99,,,
"""

CUSTOMER_HEALTH_CSV = """customer,segment,arr_usd,health,nps,tier
Reed Smith,Enterprise,84000,green,72,P1
Lumio,Mid-Market,38000,green,68,P1
Greenline,Mid-Market,41000,green,71,P1
Aerie Capital,Enterprise,96000,yellow,52,P0
Pickwick & Co,SMB,12000,green,80,P2
North Mill,Mid-Market,28000,red,32,P0
Quanta,Enterprise,72000,green,77,P1
Helix,SMB,9500,green,84,P3
"""

DD_RESPOND_SKILL = """---
name: dd-respond
description: Draft response packets to investor diligence asks
when_to_use: When an investor sends a DD checklist
version: 2.1
mcp_exposed: true
---

# DD-respond

You handle inbound investor diligence asks. The pattern is always:

1. Pull the canonical fact from the stash's Drive (financial model,
   board deck, customer list).
2. Cite the source in the response so the investor can verify.
3. Use the tone set in `examples.md` — short, honest, no padding.

Never invent a number. If the stash doesn't have it, say so and
flag it for the founders.

## Workflow

1. Read the investor's email — extract every distinct ask as a
   bullet.
2. For each bullet, find the source (CSV row, page in the deck,
   chat session). Use `read_file` and `grep_pages` aggressively.
3. Draft the response in `output/dd-{investor-slug}-{date}.md`.
4. Hand it to Karri or Sam to review before sending.
"""

DD_RESPOND_EXAMPLES = """# Example responses

## Q: "What's your CAC payback?"

> 11 months blended; 7 months for the inbound channel.
> See `arr_forecast.csv` rows 14-22 for the breakdown.
> Caveat: outbound is only 4 months in so we don't have a clean cohort
> on that channel yet.

## Q: "What's your churn?"

> 1.2% monthly logo churn over the last 6 months. Net retention 138%.
> Source: `customer_health.csv`. The 138% is real — driven by usage-based
> billing on volume tiers, not seat expansion.

## Q: "How concentrated is your revenue?"

> Top 5 customers = 38% of ARR. Top 10 = 61%. We disclose this on
> every first-round call. The top 5 are all multi-year contracts
> with auto-renew.
"""

DD_CHECKLIST = """# DD checklist (the canonical Series A asks)

## Financial
- [ ] ARR / MRR roll-forward
- [ ] Logo retention (monthly + cohort)
- [ ] Net retention
- [ ] Gross margin by segment
- [ ] Burn / runway / cash balance
- [ ] Cap table (FDS + post-money)
- [ ] Top 10 customer concentration

## Product
- [ ] Architecture diagram
- [ ] Security posture (SOC 2 status, pen test report)
- [ ] Roadmap next 12 months

## GTM
- [ ] Sales cycle by segment
- [ ] CAC payback
- [ ] Pipeline coverage
"""

POST_MORTEM_SKILL = """---
name: post-mortem
description: Run the standard incident post-mortem template
when_to_use: After any P0/P1 incident, within 48 hours of resolution
version: 1.0
mcp_exposed: false
---

# Post-mortem

Use the template in `template.md`. Fill it in within 48 hours.

The five required sections — non-negotiable:
- Timeline (UTC, minute granularity)
- Impact (customers affected, $$, SLA)
- Root cause (the actual one, not the proximate)
- Contributing factors
- Action items (each with an owner and a date)
"""

POST_MORTEM_TEMPLATE = """# Incident: <short title>

**Date:** YYYY-MM-DD
**Severity:** P0 | P1 | P2
**Owner:** @name
**Status:** Open | Resolved

## Timeline
- 14:02 UTC — first alert fired
- 14:05 UTC — on-call paged
- ...

## Impact

## Root cause

## Contributing factors

## Action items

| Item | Owner | Due |
|------|-------|-----|
"""

WEEKLY_RECAP_SKILL = """---
name: weekly-recap
description: Drafts the Friday update from this stash
when_to_use: Every Friday at 4pm; or anytime someone asks "what shipped this week"
version: 1.3
mcp_exposed: true
---

# Weekly recap

You write the Friday team update by reading:
- All `Sessions` from this week (Mon→Fri)
- Any `Drive` files modified in the last 7 days
- The Linear issues marked Done in the last 7 days (via MCP linear-mcp)

## Tone

Direct. No filler. One sentence per item. Group by:
1. Shipped
2. In flight (with ETA)
3. Risks / blocks
4. Next week
"""

# Synthetic transcripts (jsonl-ish text)

TRANSCRIPT_CUSTOMER_DISCOVERY = """{"type":"summary","summary":"Customer discovery call with Maya Chen, GC at Reed Smith"}
{"type":"user","content":"What's the biggest pain in your AP workflow?"}
{"type":"assistant","content":"Maya described losing 4 paralegal hours/week to invoice routing. They moved 80% of that to Acme in week 2."}
{"type":"user","content":"What was the trigger to switch from Tipalti?"}
{"type":"assistant","content":"Tipalti's audit-trail export was a manual XLS dump. SOC 2 auditors started rejecting it in 2026."}
{"type":"user","content":"Best quote to use externally?"}
{"type":"assistant","content":"Replaced 4 paralegals with Acme on the discovery side. It saved us 380K dollars this year."}
""".encode()

TRANSCRIPT_PRICING = """{"type":"summary","summary":"Pricing objection handling - David Park, CFO at Lumio"}
{"type":"user","content":"David is balking at 38K ARR. What do we do?"}
{"type":"assistant","content":"He compared us to a 9K Stampli plan. Reframe: Acme replaces 2.5 FTE-equivalent of paralegal time = 190K per year. ROI is 5x in year one."}
{"type":"user","content":"Will he sign?"}
{"type":"assistant","content":"He countered to 32K with a 12-month auto-renew. We took it."}
""".encode()

TRANSCRIPT_COMPETITOR = """{"type":"summary","summary":"Competitor teardown - Vendor.co"}
{"type":"user","content":"What do we know about Vendor.co?"}
{"type":"assistant","content":"Stealth. Founded by ex-Tesseract Greg Park + Sarah Hou. 4M seed from Bain Capital. No live customers yet (as of April 2026)."}
{"type":"user","content":"Are they a real threat?"}
{"type":"assistant","content":"In 12-18 months, yes. Right now no - they don't have the audit-citation primitive that's our SOC 2 wedge."}
""".encode()

TRANSCRIPT_DD = """{"type":"summary","summary":"DD prep with Sequoia (Roelof's team)"}
{"type":"user","content":"They want a 12-Q DD pack by Friday."}
{"type":"assistant","content":"I've drafted answers to all 12. Pulled CAC payback from arr_forecast.csv rows 14-22; net retention from customer_health.csv. Need Karri to review the pricing-power answer before send."}
""".encode()

TRANSCRIPT_MARKET = """{"type":"summary","summary":"TAM bottom-up sizing"}
{"type":"user","content":"What's the realistic 5-year TAM?"}
{"type":"assistant","content":"Mid-market AP teams in US: ~58k. ACV at scale = 25k-45k. 5yr TAM = 1.5B-2.6B. Source: U.S. Census + IBISWorld."}
""".encode()

# A real (small) PDF — minimal valid PDF
def _ascii(s: str) -> str:
    """Strip non-latin1 chars (em-dash, smart quotes) so they fit in a tiny PDF."""
    return (
        s.replace("—", "-")
        .replace("–", "-")
        .replace("'", "'")
        .replace("'", "'")
        .replace(""", '"')
        .replace(""", '"')
        .encode("latin1", errors="ignore")
        .decode("latin1")
    )


def _minimal_pdf(title: str, body: str) -> bytes:
    """Build a tiny valid PDF with the title + a few body lines."""
    title = _ascii(title)
    body = _ascii(body)
    text = body.replace("(", "[").replace(")", "]")
    content_stream = f"BT /F1 24 Tf 50 720 Td ({title}) Tj ET\n"
    y = 690
    for line in text.splitlines()[:40]:
        line = line[:90].replace("\\", "/")
        content_stream += f"BT /F1 11 Tf 50 {y} Td ({line}) Tj ET\n"
        y -= 14
    stream_len = len(content_stream)
    pdf = (
        "%PDF-1.4\n"
        "1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n"
        "2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj\n"
        "3 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Resources <</Font <</F1 5 0 R>>>> /Contents 4 0 R>> endobj\n"
        f"4 0 obj <</Length {stream_len}>>\nstream\n{content_stream}endstream\nendobj\n"
        "5 0 obj <</Type /Font /Subtype /Type1 /BaseFont /Helvetica>> endobj\n"
        "xref\n0 6\n0000000000 65535 f \n"
        "trailer <</Size 6 /Root 1 0 R>>\n"
        "startxref\n0\n%%EOF\n"
    )
    return pdf.encode("latin1")


# ---------------------------------------------------------------------------
# Seed driver
# ---------------------------------------------------------------------------


async def main() -> None:
    if not storage_service.is_configured():
        print(
            "⚠ S3 not configured (set S3_ENDPOINT/S3_BUCKET/S3_ACCESS_KEY/S3_SECRET_KEY).\n"
            "  Files will get placeholder storage keys; download URLs will fail.\n"
        )

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        async with conn.transaction():
            await _seed(conn)
    finally:
        await conn.close()


async def _seed(conn: asyncpg.Connection) -> None:
    print("→ wiping previous demo state")
    await conn.execute("DELETE FROM share_links WHERE workspace_id IN ($1, $2)", STASH_ID, STASH2_ID)
    await conn.execute("DELETE FROM workspaces WHERE id IN ($1, $2)", STASH_ID, STASH2_ID)

    # ─── Stash 1: Acme Series A ────────────────────────────────────────
    print("→ creating stash: Acme Series A — Investor Diligence")
    await _create_stash(
        conn,
        stash_id=STASH_ID,
        name="Acme Series A — Investor Diligence",
        description=(
            "All the artifacts we share with potential Series A leads. Decks, "
            "financial model, customer references, and the agent skills that "
            "draft our diligence responses."
        ),
        summary="Series A diligence stash — pitch deck, financials, customer references.",
        tags=["fundraise", "series-a", "demo"],
        category="fundraising",
        is_public=False,
    )

    print("→ creating skills folders")
    await _create_skill(
        conn,
        stash_id=STASH_ID,
        folder_name="dd-respond",
        files={
            "SKILL.md": DD_RESPOND_SKILL,
            "examples.md": DD_RESPOND_EXAMPLES,
            "dd-checklist.md": DD_CHECKLIST,
        },
    )
    await _create_skill(
        conn,
        stash_id=STASH_ID,
        folder_name="weekly-recap",
        files={"SKILL.md": WEEKLY_RECAP_SKILL},
    )
    await _create_skill(
        conn,
        stash_id=STASH_ID,
        folder_name="post-mortem",
        files={"SKILL.md": POST_MORTEM_SKILL, "template.md": POST_MORTEM_TEMPLATE},
    )

    print("→ creating wiki pages (narrative + memos)")
    await _create_page(
        conn, STASH_ID, "Narrative.md", NARRATIVE_DECK, public_in_share=True
    )
    await _create_page(conn, STASH_ID, "Investor FAQ.md", INVESTOR_FAQ, public_in_share=True)
    await _create_page(conn, STASH_ID, "Customer Q&A.md", CUSTOMER_QA, public_in_share=True)
    await _create_page(conn, STASH_ID, "Q1 Board Letter.md", BOARD_LETTER, public_in_share=False)

    print("→ creating session transcripts (with real S3 uploads if configured)")
    sessions = [
        ("acme-customer-discovery-2026-04-22", "claude-opus", TRANSCRIPT_CUSTOMER_DISCOVERY),
        ("acme-pricing-objections-2026-04-30", "claude-sonnet", TRANSCRIPT_PRICING),
        ("acme-competitor-teardown-2026-04-15", "gemini-2-pro", TRANSCRIPT_COMPETITOR),
        ("acme-due-diligence-prep-2026-05-01", "claude-opus", TRANSCRIPT_DD),
        ("acme-market-sizing-2026-04-08", "gpt-5", TRANSCRIPT_MARKET),
    ]
    for sess_id, agent, transcript in sessions:
        await _create_transcript(conn, STASH_ID, sess_id, agent, transcript)

    print("→ creating drive files (with real S3 uploads if configured)")
    files = [
        ("arr_forecast.csv", "text/csv", ARR_FORECAST_CSV.encode(), True),
        ("cohort_retention.csv", "text/csv", COHORT_CSV.encode(), False),
        ("customer_health.csv", "text/csv", CUSTOMER_HEALTH_CSV.encode(), False),
        (
            "unit_economics.pdf",
            "application/pdf",
            _minimal_pdf("Unit Economics", "CAC payback: 11 months blended.\nGross margin: 92%.\nNRR: 138%."),
            True,
        ),
        (
            "acme_pitch_2026.pdf",
            "application/pdf",
            _minimal_pdf("Acme Pitch — Q4 2026", "Acme reinvents AP for the mid-market."),
            True,
        ),
        (
            "growth_dashboard.html",
            "text/html",
            b"<html><body><h1>Acme Growth Dashboard</h1><p>Q1 2026 ARR: $1.4M</p></body></html>",
            False,
        ),
    ]
    for name, ct, content, public in files:
        await _create_file(conn, STASH_ID, name, ct, content, public)

    print("→ creating active share link")
    token = await _create_share(conn, STASH_ID, ttl_days=14)
    print(f"   share URL: http://localhost:3000/share/{token}")

    # ─── Stash 2: Engineering ─────────────────────────────────────────────
    print("→ creating stash: Acme Engineering")
    await _create_stash(
        conn,
        stash_id=STASH2_ID,
        name="Acme Engineering",
        description="Architecture, runbooks, and the on-call playbook.",
        summary="Eng team's shared brain — architecture, runbooks, post-mortems.",
        tags=["engineering", "runbooks"],
        category="engineering",
        is_public=False,
    )
    await _create_skill(
        conn,
        stash_id=STASH2_ID,
        folder_name="oncall-runbook",
        files={
            "SKILL.md": (
                "---\n"
                "name: oncall-runbook\n"
                "description: Diagnose a P0/P1 alert, page the right human, fix or escalate\n"
                "when_to_use: When PagerDuty fires for the API or worker tier\n"
                "version: 3.4\n"
                "mcp_exposed: true\n"
                "---\n\n"
                "# On-call runbook\n\n"
                "Step 1: Read the alert. Figure out which tier (api / worker / db).\n"
                "Step 2: Check the dashboard at https://grafana.acme.io.\n"
                "Step 3: If it's a known issue (see `known-issues.md`) follow the fix.\n"
                "Step 4: Otherwise page the tier owner and start a war room.\n"
            ),
            "known-issues.md": (
                "# Known issues\n\n"
                "## API 503 spikes\n"
                "Usually a deploy-time cold start. Wait 90s, re-check.\n\n"
                "## Worker queue depth > 5000\n"
                "Scale up the worker fleet via `kubectl scale deploy/workers --replicas=8`.\n"
            ),
        },
    )
    await _create_page(
        conn,
        STASH2_ID,
        "Architecture.md",
        "# Acme architecture\n\n"
        "- **API**: Go, hosted on Fly.io\n"
        "- **Workers**: Python, Celery + Redis\n"
        "- **DB**: Postgres 16 (Crunchy Bridge)\n"
        "- **Object storage**: Cloudflare R2\n",
        public_in_share=False,
    )
    for name, ct, content in [
        ("api-uptime.csv", "text/csv", b"month,uptime_pct\n2026-01,99.94\n2026-02,99.97\n2026-03,99.99\n2026-04,99.96\n"),
        ("post-mortem-2026-03-12.md", "text/markdown", b"# P0: API 5xx storm 2026-03-12\n\nRoot cause: bad cache key collision.\n"),
    ]:
        await _create_file(conn, STASH2_ID, name, ct, content, public_in_share=False)
    for sess_id, agent, transcript in [
        ("eng-deploy-debug-2026-04-29", "claude-opus", b'{"type":"summary","summary":"Deploy debug session"}\n'),
        ("eng-perf-tuning-2026-04-21", "claude-sonnet", b'{"type":"summary","summary":"Perf tuning session"}\n'),
    ]:
        await _create_transcript(conn, STASH2_ID, sess_id, agent, transcript)

    print("\n✓ Seed complete.")
    print(f"  Stash 1 (Acme Series A): http://localhost:3000/stashes/{STASH_ID}")
    print(f"  Stash 2 (Engineering):   http://localhost:3000/stashes/{STASH2_ID}")
    print(f"  Sender:                  sam (password: password)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_stash(
    conn: asyncpg.Connection,
    *,
    stash_id: UUID,
    name: str,
    description: str,
    summary: str,
    tags: list[str],
    category: str,
    is_public: bool,
) -> None:
    await conn.execute(
        "INSERT INTO workspaces (id, name, description, summary, creator_id, "
        "invite_code, is_public, tags, category) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
        stash_id,
        name,
        description,
        summary,
        SAM_ID,
        secrets.token_hex(4)[:12],
        is_public,
        tags,
        category,
    )
    await conn.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) "
        "VALUES ($1, $2, 'owner') ON CONFLICT DO NOTHING",
        stash_id,
        SAM_ID,
    )
    await conn.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) "
        "VALUES ($1, $2, 'admin') ON CONFLICT DO NOTHING",
        stash_id,
        HENRY_ID,
    )


async def _create_skill(
    conn: asyncpg.Connection,
    *,
    stash_id: UUID,
    folder_name: str,
    files: dict[str, str],
) -> None:
    folder_id = uuid4()
    await conn.execute(
        "INSERT INTO folders (id, workspace_id, parent_folder_id, name, created_by) "
        "VALUES ($1, $2, NULL, $3, $4)",
        folder_id,
        stash_id,
        folder_name,
        SAM_ID,
    )
    for fname, body in files.items():
        await _insert_page(conn, stash_id, folder_id, fname, body, public_in_share=False)


async def _create_page(
    conn: asyncpg.Connection,
    stash_id: UUID,
    name: str,
    body: str,
    *,
    public_in_share: bool,
) -> None:
    await _insert_page(conn, stash_id, None, name, body, public_in_share=public_in_share)


async def _insert_page(
    conn: asyncpg.Connection,
    stash_id: UUID,
    folder_id: UUID | None,
    name: str,
    body: str,
    *,
    public_in_share: bool,
) -> None:
    page_id = uuid4()
    content_hash = hashlib.sha256(body.encode()).hexdigest()
    await conn.execute(
        "INSERT INTO pages "
        "(id, workspace_id, folder_id, name, content_markdown, content_html, "
        " content_type, content_hash, metadata, created_by, updated_by, public_in_share) "
        "VALUES ($1, $2, $3, $4, $5, '', 'markdown', $6, '{}'::jsonb, $7, $7, $8)",
        page_id,
        stash_id,
        folder_id,
        name,
        body,
        content_hash,
        SAM_ID,
        public_in_share,
    )


async def _create_transcript(
    conn: asyncpg.Connection,
    stash_id: UUID,
    session_id: str,
    agent_name: str,
    content: bytes,
) -> None:
    storage_key = f"local/seed/{session_id}.jsonl"
    if storage_service.is_configured():
        try:
            storage_key = await storage_service.upload_file(
                str(stash_id), f"{session_id}.jsonl", content, "application/jsonl"
            )
        except Exception as e:
            print(f"  ⚠ failed to upload transcript {session_id}: {e}")

    await conn.execute(
        "INSERT INTO session_transcripts "
        "(workspace_id, session_id, agent_name, storage_key, size_bytes, cwd, uploaded_by) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7) "
        "ON CONFLICT (workspace_id, session_id) DO NOTHING",
        stash_id,
        session_id,
        agent_name,
        storage_key,
        len(content),
        "/Users/sam/code/acme",
        SAM_ID,
    )


async def _create_file(
    conn: asyncpg.Connection,
    stash_id: UUID,
    name: str,
    content_type: str,
    content: bytes,
    public_in_share: bool,
) -> None:
    storage_key = f"local/seed/{name}"
    if storage_service.is_configured():
        try:
            storage_key = await storage_service.upload_file(
                str(stash_id), name, content, content_type
            )
        except Exception as e:
            print(f"  ⚠ failed to upload {name}: {e}")

    extracted_text = ""
    if content_type.startswith("text/"):
        try:
            extracted_text = content.decode("utf-8")[:8000]
        except UnicodeDecodeError:
            pass

    await conn.execute(
        "INSERT INTO files "
        "(id, workspace_id, name, content_type, size_bytes, storage_key, uploaded_by, "
        " extracted_text, public_in_share) "
        "VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8)",
        stash_id,
        name,
        content_type,
        len(content),
        storage_key,
        SAM_ID,
        extracted_text,
        public_in_share,
    )


async def _create_share(
    conn: asyncpg.Connection, stash_id: UUID, *, ttl_days: int
) -> str:
    token = secrets.token_urlsafe(16)
    await conn.execute(
        "INSERT INTO share_links (token, workspace_id, created_by, expires_at, permission) "
        "VALUES ($1, $2, $3, $4, 'view')",
        token,
        stash_id,
        SAM_ID,
        NOW + timedelta(days=ttl_days),
    )
    return token


if __name__ == "__main__":
    asyncio.run(main())
