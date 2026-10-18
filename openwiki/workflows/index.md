# Files

- [Run Lifecycle: Scheduling, Locking, and Step Recording](run-lifecycle.md) - A run traced end to end in both coexisting modes - the cron-launched batch path with its two flock guards, per-pair failure isolation, and legacy run-table finalization, and the daemon path from scheduler job to claim, subprocess spawn, the step loop with its retry budget and PageStatus recording, Run finalization, and the orchestrator's fallback finalization.
