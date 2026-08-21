# Loom operator scripts

Fedora is the first supported Linux installation target. Debian/Ubuntu support follows after this path is proven.

## Clean-machine workflow

```bash
git clone https://github.com/FlossWare/loom-ai.git
cd loom-ai
./scripts/install.sh
./scripts/setup.sh
./scripts/doctor.sh
./scripts/test.sh
./scripts/dogfood.sh
```

## Commands

- `install.sh` installs Fedora host prerequisites and Loom into `.venv`.
- `setup.sh` creates `.env` from `.env.example` only when `.env` does not already exist.
- `doctor.sh` diagnoses the environment and exits nonzero for required failures. It does not install or modify dependencies.
- `test.sh` runs the repository test suite using the project virtualenv when available.
- `dogfood.sh` runs doctor first and then enters the evidence-producing acceptance path with canary mode enabled.
- `uninstall.sh` removes only the repository-local virtualenv. It deliberately leaves source, configuration and system packages alone.

## Design rules

1. Scripts must be idempotent.
2. Scripts must never print credentials or tokens.
3. Required failures must be explicit and nonzero.
4. No script may silently downgrade a configured production backend to an in-memory backend.
5. User-local installation is preferred over system-wide installation.
