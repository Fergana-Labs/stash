"""Public marketing-events router.

Anonymous, IP rate-limited beacons from the www landing pages: one event
per painted-door page view and one per signup, so the messaging test can
be scored from our own data (views and signups per variant) instead of
relying on X's dashboards. Rows land in analytics_events.
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..database import get_pool
from ..middleware import limiter
from ..services import analytics_events_service
from ..services.llm import ModelTier, complete_chat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/marketing", tags=["marketing"])

_POST_LIMIT = "60/minute"
_GET_LIMIT = "30/minute"
_CHAT_LIMIT = "30/minute"

_KINDS = {"view", "signup"}
_VARIANTS = {"drive", "wiki", "connect", "assistant"}


class MarketingEvent(BaseModel):
    kind: str = Field(..., pattern=r"^(view|signup)$")
    variant: str = Field(..., min_length=1, max_length=32)
    url: str = Field("", max_length=2048)
    referrer: str = Field("", max_length=2048)


@router.post("/events", status_code=204)
@limiter.limit(_POST_LIMIT)
async def record_marketing_event(request: Request, event: MarketingEvent) -> None:
    # Unknown variants are dropped silently — this is a public endpoint and
    # garbage input shouldn't pollute the test counts or surface errors.
    if event.variant not in _VARIANTS:
        return
    await analytics_events_service.record_event(
        user_id=None,
        surface="marketing",
        event_name=f"marketing.{event.kind}",
        properties={
            "variant": event.variant,
            "url": event.url,
            "referrer": event.referrer,
        },
    )


# The /smb landing page's interview chat. Public and anonymous by design —
# the model produces the lead-qualifying snapshot report; contact capture and
# lead email stay in the www app. Strict JSON replies let the page render
# quick-reply chips and the final report.
_SMB_CHAT_SYSTEM = """You are running a free "AI Opportunity Snapshot" interview with a small-business owner on the Stash website (joinstash.ai). Stash organizes a business's scattered knowledge into one system any AI can use. The interview qualifies them and produces a one-page report. A human from Stash follows up afterward.

VOICE — non-negotiable:
- Plain spoken, short sentences, zero jargon. Never say: leverage, streamline, cutting-edge, revolutionize, AI-powered, LLM.
- Warm, direct, curious — like a helpful local person, not a marketing funnel.
- Talk in hours and dollars, using THEIR numbers. Never invent a number they didn't give you.
- One question per turn. Brief acknowledgment of their previous answer first when natural.
- If they ask something off-topic, answer briefly and steer back to the interview.
- Never ask for sensitive data (client names, financials, health data). If they volunteer specifics, generalize them.

INTERVIEW — cover these, in roughly this order, adapting wording to what they've said and skipping anything already answered:
1. What kind of business (offer options: professional services, agency/creative, home services/trades, healthcare/wellness, retail/e-commerce, other)
2. Team size (Just me / 2-5 / 6-20 / 21+)
3. Where business knowledge lives today (one organized system / Google Drive + spreadsheets / scattered across 3+ tools / email threads and my head)
4. What eats the most hours weekly (writing / scheduling & follow-ups / invoicing & admin / answering repeat customer questions / finding information they already have)
5. Roughly how many hours a week that costs (<3 / 3-5 / 5-10 / 10+)
6. Whether they could find WHY a big decision was made 3 months ago (written down / buried in email / in my head / honestly no)
7. How much is in flight tracked only in their head (almost nothing / a few things / more than I'd like to admit)
8. Their #1 business goal this year — THE SPINE. Free text. Everything in the report must ladder to it.
9. What an hour of their time is worth (<$50 / $50-100 / $100-250 / $250+)
10. When they'd want to act if the numbers made sense (this month / this quarter / just exploring)

OUTPUT FORMAT — every reply must be PURE JSON, no markdown, no text outside the JSON object:
{"message": "<what you say>", "options": ["<chip>", ...], "done": false}
- "options": include ONLY when multiple-choice chips genuinely help (use the option sets above). Omit for free-text questions.
- Keep "message" under 60 words.

FINAL TURN — after question 10, reply with:
{"message": "<one-line wrap-up asking for their name, email, and business name for the report>", "done": true, "report": {
  "business_type": "...", "goal": "<their exact goal>",
  "score": <0-100: start 40; +15 knowledge in one organized system; +15 they already use AI (ChatGPT or an agent); +15 clear single time sink; +15 the sink costs 5+ hrs/week>,
  "tier": "<QUALIFIED if (team 2+ AND 5+ hrs lost AND acting this month/quarter AND hourly value $100+), NURTURE if some of those, EARLY otherwise>",
  "hours_week": <conservative reclaimable hours: at most half their stated weekly hours, +1 if knowledge is scattered>,
  "value_month": <hours_week x their hourly-value midpoint (35/75/175/300) x 4.3, rounded down>,
  "findings": [
    {"title": "<their #1 time sink>", "before": "<'You said...' with their hours>", "after": "<the fix in plain words>", "hours": "<e.g. ~3 hrs/week back>"},
    {"title": "...", "before": "...", "after": "...", "hours": "..."},
    {"title": "...", "before": "...", "after": "...", "hours": "..."}
  ],
  "tool": {"name": "...", "why": "<one sentence, for THEIR case>", "cost": "...", "setup": "..."}
}}
- Finding 1 = their time sink. Include a decisions/open-loops finding if those live in their head. Include a scattered-knowledge finding if knowledge is scattered. Every finding's "after" should visibly serve their goal.
- "tool": pick exactly ONE from this list (real current pricing): Claude ($20/mo, ~1 hour setup) for writing; Calendly ($12/mo, ~30 min) for scheduling; FreshBooks ($21/mo, ~2 hours) for invoicing/admin; Chatbase ($40/mo, ~2 hours) for repeat customer questions; Stash (free to start, ~30 min) for finding information they already have."""


class SmbChatMessage(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=600)


class SmbChatRequest(BaseModel):
    messages: list[SmbChatMessage] = Field(..., min_length=1, max_length=40)


@router.post("/smb-chat")
@limiter.limit(_CHAT_LIMIT)
async def smb_chat(request: Request, body: SmbChatRequest) -> dict:
    text = await complete_chat(
        messages=[m.model_dump() for m in body.messages],
        system=_SMB_CHAT_SYSTEM,
        tier=ModelTier.FAST,
        max_tokens=1200,
    )
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        logger.error("smb-chat model reply was not JSON: %s", text[:200])
        raise HTTPException(status_code=502, detail="Chat is having trouble.")
    raw = text[start : end + 1]
    try:
        reply = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("smb-chat model reply failed to parse: %s", text[:200])
        raise HTTPException(status_code=502, detail="Chat is having trouble.") from None
    return {"reply": reply, "raw": raw}


@router.get("/summary")
@limiter.limit(_GET_LIMIT)
async def marketing_summary(request: Request) -> dict:
    """Views and signups per variant — aggregate counts only."""
    pool = get_pool()
    rows = await pool.fetch("""
        SELECT properties->>'variant' AS variant,
               event_name,
               count(*) AS n
        FROM analytics_events
        WHERE surface = 'marketing'
        GROUP BY 1, 2
        """)
    summary: dict[str, dict[str, int]] = {v: {"views": 0, "signups": 0} for v in sorted(_VARIANTS)}
    for r in rows:
        variant = r["variant"]
        if variant not in summary:
            continue
        key = "views" if r["event_name"] == "marketing.view" else "signups"
        summary[variant][key] = r["n"]
    return summary
