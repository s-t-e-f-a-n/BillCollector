"""BillCollector daemon package (Wave 1, M1).

Turns the cron batch job into a 24/7 daemon: an orchestrator spawns one
subprocess per task run (sync Playwright), each run is pausable through a
versioned control socket, and a machine-readable pause context is persisted
for human (and future AI) intervention.

Keep this module free of heavy imports (nicegui, playwright) so the runner
subprocess stays lightweight and the UI process is the only one that loads
the web stack.
"""

__version__ = "0.1.0"
