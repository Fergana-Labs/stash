"""Test sets: regression tests for agents.

A test set holds cases (an input, and optionally the answer the agent should
give). Stash never runs the agent: the customer runs a new version on the
cases (the `stash test run --command` CLI does it in CI) and posts the outputs
as a run. Each output is scored by the set's scorers -- evals, with the labels
that count as a pass, and a judge of whether it matches the expected answer --
and the run is compared with a baseline: which cases got fixed, which broke.
The run fails its gate when more cases broke than the set allows.
"""
