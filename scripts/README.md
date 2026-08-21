# Loom operator scripts

Fedora is the first supported Linux installation target. **Podman is the supported Linux container runtime.** Docker is optional compatibility, not a dependency.

## Clean-machine workflow

```bash
./scripts/install.sh
./scripts/setup.sh
./scripts/doctor.sh
./scripts/test.sh
./scripts/dogfood.sh
```

The installer provisions a repository-local `.venv`, required Fedora host tools, and rootless Podman. The doctor is diagnostic and fail-closed for the configured dogfood dependencies. It performs a real rootless Podman container smoke test.

Configure a real LLM, non-noop embedding backend, and persistent storage before claiming dogfood qualification. Never commit credentials.

## Design rules

1. Scripts are idempotent.
2. Secrets are never printed.
3. Required failures are non-zero.
4. Configured production backends are never silently downgraded.
5. Podman runs rootless.
6. Fedora is first-class until the installation path is proven; Debian follows afterward.
