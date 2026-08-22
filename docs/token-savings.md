# Token Savings with loom-ai  

---  

## 1. The Problem  

Modern coding assistants (e.g., **Claude Code**, **Cursor**) rely on large-language-model (LLM) APIs that charge per token.  
- A **single issue resolution** can consume **70 k–120 k tokens**.  
- At premium pricing, that translates to **$5–$9** per issue.  
- Scaling to dozens or hundreds of issues quickly becomes prohibitively expensive.  

---  

## 2. The Solution  

**loom-ai** uses free-model routing (now provided by [model-router-ai](https://github.com/FlossWare/model-router-ai)):  

| What it does | How it works |
|--------------|--------------|
| **Routes every LLM call** to **free** API models (Cohere, Groq, Cloudflare Workers AI, Cerebras, HuggingFace, etc.) | Uses **Thompson Sampling** to dynamically pick the best-performing free model for each sub-task |
| **Keeps the client** (Claude Code, Cursor, etc.) **agnostic** to the underlying model | The client only pays the tiny overhead of the **MCP tool call** (~500 tokens) |
| **Maintains quality** via multi-model consensus and a lightweight review loop | model-router-ai can fall back to a second free model if the first response fails quality checks |

Result: the client sees **premium-grade assistance** while paying **only for the tool-call overhead**.

---  

## 3. Token Comparison  

| Operation | Without loom-ai | With loom-ai | Savings |
|-----------|----------------|-------------|---------|
| Single issue resolution | 70 k–120 k tokens | ~500 tokens | **≈ 99.5 %** |
| Batch of 13 issues | ~1 M–1.5 M tokens | ~6.5 k tokens | **≈ 99.5 %** |
| Code review (3 rounds) | 18 k–36 k tokens | ~200 tokens | **≈ 99.4 %** |
| Multi-model consensus | 20 k–40 k tokens | ~300 tokens | **≈ 99.3 %** |

---  

## 4. Cost Comparison  

*(Claude Opus pricing ≈ $75 per million output tokens)*  

| Operation | Without loom-ai | With loom-ai |
|-----------|----------------|-------------|
| Single issue | **$5 – $9** | **$0.04** |
| Batch of 13 issues | **$75 – $112** | **$0.50** |
| Monthly (≈ 100 issues) | **$500 – $900** | **$3.75** |

---  

## 5. How It Works (Step-by-Step)  

1. **Client call** – The MCP client invokes the loom-ai tool:  

   ```python
   loom_resolve_issue(issue_number=123)   # ≈ 200 tokens
   ```  

2. **model-router-ai** – `DemoAgent` orchestrates the full resolution pipeline (retrieval, analysis, code generation, review) **exclusively on free models**. The internal token usage (70 k–120 k) is **$0** because the APIs are free.  

3. **Result return** – The final answer is sent back to the client, incurring only the response overhead:  

   ```text
   # result payload …  ≈ 300 tokens
   ```  

4. **Net paid tokens** – Roughly **500 tokens** total, all billed at the client’s standard MCP rate.  

---  

## 6. Free Model Providers Used  

- **Cohere** – `command-a-03-2025`  
- **Groq** – Qwen, GPT-OSS, LLaMA-2 variants  
- **Cloudflare Workers AI** – `@cf/meta/llama-2-7b-chat-fp16`  
- **Cerebras** – `llama2.7b`  
- **HuggingFace** – hosted inference endpoints (e.g., `mistralai/Mistral-7B-Instruct-v0.2`)  
- **Additional** – Any other zero-cost or community-hosted LLM that exposes an OpenAI-compatible API can be added to the router.  

---  

## 7. Quality Note  

- **Thompson Sampling** continuously balances exploration (trying new free models) and exploitation (using the best-known model) to keep performance high.  
- **Multi-model consensus**: For critical steps (e.g., final code diff), loom-ai aggregates responses from two or more free models and selects the most consistent output, achieving quality **on par with premium-only pipelines**.  

---  

### Bottom Line  

By off-loading the heavy LLM lifting to **free** APIs and only paying the minimal MCP tool-call overhead, loom-ai delivers **> 99 % token and cost savings** while preserving the developer experience of premium coding assistants.  

---

## See Also

- [MCP Tool Reference](mcp-tools.md) — the `loom_resolve_issue` tool that enables these savings
- [Frontend Setup](frontend-setup.md) — connect your coding assistant to loom-ai
- [Free AI Providers](free-ai-providers.md) — full list of free providers and accounts
