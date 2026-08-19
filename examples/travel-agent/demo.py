"""Two agencies, one planner. Proves what crosses between them and what does not.

export STASH_API_KEY=...
export ANTHROPIC_API_KEY=...
python demo.py            # both agencies talk
python demo.py verify     # after a curator run
"""

import os
import sys

from agent import answer
from stash import Stash

BASE_URL = os.environ.get("STASH_BASE_URL", "http://localhost:3456")
WANDERLY = ("wanderly", "Wanderly Travel")
GLOBETREK = ("globetrek", "Globetrek Corporate")


def main() -> int:
    stash = Stash(os.environ["STASH_API_KEY"], BASE_URL)
    key = os.environ["ANTHROPIC_API_KEY"]

    say("Wanderly learns something about the world the hard way")
    ask(stash, key, WANDERLY, "Client needs a Vietnam e-visa for a trip in 3 weeks. Fine?")
    ask(
        stash,
        key,
        WANDERLY,
        "Update: the Vietnam e-visa took 19 working days, not the 3 the site claims. "
        "We nearly missed it. Always allow a month.",
    )

    say("And something that is only ever Wanderly's business")
    ask(
        stash,
        key,
        WANDERLY,
        "Note for the file: our client Dr Okafor will not fly overnight and always "
        "books the aisle seat.",
    )

    say("Globetrek asks about something of its own")
    ask(stash, key, GLOBETREK, "Best way to get a team of six from Berlin to Lisbon in May?")

    say("What each agency can see")
    for org, name in (WANDERLY, GLOBETREK):
        print(f"\n  {name} ({org})")
        print(indent(stash.read(org, "ls /sessions")))

    say("Next")
    print("  Console -> Curator -> Run now, then:  python demo.py verify\n")
    return 0


def verify() -> int:
    stash = Stash(os.environ["STASH_API_KEY"], BASE_URL)
    key = os.environ["ANTHROPIC_API_KEY"]

    say("Globetrek hits the visa question Wanderly already learned about")
    ask(stash, key, GLOBETREK, "Client wants Vietnam in 3 weeks. Is the e-visa going to make it?")

    say("Can Globetrek see whose lesson that was?")
    for term in ("wanderly", "okafor"):
        hit = stash.read(GLOBETREK[0], f"grep -ri '{term}' /memory /files /sessions 2>/dev/null")
        print(
            f"  searching Globetrek's whole view for {term!r}: "
            f"{'FOUND — leak' if hit.strip() else 'nothing'}"
        )
    print()
    return 0


def ask(stash, key, org, question):
    org_id, org_name = org
    print(f"\n  {org_name} asks: {question}")
    print(indent(answer(stash, key, org_id, org_name, f"{org_id}/conv-1", question)))


def say(headline: str) -> None:
    print(f"\n\n=== {headline} ===")


def indent(text: str) -> str:
    return "\n".join(f"    {line}" for line in text.strip().splitlines()) or "    (nothing)"


if __name__ == "__main__":
    sys.exit(verify() if "verify" in sys.argv else main())
