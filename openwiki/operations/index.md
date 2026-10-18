# Files

- [Development and Deployment](deployment.md) - The three delivery surfaces of BillCollector - install_local.sh for the local development stack, the single billcollector:latest image with its BuildKit layer-cache ordering and NAS bind-mount setup, and deploy_remote.sh's tag-aware remote deploy and one-command rollback - plus the trunk-based release model, the sanitized public mirror (sync script STRIP list covering the private agent-context artifacts, no CI pipeline), and the environment surface (apps/.env, BC_* path overrides, the Settings table, .dockerignore).
