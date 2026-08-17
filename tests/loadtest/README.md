# Load Testing

Load tests for the loom-ai FastAPI server using [Locust](https://locust.io/).

## Prerequisites

```bash
pip install flossware-loom-ai[loadtest]
```

## Running

1. Start the loom-ai server (in-memory backends are sufficient):

   ```bash
   LOOM_LLM_BASE_URL=http://localhost:11434/v1 python -m loom_ai.server
   ```

   Or without an LLM backend (the `/llm/chat` task will return errors,
   but `/health` and `/ready` still work):

   ```bash
   python -m loom_ai.server
   ```

2. Run Locust:

   ```bash
   locust -f tests/loadtest/locustfile.py --host http://127.0.0.1:5000
   ```

3. Open `http://localhost:8089` in a browser to configure user count,
   spawn rate, and view real-time metrics.

### Headless mode

```bash
locust -f tests/loadtest/locustfile.py \
    --host http://127.0.0.1:5000 \
    --headless \
    -u 50 -r 10 \
    --run-time 60s
```

## Endpoints tested

| Endpoint     | Method | Weight | Notes                              |
|------------- |--------|--------|------------------------------------|
| `/health`    | GET    | 3      | Liveness probe, always available   |
| `/ready`     | GET    | 2      | Readiness probe, pings backends    |
| `/llm/chat`  | POST   | 1      | Requires LLM backend configured   |
