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

## Minimum dogfood configuration

A fresh install is intentionally **not** dogfood-ready. Configure a real LLM and embedding backend before running `doctor.sh`.

For an OpenAI-compatible provider:

```bash
export LOOM_LLM_PROVIDER=openai-compatible
export LOOM_LLM_BASE_URL="https://your-provider.example/v1"
export LOOM_LLM_API_KEY="<secret>"
export LOOM_LLM_MODEL="<model>"
export LOOM_EMBEDDING=litellm
```

For the free/local model router, use:

```bash
export LOOM_LLM_PROVIDER=free
export LOOM_EMBEDDING=litellm
```

For the production-style dogfood path, configure persistent storage and the GitHub workflow explicitly:

```bash
export LOOM_STORAGE=postgresql
export LOOM_PG_HOST=localhost
export LOOM_PG_PORT=5432
export LOOM_REQUIRE_GITHUB=1
```

Do not put real secrets into documentation or commit them to `.env`. `setup.sh` preserves an existing `.env` and never prints its values.

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
6. Fedora is the supported Linux target until this installation path is proven.
