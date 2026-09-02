"""The GPU-free parts of Stylewriter. Why they matter: the prompt format is
the technique (train and serve must agree to the token), the style score is
what ranks drafts, and the selection loop is what keeps GPU cost to one
batch in the common case."""

from stylewriter import adapters, binoculars, prep, scaffold, selection, stylometry

ESSAY = (
    "I keep coming back to the same idea. Memory is not a feature you bolt onto "
    "an agent; it's a control problem. Every time we tried the easy version, it "
    "worked for a week and then quietly drifted. So we stopped and asked what "
    "we were actually trying to hold still. "
) * 6

CORPORATE = (
    "Our organization is committed to delivering comprehensive solutions that "
    "leverage synergies across the enterprise. Stakeholders are encouraged to "
    "align on strategic priorities. Deliverables will be tracked in accordance "
    "with established governance frameworks. "
) * 6


def test_training_pair_and_generation_share_one_prompt():
    prompt = scaffold.write_prompt(["the wedge is trust", "users are ops leads"], "short")
    chat = scaffold.training_pair(prompt, "Trust is the wedge.")
    assert chat[:-1] == prompt.messages
    assert chat[-1] == {"role": "assistant", "content": "Trust is the wedge."}
    assert "- the wedge is trust" in prompt.messages[-1]["content"]


def test_continue_prompt_carries_preceding_text():
    prompt = scaffold.write_prompt(["next point"], "medium", preceding_text="So far so good.")
    assert "So far so good." in prompt.messages[-1]["content"]
    assert scaffold.Prompt.from_dict(prompt.to_dict()) == prompt


def test_trim_keeps_whole_sentences():
    assert scaffold.trim_to_sentence("One. Two. Thr") == "One. Two."
    assert scaffold.trim_to_sentence("no punctuation at all") == "no punctuation at all"


def test_parse_notes_reads_bullets_and_numbers_only():
    answer = "Here are notes:\n- first point\n2. second point\nnot a note\n* third"
    assert prep.parse_notes(answer) == ["first point", "second point", "third"]


def test_pairs_per_chunk_cover_write_continue_and_rewrite():
    chunk = {"text": ESSAY, "words": len(ESSAY.split()), "length": "long"}
    pairs = prep.pairs_for_chunk(chunk, ["memory is a control problem"], "Generic version.")
    assert len(pairs) == 3
    assert all(p[-1]["role"] == "assistant" for p in pairs)
    preceding, rest = prep.split_for_continuation(ESSAY)
    assert preceding.endswith(".") and rest


def test_stylometry_prefers_the_authors_own_register():
    profile = stylometry.fit([ESSAY[:400], ESSAY[400:800], ESSAY[800:1200]])
    own = stylometry.similarity(profile, ESSAY[1200:1600])
    other = stylometry.similarity(profile, CORPORATE[:400])
    assert own > other
    assert stylometry.Profile.from_dict(profile.to_dict()) == profile


def test_selection_stops_at_the_first_passing_batch():
    calls = []

    def draw(n):
        calls.append(n)
        return [f"draft {len(calls)}-{i}" for i in range(n)]

    chosen = selection.best_of_n(
        draw, score=lambda t: 0.5, detect=lambda texts: [0.9] * len(texts), cap=8, batch=4
    )
    assert calls == [4]
    assert chosen.draws == 4 and not chosen.soft_failed
    assert len(chosen.alternates) == 3


def test_selection_soft_fails_after_the_cap():
    chosen = selection.best_of_n(
        lambda n: [f"d{i}" for i in range(n)],
        score=lambda t: float(t[-1]) / 10,
        detect=lambda texts: [0.1] * len(texts),
        cap=8,
        batch=4,
    )
    assert chosen.soft_failed and chosen.draws == 8
    assert chosen.text == "d3"


def test_p_human_is_monotone_around_the_threshold():
    assert binoculars.p_human(binoculars.THRESHOLD) == 0.5
    assert binoculars.p_human(binoculars.THRESHOLD + 0.2) > 0.9
    assert binoculars.p_human(binoculars.THRESHOLD - 0.2) < 0.1


def test_lora_ids_fit_the_engine():
    # This path's CRC exceeds int32 and crashed the engine once.
    path = "/adapters/model_ff531fdb5bfb4e5ab000e00e0954a8c7"
    for candidate in (path, "/adapters/model_default", "/adapters/model_x"):
        value = adapters.lora_id(candidate)
        assert 1 <= value <= 0x7FFFFFFF
    assert adapters.lora_id(path) != adapters.lora_id("/adapters/model_default")
