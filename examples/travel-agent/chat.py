"""Talk to the travel planner as one agency. This is the toy — play with it.

    export STASH_API_KEY=...        # console -> API Keys
    export ANTHROPIC_API_KEY=...
    python chat.py wanderly         # or any agency id you like

Every turn is recorded under that agency's org id, and every turn reads back
what that agency is allowed to know. Run it twice with two different agency
ids and watch what does and does not cross between them.
"""

import os
import sys
import uuid

from agent import answer
from stash import Stash

BASE_URL = os.environ.get("STASH_BASE_URL", "http://localhost:3456")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    org = sys.argv[1]
    org_name = sys.argv[2] if len(sys.argv) > 2 else org.replace("-", " ").title()

    stash = Stash(os.environ["STASH_API_KEY"], BASE_URL)
    # A session belongs to one agency, so the id is namespaced by agency.
    session = f"{org}/chat-{uuid.uuid4().hex[:8]}"

    print(f"Planning for {org_name} ({org}). Ctrl-D to leave.\n")
    while True:
        try:
            question = input("you  ")
        except EOFError:
            print()
            return 0
        if not question.strip():
            continue
        print(
            f"\nplanner  {answer(stash, os.environ['ANTHROPIC_API_KEY'], org, org_name, session, question)}\n"
        )


if __name__ == "__main__":
    sys.exit(main())
