# Files

- [Testing and Verification](verification.md) - How every documented BillCollector behavior is proven: the local regression harness that drives the production engine against a mock portal (with --vault end-to-end mode and exit codes 0-4), the pytest suite with the NiceGUI User fixture and fresh temp DB per test, and the Docker build context canary check - each with its exact command and expected result.
