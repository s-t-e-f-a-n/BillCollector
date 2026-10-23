# Phased login protection

Candidate interface for [upstream issue #20](https://github.com/s-t-e-f-a-n/BillCollector/issues/20).
This is a complete fork implementation candidate. Local proof and upstream
contract acceptance are separate gates. It is not approved for deployment.
The recipe and database interface were agreed in issue #20 (2026-10-22).

## Candidate recipe

Navigate to the portal before the login block. An already visible success locator
skips the whole block. Preparation supports locator chains ending in `fill` only.
The submit chain ends in one `click` or `press(key="Enter")`. Do not use this
contract for a portal that submits automatically when a field is filled.
For password then TOTP, use ordered `phases`. Each phase contains `steps`,
`submit` and `success`. The last success must equal the login success locator.
Do not combine `phases` with the single-phase shorthand below.

One transaction reserves one budget entry before its first submission. Each
phase submits once. A failed phase stops all later automatic phases. Resume
only verifies final authentication. A visible intermediate success locator lets
the runner skip an already completed phase. Use a marker unique to that state.
A crash between phases consumes one transaction attempt.
An intermediate marker must disappear after the portal leaves that state. A marker
that stays visible on later pages can make the runner skip a required phase.
After the first submission, preparation errors in later phases (including a TOTP
vault fetch failure) consume the reserved attempt even without a later submission.

```yaml
services:
  - serviceName: synthetic
    steps:
      - step: 1
        methods:
          - method: goto
            arguments:
              - url: http://127.0.0.1:8787/
      - step: 2
        methods:
          - method: login
            arguments:
              - success: {selector: '#account'}
              - max_failures: 2
              - timeout_ms: 10000
              - session_timeout_ms: 1000
        steps:
          - step: 21
            methods:
              - method: get_by_label
                arguments:
                  - text: Password
              - method: fill
                arguments:
                  - value: '{{PASSWORD}}'
        submit:
          step: 22
          methods:
            - method: get_by_role
              arguments:
                - role: button
                - name: Sign in
            - method: click
```

The daemon is the only supported executor of the new method. The historical batch
runner is unchanged. Existing daemon recipes keep their existing behavior.

## Persistence and recovery

The five additive Task fields are `login_failures`, `login_failure_limit`,
`login_locked`, `login_pending_run_id` and `login_cycle_active`.
The cycle marker survives a clear even when a limit of one leaves zero failures.
Only session proof ends that cycle. Migration of an older candidate conservatively
keeps a stored limit of one active until session proof, because its cleared and
successful states were indistinguishable. Reservation increments and commits the
budget before dispatch. A pending attempt is settled once on normal exit, runner
failure, monitor finalization or orphan recovery. A crash without success proof
consumes that budget. A crash before dispatch can conservatively consume it too.

The limit cannot increase during a consecutive-failure cycle. A new lower limit
can tighten it. Raising the recipe limit after a block grants no extra attempts:
the effective limit stays at the minimum of the stored and recipe limits until
session proof. Explicit clear preserves the profile and scheduler configuration,
and leaves only one attempt. Session proof resets the budget. Ordinary lifecycle
status changes cannot clear a login block. Manual VNC/guided-browser submissions
are outside the automatic counter and the UI states that limitation.

## Implementation and acceptance plan

The implementation follows six steps:

1. **Recipe validation** (`login.py`, schema, recipe editor): one top-level login
   transaction, explicit success locator, preparation fills, one submission per phase.
   Reject nested/graceful login and unsupported options before vault/browser use.
2. **Persistent budget** (`db.py`): additive migration, atomic reservation,
   run ownership, idempotent settlement and one-attempt clear. A threshold cannot
   increase during a failure cycle. A foreign or finalized run cannot reset it.
3. **Execution** (`runner.py`): persistent-session bypass, ordered phase submissions,
   pause/resume proof without replay, and a process-held task lock for CLI and
   daemon entry. Keep unrelated retries and graceful/download behavior.
4. **Recovery** (`orchestrator.py`): settle pending attempts after crash and
   daemon restart, including a crash after Run finalization. Do not release a
   task while another active Run still owns it.
5. **Operator controls** (dashboard, task detail, notifications): show the block,
   refuse execution, confirm idle-only clear, preserve profile and schedule.
   Automatic locking sends one best-effort notification. Delivery is not durable
   across a crash in the commit-to-send window. The daemon sends HTTP in a worker
   thread and awaits pending sends during shutdown without blocking its event loop.
   The runner sends synchronously. An empty UI base URL omits the task link.
6. **Acceptance**: execute isolated tests, browser fixtures and historical
   regression; inspect the semantic diff and pinned static checks; commit locally.
   Upstream publication requires the issue #20 agreement and a fresh baseline.

## Requirement-to-proof map

| Requirement | Evidence in repository |
|---|---|
| Session proof bypasses login and resets budget | `test_real_browser_existing_session_skips_and_resets` |
| One submit per phase, failed resume never replays | `test_real_browser_failure_pause_resume_never_resubmits` |
| Password/TOTP success, failures and direct OTP entry | `test_two_phase_browser_login_counts_one_transaction` |
| Crash between password and TOTP consumes one attempt | `test_interruption_between_phases_keeps_one_durable_attempt` |
| Two failures block; clear grants only one attempt | `test_real_browser_threshold_blocks_and_clear_grants_one_attempt` |
| Ambiguous submit consumes budget | `test_submission_exception_never_replays_and_consumes_budget` |
| Preparation failure consumes no attempt | `test_prepare_failure_never_consumes_attempt` |
| Pending attempt survives process death | `test_process_crash_after_reservation_recovers_without_replay` |
| Finalization/settlement crash window recovers | `test_crash_between_finalization_and_settlement_recovers` |
| SQLite migration preserves data | `test_migrate_old_database_twice_preserves_data` |
| Concurrent reservation and direct entry are bounded | `test_concurrent_connections_can_reserve_only_one_attempt`, `test_concurrent_direct_entry_stops_before_task_execution` |
| CLI and daemon admission refuse a blocked task | `test_blocked_direct_runner_stops_before_recipe_vault_or_display`, `test_blocked_manual_and_scheduled_admission_never_spawns` |
| Foreign run cannot reset or release another run | `test_foreign_or_completed_run_cannot_reset_budget`, `test_rejected_contender_cannot_release_active_task` |
| Lowering the limit preserves one-attempt clear | `test_lowered_limit_clear_grants_exactly_one_retry` |
| Unsupported locator options fail before runtime | `test_unsupported_test_id_option_rejected_before_runtime` |
| Finalized-attempt recovery preserves another active Run | `test_finalized_attempt_recovery_preserves_another_active_run` |
| Limit-one clear survives restart and cannot raise the budget | `test_limit_one_clear_cannot_raise_budget_and_survives_restart` |
| Prior candidate migration preserves a cleared limit-one budget | `test_migrate_prior_candidate_preserves_cleared_limit_one` |
| Pending login is distinct from blocked in task detail | `test_login_pending_is_distinct_from_blocked` |
| Limit increase cannot bypass clear | `test_limit_cannot_increase_to_bypass_clear_budget` |
| UI clear preserves profile and schedule | `test_login_clear_grants_one_attempt_and_preserves_configuration` |
| Clear is unavailable while active | `test_login_clear_is_unavailable_while_task_is_active` |
| Notification transport is simulated and called once | `test_notification_is_mocked_and_sent_once_per_block` |
| Slow notifications keep daemon lifecycle paths responsive | `test_slow_login_notification_keeps_daemon_loop_responsive` |
| Notification links require a configured UI base URL | `test_login_notification_links_require_a_base_url` |
| Real recipe dispatcher continues after proven login | `test_dispatcher_runs_login_and_continues_only_after_success` |

The focused tests are in `tests/test_bc_login.py`. UI tests are in
`tests/test_bc_ui_task_detail.py`. Run the full suite with
`LC_ALL=C apps/.venv/bin/python -m pytest tests/ -q`. The test setup forces
DB/profile/download paths into temporary directories and denies non-loopback
Python connections. The real browser fixture also blocks non-loopback requests.

## Boundaries and rollback

This supports explicit ordered phases and requires a reliable, portal-specific
success locator. Preparation fills must not trigger implicit submission. A stale
or incorrect success locator cannot establish real authentication: recipe authors
must verify that proof. Arbitrary manual VNC/browser submissions are not counted.
The candidate phased contract still requires upstream agreement. The UI
notification is best-effort, and a stopped older binary does not enforce the new
block fields. These are explicit contract limits, not claims of provider lockout
immunity.

The first test attempt in d944151 contacted the default public ntfy transport;
delivery was unknown. Tests were stopped. Resumed work forces isolated paths,
forbids external Python socket connections and mocks notification transport.
The incident and transient verification results remain in Beads.

No live provider, vault, Paperless or production state is part of acceptance.
Revert the scoped source commits to roll back local development. A deployed
rollback must preserve the SQLite fields and stop blocked tasks before starting
an older binary. Deployment remains a separate operation and authorization.
