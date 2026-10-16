"""Agent Judge: an evaluator that investigates a trajectory instead of reading it whole.

A coordinator reads a trace's outline and the rubric, plans the checks, and
fans out workers. Each worker runs a small tool loop over the trace as a
queryable object (read a step range, grep, list tool calls, find similar
traces) and over read-only sources of truth (GitHub PRs and CI), and submits a
finding with step citations. Unsure findings fork a follow-up worker. The
coordinator merges the findings into answer probabilities per rubric question
and a claims ledger: what the agent said it did, and whether that held up.
"""
