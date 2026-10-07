# Account product checkpoints

`users.product_checkpoint` selects an operator-managed product experience. New
and existing accounts default to `latest`. The profile API returns the selection,
but profile edits cannot change it. Authentication and account ownership stay the
same; switching checkpoints does not move or delete data.

## Floodgate, October 5, 2026

`floodgate-2026-10-05` reproduces the reward-model experience deployed at the start
of the October 5, 3:15 PM America/Los_Angeles demo (22:15 UTC):

- Source commit: `c9f40a421d309fba47ea243681adddaea66da9d6` (release 0.1.371).
- Navigation: Traces, Reward models, Skills.
- Original trace detail, action scoring, annotations, trace table, and training
  form, including the original single-trace training request.
- No Review, Changes, Graders, or automatic Jev workbench evaluation. Those
  backend routes return 404 for checkpoint accounts, and new comments do not
  become workbench feedback.

The eight changed UI components are preserved under
`frontend/src/checkpoints/floodgate-2026-10-05/`. They were copied from the source
commit; imports use the existing shared components where their behavior has not
changed. The current compatible backend, authentication, storage, and shared
infrastructure remain in use. This is a named UI/workflow checkpoint, not an
independently deployed historical server or a database rollback.

## Assign or remove a checkpoint

Deploy migration 0222 and both application services before selecting a checkpoint.
Use an operator database transaction that verifies both the intended account ID
and email. Set `reward_models_enabled = true` and
`product_checkpoint = 'floodgate-2026-10-05'` for that account only. Reload the
signed-in app so its profile is refreshed. Return it to the current experience by
setting `product_checkpoint = 'latest'`.

Historical demo data must be copied separately from a point-in-time snapshot,
remapping owner and record IDs while preserving relationships. Do not restore the
shared production database, copy sign-in credentials or integration tokens, or
replace another account's data. Retain a backup of the destination data before
replacing its demo records.

## Validation

Backend integration tests cover profile defaults, operator-only selection,
profile edits, trace and annotation access, workbench isolation, and the original
single-trace training payload without launching compute. Frontend tests cover
both navigation and table variants, historical/latest training behavior, and
redirects away from newer workbench routes.
