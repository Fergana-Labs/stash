"""Prove External Multiplayer end to end, as a customer's backend would.

Two repair shops talk to the same agent. Acme hits a fault and finds the fix.
The curator distils that into the shared wiki, anonymized. Beta then hits the
same fault — and its agent already knows, without ever learning that Acme
exists.

    export STASH_API_KEY=...        # minted in the console, API Keys tab
    export ANTHROPIC_API_KEY=...
    python demo.py
"""

import os
import sys

from agent import answer
from stash import Stash

BASE_URL = os.environ.get("STASH_BASE_URL", "http://localhost:3456")
ACME = ("shop_acme", "Acme Truck Repair")
BETA = ("shop_beta", "Beta Fleet Services")


def main() -> int:
    api_key = os.environ["STASH_API_KEY"]
    anthropic_key = os.environ["ANTHROPIC_API_KEY"]
    stash = Stash(api_key, BASE_URL)

    say("Acme asks about a fault it has never seen")
    ask(
        stash,
        anthropic_key,
        ACME,
        f"{ACME[0]}/conv-1",
        "2020 Cascadia throwing fault F45. What is it?",
    )
    ask(
        stash,
        anthropic_key,
        ACME,
        f"{ACME[0]}/conv-1",
        "We fitted brake valve X123 and F45 cleared. Torque was 90 Nm.",
    )

    say("Beta asks about something of its own")
    ask(
        stash,
        anthropic_key,
        BETA,
        f"{BETA[0]}/conv-1",
        "Our 2018 Volvo VNL needs a serpentine belt.",
    )

    say("What each shop can see right now")
    for org, name in (ACME, BETA):
        print(f"\n  {name} ({org})")
        print(indent(stash.read(org, "ls /sessions")))

    say("Run the curator, then re-check")
    print("  Console -> Curator -> Run now, or wait for tonight's pass.")
    print("  Then:  python demo.py verify\n")
    return 0


def verify() -> int:
    stash = Stash(os.environ["STASH_API_KEY"], BASE_URL)
    anthropic_key = os.environ["ANTHROPIC_API_KEY"]

    say("Beta hits the fault Acme already solved")
    ask(
        stash,
        anthropic_key,
        BETA,
        f"{BETA[0]}/conv-2",
        "Now a 2020 Cascadia with fault F45. Any ideas?",
    )

    say("Can Beta tell where that came from?")
    leaked = stash.read(BETA[0], "grep -ri 'acme' /memory /files 2>/dev/null")
    print(indent(leaked) if leaked.strip() else "  Nothing. Beta cannot see that Acme exists.\n")
    return 0


def ask(stash, anthropic_key, org, session, question):
    org_id, org_name = org
    print(f"\n  {org_name} asks: {question}")
    print(indent(answer(stash, anthropic_key, org_id, org_name, session, question)))


def say(headline: str) -> None:
    print(f"\n\n=== {headline} ===")


def indent(text: str) -> str:
    return "\n".join(f"    {line}" for line in text.strip().splitlines()) or "    (nothing)"


if __name__ == "__main__":
    sys.exit(verify() if "verify" in sys.argv else main())
