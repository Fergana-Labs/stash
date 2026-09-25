# Transcript usage billing

Free includes **100,000 transcript tokens/month**. Pro retains its **$20/month or
$200/year** base subscription and includes **2,000,000 tokens/month**. Pro can opt
into additional usage at **$10 per million tokens**, with an explicit monthly
spending cap. The initial cap is $0 for every account, including existing Pro
subscribers. Enterprise retains its granted/custom entitlement and records usage
without automatic overage charges.

These are initial product rates, not measured gross-margin guarantees. Review
actual curation inference costs after rollout before changing allowances or rates.

## What counts

Count transcript event text using the pinned `tiktoken` **cl100k_base** encoding.
This is a stable, provider-independent billing unit. It does not include our
prompts, model outputs, cache accounting, or the cumulative token counters emitted
by coding agents. All event text, including tool results, counts. No rounding to
sessions, Skills, or million-token packages occurs.

The receipt is committed only after a successful curation run. Exact repeated
content within the same session and event type counts once; a replacement upload
cannot reset that identity. New entries appended to an existing session count as
new usage. The ledger retains content hashes, not transcript bodies. Private and
shared workspace curation of the same content produces one receipt.

A personal curation run freezes its history input in a short-lived database batch.
The agent's changes feed reads that batch and successful completion accounts for
that exact input. Curation progress, receipts, and the Stripe outbox commit in one
transaction. Failure or a changed spending limit rolls back accounting. Failed
batches are released for retry; abandoned worker batches expire. Budget checks and
receipts serialize on the billing account row.

Free and Pro allowances reset on the first of each month at **00:00 UTC**, including
annual subscriptions. Use processing time, not the transcript's historical date.
There is no rollover. Pause before the next whole transcript entry would exceed
the available tokens; leave the entry queued and explain the limit. A single
entry larger than the plan allowance requires a higher plan or spending cap.
Uploads, search, existing Skills, and manually authored Skills remain available.

Migration 0224 recognizes content already behind each curator's watermark without
charging for it, preserves the transcript data, and removes the old session quota
column. No historical overage is generated.

## Stripe configuration before enabling overages

Keep the existing monthly and annual base prices. Configure one **sum** meter:

- Event name: `transcript_overage_tokens`
- Customer payload key: `stripe_customer_id`
- Value payload key: `value`
- Default raw event ingestion; no pre-aggregation window

Create a recurring **monthly**, **USD**, **per-unit**, **metered** price attached to
that meter, with `unit_amount_decimal=0.001` (cents per token). Do not apply tiers
or quantity transforms: the backend reports only tokens above the included
allowance. Set `STRIPE_TOKEN_PRICE_ID` on the backend and workers. The opt-in
endpoint validates the price and meter against the code's published rate before
allowing additional spending. Missing configuration fails explicitly.

Opt-in attaches that price to the existing subscription and migrates it to
flexible billing when necessary. This supports annual base fees alongside monthly
usage invoices. Stripe documents this in [mixed interval subscriptions](https://docs.stripe.com/billing/subscriptions/mixed-interval?dashboard-or-api=api).
The invoice cycle can differ from the UTC allowance/reset calendar; the settings
screen states the calendar used for the spending cap.

Listen for `checkout.session.completed`, `customer.subscription.created`,
`customer.subscription.updated`, and `customer.subscription.deleted`. The handler
retrieves current subscription state rather than trusting reordered event payloads.
Canceled/past-due subscriptions and removed usage items cannot authorize overages.
Lowering a cap stops future spending, but leaves the usage item attached so accrued
charges can still be invoiced. All advertised caps/rates exclude tax.

## Delivery and reconciliation

Celery beat dispatches `backend.tasks.transcript_billing.report_usage` every minute.
A committed outbox row has a stable identifier and idempotency key. Failed requests
retry after five minutes using the original quantity and timestamp. Stripe only
guarantees meter-event identifier deduplication for at least 24 hours; see
[the meter event API](https://docs.stripe.com/api/billing/meter-event/create).

After 23 hours without a confirmed response, automatic replay stops and the task
raises an error. Inspect the affected row and Stripe's meter event records before
marking it reconciled or resending. Never issue a new identifier for an uncertain
delivery. Events older than 34 days also fail explicitly. Monitor worker failures
and Stripe's asynchronous meter processing errors; API acceptance alone is not an
invoice reconciliation check.

Before production activation, exercise the configured price in Stripe test mode:
opt in, cross the allowance, replay a report, advance the monthly and annual test
clocks, inspect invoices, lower the cap, and cancel. Automated repository tests use
Stripe mocks and a real local Postgres database; they do not prove account-specific
Stripe invoice configuration. No live Stripe resources or charges are created by
this code change itself.

Heavi workspaces with `legacy_wiki_enabled` keep unmetered curation and do not generate transcript usage charges. See [the rollout exception](../heavi-wiki-contract.md).
