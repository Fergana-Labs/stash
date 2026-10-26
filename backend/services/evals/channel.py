"""An eval's channel: people drop in examples and say what they think, Slack-style, and an
agent turns that into labeled evidence, asking in threads when it can't tell.

Each file posted becomes an example (intuition_examples.message_id), unlabeled until the
person's words decide. After a post, the channel agent (run) reads the new messages with
their files and returns one structured update: labels for attachments, thread replies
(questions, with quick-reply choices), a rewritten description when the person says what
the eval is for, and rubric change requests for the next build. New labels queue a build
(service.request_build), so the rubric keeps up with the evidence; the build posts what
changed back here (build.announce). One agent reads a channel at a time
(intuition_models.channel_busy_since); one that finds the channel taken leaves the new
messages to the agent already reading it.
"""

import asyncio
import json
import logging
import re
import time
from uuid import UUID

from ...database import get_pool
from .. import llm
from . import items, service, versions

log = logging.getLogger(__name__)

MAX_TEXT = 8000
MAX_MESSAGES = 400  # listed, and read for context
HISTORY = 60  # earlier messages the agent reads as text
MAX_BATCH = 12  # new messages the agent reads at once
MAX_IMAGES = 40  # attachments shown to the agent as files per call
RUN_SECONDS = 60  # one task reads for about this long, then hands the rest to another
CALL_TIMEOUT = 120  # seconds per Claude call: well inside the task's time limit

SYSTEM = """You run the channel where a person teaches an eval what good work by their AI \
agent looks like. They drop in examples (screenshots, files, agent output), often many at \
once, and say what they think in a few words. Each attachment you label becomes an example an \
AI judge learns from; the eval's rubric is rewritten from the examples automatically and \
posted in the channel.

For the new messages:
1. Label attachments from the person's words: good or bad, with their reason in their own \
words ("" when they gave none). "These are all bad" labels every attachment in that message \
bad; "the second one is fine" labels that one good; an answer in a thread applies to the \
attachments that thread is about. Their words decide: never label from how the work looks, \
and don't relabel what they already labeled unless they say so.
2. Ask when you can't tell whether attachments are good or bad, or which ones their words are \
about. Ask in that message's thread: one short question per message, never one per file, with \
choices when the answer is one of a few, such as ["All good", "All bad"].
3. When they say what the eval is for, rewrite the description: one or two sentences in \
their terms that keep what still holds.
4. When they state a standing preference ("never use gradients") or ask to change the rubric \
itself ("drop the color trait", "be stricter about spacing"), pass it on as a rubric request \
in their words.
5. Reply only when it helps: a question, an answer to their question, or a confirmation they \
asked for. Don't acknowledge drops; labels show up on the attachments.
Replies are one or two short sentences in plain words.

Return only JSON: {"labels": [{"attachments": [ids such as "A3", or "M2/all" for every \
attachment in M2], "label": "good" | "bad", "reason": str}], "replies": [{"message": "M2", \
"text": str, "choices": [str] (0-4)}], "description": str or null, "rubric_request": str or \
null, "name": str or null (only while the eval is untitled: 2-5 words for what it judges)}"""


# ── Messages ─────────────────────────────────────────────────────────────


def _file(item) -> dict:
    item = item if isinstance(item, dict) else json.loads(item)
    f = (item.get("files") or [{}])[0]
    return {
        "name": f.get("name") or item.get("name") or "",
        "content_type": f.get("content_type", ""),
    }


def _attachment(row) -> dict:
    return {
        "example_id": row["id"],
        **_file(row["item"]),
        "label": row["label"],
        "note": row["note"],
        "held_out": row["split"] == "eval",
    }


async def _render(model_id: UUID, rows: list) -> list[dict]:
    ids = [r["id"] for r in rows]
    about = [UUID(r["data"]["about"]) for r in rows if (r["data"] or {}).get("about")]
    examples = await get_pool().fetch(
        """SELECT id, message_id, item, label, note, split FROM intuition_examples
           WHERE model_id=$1 AND (message_id = ANY($2::uuid[]) OR id = ANY($3::uuid[]))
           ORDER BY created_at""",
        model_id,
        ids,
        about,
    )
    by_message: dict[UUID, list[dict]] = {}
    by_id = {}
    for e in examples:
        by_id[e["id"]] = _attachment(e)
        if e["message_id"]:
            by_message.setdefault(e["message_id"], []).append(by_id[e["id"]])
    out = []
    for r in rows:
        data = r["data"] or {}
        out.append(
            {
                "id": r["id"],
                "thread_id": r["thread_id"],
                "author": r["author"],
                "kind": r["kind"],
                "text": r["text"],
                "data": data,
                "attachments": by_message.get(r["id"], []),
                "about": by_id.get(UUID(data["about"])) if data.get("about") else None,
                "created_at": r["created_at"],
            }
        )
    return out


async def listing(owner: UUID, eval_id: UUID) -> dict:
    await service._owned(owner, eval_id)
    rows = await get_pool().fetch(
        """SELECT * FROM (SELECT * FROM eval_messages WHERE model_id=$1
           ORDER BY created_at DESC LIMIT $2) recent ORDER BY created_at""",
        eval_id,
        MAX_MESSAGES,
    )
    busy = await get_pool().fetchval(
        f"""SELECT EXISTS (
                SELECT 1 FROM intuition_models WHERE id=$1
                AND channel_busy_since > now() - interval '{service.READ_TIMEOUT}'
            ) OR EXISTS (
                SELECT 1 FROM eval_messages WHERE model_id=$1 AND author='user'
                AND handled_at IS NULL AND NOT data ? 'uploading'
                AND created_at > now() - interval '{service.READ_TIMEOUT}'
            )""",
        eval_id,
    )
    return {"messages": await _render(eval_id, rows), "busy": busy}


async def _store(
    owner: UUID, eval_id: UUID, files: list[tuple[str, bytes, str]]
) -> tuple[list, list]:
    """(stored items, skipped files): every readable file is stored; one that can't be read is
    reported with why, instead of failing the whole drop."""
    have = await get_pool().fetchval(
        "SELECT count(*) FROM intuition_examples WHERE model_id=$1", eval_id
    )
    if have + len(files) > service.MAX_EXAMPLES:
        raise ValueError(f"An eval holds at most {service.MAX_EXAMPLES} examples")
    results = await asyncio.gather(
        *(items.store(owner, name, [(name, data, ctype)]) for name, data, ctype in files),
        return_exceptions=True,
    )
    stored, skipped = [], []
    for (name, _, _), result in zip(files, results, strict=True):
        if isinstance(result, ValueError):  # items.Unreadable: the person sees why
            skipped.append({"name": name, "error": str(result)})
        elif isinstance(result, BaseException):
            raise result
        else:
            stored.append(result)
    return stored, skipped


async def _attach(conn, eval_id: UUID, message_id: UUID, stored: list[dict]) -> None:
    have = await conn.fetchval("SELECT count(*) FROM intuition_examples WHERE model_id=$1", eval_id)
    for item, split in zip(stored, service.splits(have, len(stored)), strict=True):
        await conn.execute(
            """INSERT INTO intuition_examples
               (model_id, kind, item, label, source, split, needs_review, message_id, created_at)
               VALUES ($1, 'item', $2, NULL, 'human', $3, true, $4, clock_timestamp())""",
            eval_id,
            item,
            split,
            message_id,
        )
    await conn.execute("UPDATE intuition_models SET updated_at=now() WHERE id=$1", eval_id)


async def post(
    owner: UUID,
    eval_id: UUID,
    text: str,
    files: list[tuple[str, bytes, str]],
    thread_id: UUID | None = None,
    more: bool = False,
) -> dict:
    """Post the person's message; each readable file becomes an unlabeled example. With more,
    further files follow (attach) and the agent waits for the last of them."""
    from ...tasks import evals as eval_tasks

    await service._owned(owner, eval_id)
    text = text.strip()[:MAX_TEXT]
    if not text and not files:
        raise ValueError("Write something or attach a file")
    if thread_id is not None:
        parent = await get_pool().fetchrow(
            "SELECT id, thread_id FROM eval_messages WHERE id=$1 AND model_id=$2",
            thread_id,
            eval_id,
        )
        if parent is None:
            raise service.NotFound("Thread not found")
        thread_id = parent["thread_id"] or parent["id"]
    stored, skipped = await _store(owner, eval_id, files)
    if not text and not stored and not more:
        raise ValueError(skipped[0]["error"])
    async with get_pool().acquire() as conn, conn.transaction():
        message = await conn.fetchrow(
            """INSERT INTO eval_messages (model_id, thread_id, author, text, data)
               VALUES ($1, $2, 'user', $3, $4) RETURNING *""",
            eval_id,
            thread_id,
            text,
            {"uploading": True} if more else {},
        )
        await _attach(conn, eval_id, message["id"], stored)
    if not more:
        eval_tasks.read_channel.delay(str(eval_id))
    return {"message": (await _render(eval_id, [message]))[0], "skipped": skipped}


async def attach(
    owner: UUID, eval_id: UUID, message_id: UUID, files: list[tuple[str, bytes, str]], more: bool
) -> dict:
    """More files for a message posted with more; the last call hands it to the agent."""
    from ...tasks import evals as eval_tasks

    await service._owned(owner, eval_id)
    message = await get_pool().fetchrow(
        """SELECT * FROM eval_messages WHERE id=$1 AND model_id=$2 AND author='user'
           AND data ? 'uploading' AND handled_at IS NULL""",
        message_id,
        eval_id,
    )
    if message is None:
        raise service.NotFound("No upload in progress for this message")
    stored, skipped = await _store(owner, eval_id, files)
    async with get_pool().acquire() as conn, conn.transaction():
        await _attach(conn, eval_id, message_id, stored)
        if not more:
            message = await conn.fetchrow(
                "UPDATE eval_messages SET data = data - 'uploading' WHERE id=$1 RETURNING *",
                message_id,
            )
    if not more:
        eval_tasks.read_channel.delay(str(eval_id))
    return {"message": (await _render(eval_id, [message]))[0], "skipped": skipped}


async def post_agent(
    model_id: UUID,
    text: str,
    *,
    thread_id: UUID | None = None,
    kind: str = "message",
    data: dict | None = None,
) -> None:
    await get_pool().execute(
        """INSERT INTO eval_messages (model_id, thread_id, author, kind, text, data, handled_at)
           VALUES ($1, $2, 'agent', $3, $4, $5, now())""",
        model_id,
        thread_id,
        kind,
        text[:MAX_TEXT],
        data or {},
    )


# ── The agent ────────────────────────────────────────────────────────────


async def _claim(model_id: UUID) -> bool:
    return (
        await get_pool().fetchval(
            f"""UPDATE intuition_models SET channel_busy_since=now()
                WHERE id=$1 AND (channel_busy_since IS NULL
                                 OR channel_busy_since < now() - interval '{service.READ_TIMEOUT}')
                RETURNING true""",
            model_id,
        )
        is not None
    )


async def _release(model_id: UUID) -> None:
    await get_pool().execute(
        "UPDATE intuition_models SET channel_busy_since=NULL WHERE id=$1", model_id
    )


async def _unhandled(model_id: UUID, limit: int) -> list:
    """New messages, oldest first. A drop still uploading waits, unless its upload was abandoned."""
    return await get_pool().fetch(
        f"""SELECT * FROM eval_messages WHERE model_id=$1 AND author='user' AND handled_at IS NULL
              AND (NOT data ? 'uploading' OR created_at < now() - interval '{service.READ_TIMEOUT}')
            ORDER BY created_at LIMIT $2""",
        model_id,
        limit,
    )


async def run(model_id: UUID) -> None:
    """Read the channel's new messages until there are none. Releasing and checking again
    closes the gap where a message lands just as the agent finishes."""
    from ...tasks import evals as eval_tasks

    started = time.monotonic()
    while await _claim(model_id):
        try:
            while batch := await _unhandled(model_id, MAX_BATCH):
                await _handle(model_id, batch)
                if time.monotonic() - started > RUN_SECONDS:
                    break
        finally:
            await _release(model_id)
        if not await _unhandled(model_id, 1):
            return
        if time.monotonic() - started > RUN_SECONDS:
            # Long drops are read by a fresh task so this one never holds a worker for minutes.
            eval_tasks.read_channel.delay(str(model_id))
            return


async def _handle(model_id: UUID, batch: list) -> None:
    try:
        context = await _context(model_id, batch)
        reply = await llm._get_client().messages.create(
            model=llm._model_for(llm.ModelTier.QUALITY),
            max_tokens=3000,
            system=SYSTEM,
            messages=[{"role": "user", "content": context["content"]}],
            timeout=CALL_TIMEOUT,
        )
        update = parse("".join(b.text for b in reply.content if b.type == "text"))
        await _apply(model_id, context, update)
    except Exception:
        log.exception("Eval channel agent failed for %s", model_id)
        last = batch[-1]
        await post_agent(
            model_id,
            "I couldn't read that just now. Label the attachments with the buttons on them, "
            "or send your message again.",
            thread_id=last["thread_id"] or last["id"],
        )
    finally:
        # Read: an abandoned upload is closed with whatever arrived, and takes no more files.
        await get_pool().execute(
            """UPDATE eval_messages SET handled_at=now(), data = data - 'uploading'
               WHERE id = ANY($1::uuid[])""",
            [m["id"] for m in batch],
        )


def _who(row, alias: dict, about: dict) -> str:
    where = f", in {alias[row['thread_id']]}'s thread" if row["thread_id"] in alias else ""
    if row["author"] == "user":
        return f"person{where}"
    if row["kind"] == "rubric":
        return "rubric update"
    subject = about.get(row["data"].get("about")) if row["data"] else None
    return f"you{where}" + (f", about {subject}" if subject else "")


async def _context(model_id: UUID, batch: list) -> dict:
    model = await get_pool().fetchrow(
        "SELECT name, instructions FROM intuition_models WHERE id=$1", model_id
    )
    version = await versions.current(model_id)
    rows = await get_pool().fetch(
        """SELECT * FROM (SELECT * FROM eval_messages WHERE model_id=$1
           ORDER BY created_at DESC LIMIT $2) recent ORDER BY created_at""",
        model_id,
        MAX_MESSAGES,
    )
    new_ids = {m["id"] for m in batch}
    examples = await get_pool().fetch(
        """SELECT id, message_id, item, label FROM intuition_examples
           WHERE model_id=$1 AND message_id = ANY($2::uuid[]) ORDER BY created_at""",
        model_id,
        [r["id"] for r in rows],
    )
    alias = {r["id"]: f"M{i}" for i, r in enumerate(rows, 1)}
    attachment = {e["id"]: f"A{i}" for i, e in enumerate(examples, 1)}
    about = {str(k): v for k, v in attachment.items()}
    in_message: dict[UUID, list] = {}
    for e in examples:
        in_message.setdefault(e["message_id"], []).append(e)

    def attached(message_id: UUID) -> str:
        found = in_message.get(message_id, [])
        if not found:
            return ""
        return (
            " (attachments: "
            + ", ".join(f"{attachment[e['id']]} {e['label'] or 'unlabeled'}" for e in found)
            + ")"
        )

    untitled = model["name"] == service.UNTITLED
    head = [f"Eval: {model['name']}" + (" (untitled)" if untitled else "")]
    head.append(f"Description: {model['instructions'] or '(none yet)'}")
    if version:
        head.append(
            f"Rubric v{version['number']}: " + "; ".join(t["name"] for t in version["traits"])
        )
    # Unread messages outside this batch are left for the read that takes them.
    earlier = [
        r
        for r in rows
        if r["id"] not in new_ids and (r["author"] == "agent" or r["handled_at"] is not None)
    ][-HISTORY:]
    if earlier:
        head.append(
            "Earlier in the channel (oldest first):\n"
            + "\n".join(
                f"[{alias[r['id']]}] {_who(r, alias, about)}: {r['text'][:800]}"
                + attached(r["id"])
                + (
                    f" (choices: {', '.join(r['data']['choices'])})"
                    if (r["data"] or {}).get("choices")
                    else ""
                )
                for r in earlier
            )
        )
    waiting = [
        f"{attachment[e['id']]} (in {alias[e['message_id']]})"
        for e in examples
        if e["label"] is None and e["message_id"] not in new_ids
    ]
    if waiting:
        head.append("Still unlabeled: " + ", ".join(waiting))
    content: list[dict] = [
        {"type": "text", "text": "\n\n".join(head)},
        {"type": "text", "text": "New messages:"},
    ]
    shown: set[UUID] = set()
    images = 0

    async def show(found: list) -> list[dict]:
        nonlocal images
        blocks = []
        for e in found:
            if e["id"] in shown:
                continue
            shown.add(e["id"])
            item = e["item"] if isinstance(e["item"], dict) else json.loads(e["item"])
            label = f"Attachment {attachment[e['id']]} ({_file(item)['name']}, {e['label'] or 'unlabeled'})"
            if images >= MAX_IMAGES:
                blocks.append({"type": "text", "text": label + ": not shown"})
                continue
            images += 1
            blocks += [{"type": "text", "text": label + ":"}, *await items.blocks(item, 512)]
        return blocks

    for m in batch:
        content.append(
            {
                "type": "text",
                "text": f"[{alias[m['id']]}] {_who(m, alias, about)}: {m['text'] or '(no text)'}",
            }
        )
        content += await show(in_message.get(m["id"], []))
        if m["thread_id"] in in_message:
            parent = in_message[m["thread_id"]]
            if any(e["id"] not in shown for e in parent):
                content.append(
                    {
                        "type": "text",
                        "text": f"Attachments in {alias[m['thread_id']]}, where this thread starts:",
                    }
                )
                content += await show(parent)
    content.append({"type": "text", "text": "Return the update now."})
    return {
        "content": content,
        "alias": {v: k for k, v in alias.items()},
        "attachment": {v: k for k, v in attachment.items()},
        "in_message": {alias[k]: [e["id"] for e in v] for k, v in in_message.items()},
        "messages": {r["id"]: r for r in rows},
        "untitled": untitled,
    }


def parse(text: str) -> dict:
    parsed = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
    labels = [
        {
            "attachments": [str(a) for a in lab.get("attachments", [])][:200],
            "label": lab.get("label"),
            "reason": str(lab.get("reason") or "")[:2000],
        }
        for lab in parsed.get("labels") or []
        if isinstance(lab, dict) and lab.get("label") in ("good", "bad")
    ]
    replies = [
        {
            "message": str(r.get("message", "")),
            "text": str(r.get("text", "")).strip()[:2000],
            "choices": [str(c)[:80] for c in (r.get("choices") or [])][:4],
        }
        for r in parsed.get("replies") or []
        if isinstance(r, dict) and str(r.get("text", "")).strip()
    ]
    return {
        "labels": labels,
        "replies": replies,
        "description": _text(parsed.get("description"), 2000),
        "rubric_request": _text(parsed.get("rubric_request"), 1000),
        "name": _text(parsed.get("name"), 160),
    }


def _text(value, limit: int) -> str | None:
    return (str(value).strip()[:limit] or None) if value else None


async def _apply(model_id: UUID, context: dict, update: dict) -> None:
    changed = False
    for lab in update["labels"]:
        targets: list[UUID] = []
        for ref in lab["attachments"]:
            if ref.endswith("/all"):
                targets += context["in_message"].get(ref[: -len("/all")], [])
            elif ref in context["attachment"]:
                targets.append(context["attachment"][ref])
        if not targets:
            continue
        updated = await get_pool().fetch(
            """UPDATE intuition_examples
                  SET label=$3, needs_review=false, note=CASE WHEN $4 <> '' THEN $4 ELSE note END
                WHERE model_id=$1 AND id = ANY($2::uuid[])
                  AND (label IS DISTINCT FROM $3 OR ($4 <> '' AND note <> $4))
            RETURNING id""",
            model_id,
            targets,
            lab["label"],
            lab["reason"],
        )
        changed = changed or bool(updated)
    for r in update["replies"]:
        target = context["messages"].get(context["alias"].get(r["message"]))
        if target is None:
            continue
        await post_agent(
            model_id,
            r["text"],
            thread_id=target["thread_id"] or target["id"],
            data={"choices": r["choices"]} if r["choices"] else None,
        )
    if update["description"]:
        await service.set_instructions(model_id, update["description"])
    if update["name"] and context["untitled"]:
        await get_pool().execute(
            "UPDATE intuition_models SET name=$2, updated_at=now() WHERE id=$1 AND name=$3",
            model_id,
            update["name"],
            service.UNTITLED,
        )
    if update["rubric_request"]:
        await get_pool().execute(
            """UPDATE intuition_models SET build = jsonb_set(COALESCE(build, '{}'::jsonb), '{requests}',
                      COALESCE(build->'requests', '[]'::jsonb) || jsonb_build_array($2::text))
               WHERE id=$1""",
            model_id,
            update["rubric_request"],
        )
        changed = True
    if changed:
        await service.request_build(model_id)
