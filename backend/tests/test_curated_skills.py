"""The three curated slots the nightly curator owns.

Every rule here exists because a curated skill is *push*: its description
loads into every agent session whether or not anyone asked for it. That makes
the failure modes structural rather than cosmetic — an unbounded set crowds
out the context it was meant to improve, and a curator that overwrites a
human's skill changes behavior the human thought they controlled. So the cap
and the adoption boundary are enforced by the server, not by the prompt.
"""

import pytest
from httpx import AsyncClient

from .conftest import unique_name


async def _register(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/users/register",
        json={"name": unique_name(), "password": "securepassword1"},
    )
    assert resp.status_code == 201
    return resp.json()["api_key"]


def _auth(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


async def _write(client: AsyncClient, api_key: str, name: str, **extra):
    body = {
        "name": name,
        "description": f"When the user is doing {name}.",
        "body": f"- Always {name}.",
        **extra,
    }
    return await client.post("/api/v1/me/curated-skills", json=body, headers=_auth(api_key))


async def _fill_slots(client: AsyncClient, api_key: str) -> None:
    for name in ("alpha", "beta", "gamma"):
        assert (await _write(client, api_key, name)).status_code == 200


@pytest.mark.asyncio
async def test_curated_skill_is_a_real_skill_carrying_its_trigger(client: AsyncClient):
    """A curated skill has to be an ordinary skill or it never reaches an
    agent — sync only materializes what /me/skills lists. The description is
    the only text the harness matches on, so it must survive into SKILL.md."""
    api_key = await _register(client)
    resp = await _write(client, api_key, "port-discipline")
    assert resp.status_code == 200
    assert resp.json()["action"] == "created"

    listed = (await client.get("/api/v1/me/skills", headers=_auth(api_key))).json()["skills"]
    entry = next(s for s in listed if s["name"] == "port-discipline")
    assert entry["curated"] is True
    assert entry["description"] == "When the user is doing port-discipline."

    contents = await client.get(
        f"/api/v1/me/skills/{entry['folder_id']}/contents", headers=_auth(api_key)
    )
    skill_md = next(p for p in contents.json()["contents"]["pages"] if p["name"] == "SKILL.md")
    assert "curated: true" in skill_md["content_markdown"]
    assert "- Always port-discipline." in skill_md["content_markdown"]


@pytest.mark.asyncio
async def test_writing_the_same_name_updates_in_place(client: AsyncClient):
    """Nightly runs refine what they already wrote. If re-writing a slot minted
    a second skill instead, the set would grow past the cap one night at a
    time and two skills would compete for the same trigger."""
    api_key = await _register(client)
    first = await _write(client, api_key, "alpha")
    second = await _write(client, api_key, "alpha", body="- Sharper rule.")

    assert second.json()["action"] == "updated"
    assert second.json()["folder_id"] == first.json()["folder_id"]
    curated = (await client.get("/api/v1/me/curated-skills", headers=_auth(api_key))).json()
    assert len(curated["skills"]) == 1
    assert "- Sharper rule." in curated["skills"][0]["body"]


@pytest.mark.asyncio
async def test_fourth_slot_fails_loud_and_changes_nothing(client: AsyncClient):
    """The cap is the whole design: three skills the user can read in a minute.
    A curator that could quietly add a fourth would eventually rebuild the
    hundred-skill catalog this feature exists to avoid, so an unnamed
    replacement is an error rather than an eviction of the server's choosing."""
    api_key = await _register(client)
    await _fill_slots(client, api_key)

    resp = await _write(client, api_key, "delta")
    assert resp.status_code == 400
    assert "replaces" in resp.json()["detail"]

    curated = (await client.get("/api/v1/me/curated-skills", headers=_auth(api_key))).json()
    assert [s["name"] for s in curated["skills"]] == ["alpha", "beta", "gamma"]


@pytest.mark.asyncio
async def test_replaces_evicts_exactly_the_named_slot(client: AsyncClient):
    """Eviction has to remove the old skill, not merely stop advertising it:
    a retired skill still sitting in the agent's skills dir keeps firing."""
    api_key = await _register(client)
    await _fill_slots(client, api_key)

    resp = await _write(client, api_key, "delta", replaces="beta")
    assert resp.status_code == 200

    curated = (await client.get("/api/v1/me/curated-skills", headers=_auth(api_key))).json()
    assert sorted(s["name"] for s in curated["skills"]) == ["alpha", "delta", "gamma"]
    listed = (await client.get("/api/v1/me/skills", headers=_auth(api_key))).json()["skills"]
    assert "beta" not in [s["name"] for s in listed]


@pytest.mark.asyncio
async def test_replaces_an_unknown_name_evicts_nothing(client: AsyncClient):
    """A curator that misremembers a slot name must not get a free eviction of
    whichever skill the server would have picked."""
    api_key = await _register(client)
    await _fill_slots(client, api_key)

    resp = await _write(client, api_key, "delta", replaces="nonexistent")
    assert resp.status_code == 400

    curated = (await client.get("/api/v1/me/curated-skills", headers=_auth(api_key))).json()
    assert [s["name"] for s in curated["skills"]] == ["alpha", "beta", "gamma"]


@pytest.mark.asyncio
async def test_editing_a_curated_skill_adopts_it(client: AsyncClient):
    """The adoption rule: a human edit takes the skill out of the curator's
    hands for good. Without it, the two authors overwrite each other nightly
    and the user's edit silently disappears."""
    api_key = await _register(client)
    resp = await _write(client, api_key, "alpha")
    folder_id = resp.json()["folder_id"]

    contents = await client.get(f"/api/v1/me/skills/{folder_id}/contents", headers=_auth(api_key))
    page = next(p for p in contents.json()["contents"]["pages"] if p["name"] == "SKILL.md")
    edited = await client.patch(
        f"/api/v1/me/pages/{page['id']}",
        json={"content": '---\nname: "alpha"\ndescription: "mine now"\n---\n\n- My rule.'},
        headers=_auth(api_key),
    )
    assert edited.status_code == 200

    curated = (await client.get("/api/v1/me/curated-skills", headers=_auth(api_key))).json()
    assert curated["skills"] == []
    listed = (await client.get("/api/v1/me/skills", headers=_auth(api_key))).json()["skills"]
    assert next(s for s in listed if s["name"] == "alpha")["curated"] is False


@pytest.mark.asyncio
async def test_curator_refuses_to_rewrite_an_adopted_skill(client: AsyncClient):
    """Adoption is permanent. The next night's run must not resurrect its own
    version of a skill the user took over — under that name or a uniquified
    copy of it competing for the same trigger."""
    api_key = await _register(client)
    folder_id = (await _write(client, api_key, "alpha")).json()["folder_id"]
    await client.post(f"/api/v1/me/folders/{folder_id}/adopt-curated-skill", headers=_auth(api_key))

    resp = await _write(client, api_key, "alpha", body="- The curator's version.")
    assert resp.status_code == 400
    assert "own skill" in resp.json()["detail"]

    listed = (await client.get("/api/v1/me/skills", headers=_auth(api_key))).json()["skills"]
    assert [s["name"] for s in listed] == ["alpha"]


@pytest.mark.asyncio
async def test_publishing_a_curated_skill_adopts_it(client: AsyncClient):
    """Publishing is standing behind it in public. The curator must not keep
    rewriting a skill that now carries the user's name on a public URL."""
    api_key = await _register(client)
    folder_id = (await _write(client, api_key, "alpha")).json()["folder_id"]

    published = await client.post(
        "/api/v1/me/skills",
        json={"folder_id": folder_id, "description": "mine", "discoverable": False},
        headers=_auth(api_key),
    )
    assert published.status_code == 201

    curated = (await client.get("/api/v1/me/curated-skills", headers=_auth(api_key))).json()
    assert curated["skills"] == []


@pytest.mark.asyncio
async def test_demoting_a_curated_skill_to_a_folder_frees_the_slot(client: AsyncClient):
    """ "Not a skill" is the strongest possible rejection, so it has to release
    the slot too. It also has to be representable at all: a curated flag on a
    plain folder violates the folders_curated_is_a_skill check."""
    api_key = await _register(client)
    folder_id = (await _write(client, api_key, "alpha")).json()["folder_id"]

    demoted = await client.post(
        f"/api/v1/me/folders/{folder_id}/convert-to-folder", headers=_auth(api_key)
    )
    assert demoted.status_code == 200

    curated = (await client.get("/api/v1/me/curated-skills", headers=_auth(api_key))).json()
    assert curated["skills"] == []
