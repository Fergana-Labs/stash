"""Telegram agent behavior: DM vs group, mention detection, connect flow."""

import pytest

from backend.config import settings
from backend.integrations.telegram import agent


def _msg(text, chat_type="private", **extra):
    m = {"message_id": 5, "text": text, "from": {"id": 42, "is_bot": False},
         "chat": {"id": 100, "type": chat_type}}
    m.update(extra)
    return m


def test_text_and_mention_in_group(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_USERNAME", "StashBot")
    body, addressed = agent._text_and_mention(_msg("@StashBot what's up"), "StashBot")
    assert body == "what's up" and addressed is True

    body, addressed = agent._text_and_mention(_msg("just chatting"), "StashBot")
    assert addressed is False


def test_reply_to_bot_counts_as_addressed():
    m = _msg("thanks", reply_to_message={"from": {"is_bot": True}})
    _, addressed = agent._text_and_mention(m, "StashBot")
    assert addressed is True


def test_session_id_dm_vs_group():
    assert agent._session_id("u1", _msg("hi"), True) == "telegram-agent-u1-dm"
    grp = agent._session_id("u1", _msg("hi", chat_type="group", message_thread_id=9), False)
    assert grp == "telegram-agent-u1-t-9"


@pytest.mark.asyncio
async def test_group_message_ignored_unless_addressed(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_USERNAME", "StashBot")
    calls = []

    async def fake_send(chat_id, text, **kw):
        calls.append(text)

    monkeypatch.setattr(agent.client, "send_message", fake_send)
    # Unaddressed group text → no reply, no lookup.
    await agent.respond_to_message(_msg("random group chatter", chat_type="group"))
    assert calls == []


@pytest.mark.asyncio
async def test_unlinked_dm_gets_connect_prompt(monkeypatch):
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append(text)

    async def no_link(_tid):
        return None

    monkeypatch.setattr(agent.client, "send_message", fake_send)
    monkeypatch.setattr(agent.links, "get_linked_user_id", no_link)
    await agent.respond_to_message(_msg("hello"))
    assert sent and "connect Telegram" in sent[0]


@pytest.mark.asyncio
async def test_start_with_code_links_account(monkeypatch):
    sent = []
    redeemed = {}

    async def fake_send(chat_id, text, **kw):
        sent.append(text)

    async def fake_redeem(code, tg_id):
        redeemed["code"] = code
        redeemed["tg"] = tg_id
        return "user-uuid"

    async def fake_get_user(uid):
        return {"display_name": "Sam", "name": "sam"}

    monkeypatch.setattr(agent.client, "send_message", fake_send)
    monkeypatch.setattr(agent.links, "redeem_connect_code", fake_redeem)
    monkeypatch.setattr(agent.user_service, "get_user_by_id", fake_get_user)
    await agent.respond_to_message(_msg("/start abc123"))
    assert redeemed == {"code": "abc123", "tg": "42"}
    assert sent and "Connected" in sent[0] and "Sam" in sent[0]


@pytest.mark.asyncio
async def test_bot_messages_ignored(monkeypatch):
    called = []
    monkeypatch.setattr(agent.client, "send_message",
                        lambda *a, **k: called.append(1))
    m = _msg("hi")
    m["from"]["is_bot"] = True
    await agent.respond_to_message(m)
    assert called == []


@pytest.mark.asyncio
async def test_free_user_gets_upgrade_prompt(monkeypatch):
    sent = []

    async def fake_send(chat_id, text, **kw):
        sent.append(text)

    async def linked(_tid):
        return "user-uuid"

    async def get_user(_uid):
        return {"display_name": "Sam", "name": "sam"}

    async def needs_auth(*a, **k):
        raise agent.sprite_agent_service.NeedsAuth

    monkeypatch.setattr(agent.client, "send_message", fake_send)
    monkeypatch.setattr(agent.links, "get_linked_user_id", linked)
    monkeypatch.setattr(agent.user_service, "get_user_by_id", get_user)
    monkeypatch.setattr(agent.sprite_agent_service, "run_chat", needs_auth)
    await agent.respond_to_message(_msg("do something"))
    assert sent and "upgrade to Pro" in sent[0]
