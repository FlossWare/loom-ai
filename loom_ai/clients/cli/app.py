"""Loom-AI CLI — interactive chat, consensus, search, and management.

Usage::

    # Interactive REPL
    loom

    # One-shot commands
    loom chat "What is Python?"
    loom chat "Explain async" --model gpt-4o-mini --temperature 0.3
    loom consensus "Best Python web framework?" --models gemini,gpt-4o,claude
    loom models
    loom search "async patterns"
    loom health
    loom docs store --title "README" --file README.md
    loom docs list
    loom secrets list

Environment variables:
    LOOM_URL          Full server URL (default: http://127.0.0.1:5000)
    LOOM_HOST         Server host (default: 127.0.0.1)
    LOOM_PORT         Server port (default: 5000)
    LOOM_API_KEY      Bearer token for authentication
    LOOM_MODEL        Default model for chat commands
    LOOM_TIMEOUT      Request timeout in seconds (default: 60)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
from typing import Any, Union

from loom_ai.clients import get_client
from loom_ai.clients.client import ClientConfig, LoomClient
from loom_ai.clients.local_client import LocalClient

AnyClient = Union[LocalClient, LoomClient]


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loom",
        description="Loom-AI client — chat, consensus, search, and more",
    )
    parser.add_argument(
        "--url", default=None, help="Server URL (overrides LOOM_URL env var)"
    )
    parser.add_argument(
        "--api-key", default=None, help="API key (overrides LOOM_API_KEY env var)"
    )

    sub = parser.add_subparsers(dest="command")

    # chat
    chat_p = sub.add_parser("chat", help="Send a chat message")
    chat_p.add_argument("message", nargs="?", help="Message text (omit for stdin)")
    chat_p.add_argument("-m", "--model", default=None, help="Model to use")
    chat_p.add_argument("-t", "--temperature", type=float, default=0.7)
    chat_p.add_argument("--max-tokens", type=int, default=None)
    chat_p.add_argument("-s", "--system", default=None, help="System prompt")
    chat_p.add_argument("--stream", action="store_true", help="Stream response")
    chat_p.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output raw JSON",
    )

    # consensus
    cons_p = sub.add_parser("consensus", help="Multi-model consensus")
    cons_p.add_argument("prompt", help="Prompt to send to all models")
    cons_p.add_argument("--models", required=True, help="Comma-separated model list")
    cons_p.add_argument("--arbiter", default=None, help="Arbiter model")
    cons_p.add_argument(
        "--tool",
        default="design",
        choices=["design", "review", "implement"],
    )
    cons_p.add_argument("-t", "--temperature", type=float, default=0.7)
    cons_p.add_argument("--json", action="store_true", dest="json_output")

    # models
    sub.add_parser("models", help="List available models")

    # health
    sub.add_parser("health", help="Check server health")

    # ready
    sub.add_parser("ready", help="Check server readiness")

    # search
    search_p = sub.add_parser("search", help="Search knowledge base")
    search_p.add_argument("query", help="Search query")
    search_p.add_argument("-n", "--limit", type=int, default=10)

    # docs store
    docs_p = sub.add_parser("docs", help="Document management")
    docs_sub = docs_p.add_subparsers(dest="docs_command")

    docs_store = docs_sub.add_parser("store", help="Store a document")
    docs_store.add_argument("--title", required=True)
    docs_store.add_argument("--file", default=None, help="Read content from file")
    docs_store.add_argument("--content", default=None, help="Inline content")
    docs_store.add_argument("--category", default="")

    docs_sub.add_parser("list", help="List documents")
    docs_sub.add_parser("stats", help="Knowledge base stats")

    # secrets
    secrets_p = sub.add_parser("secrets", help="Secret management")
    secrets_sub = secrets_p.add_subparsers(dest="secrets_command")
    secrets_sub.add_parser("list", help="List secret names")
    secrets_get = secrets_sub.add_parser("get", help="Retrieve a secret")
    secrets_get.add_argument("name", help="Secret name")

    # graph
    graph_p = sub.add_parser("graph", help="Knowledge graph operations")
    graph_sub = graph_p.add_subparsers(dest="graph_command")
    node_add = graph_sub.add_parser("add-node", help="Add a graph node")
    node_add.add_argument("label", help="Node label")
    node_add.add_argument("--id", default=None)
    node_get = graph_sub.add_parser("get-node", help="Get a graph node")
    node_get.add_argument("node_id", help="Node ID")
    neighbors = graph_sub.add_parser("neighbors", help="Get node neighbors")
    neighbors.add_argument("node_id")
    neighbors.add_argument("--edge-label", default=None)

    return parser


async def _build_client(
    args: argparse.Namespace,
) -> AnyClient:
    if args.url or args.api_key:
        config = ClientConfig.from_env()
        if args.url:
            config.base_url = args.url
        if args.api_key:
            config.api_key = args.api_key
        return LoomClient(config)
    return await get_client()


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2))


def _read_message(args: argparse.Namespace) -> str:
    message = args.message
    if not message:
        if sys.stdin.isatty():
            print("Enter message (Ctrl+D to send):", file=sys.stderr)
        message = sys.stdin.read().strip()
        if not message:
            print("Error: empty message", file=sys.stderr)
            sys.exit(1)
    return message


def _build_messages(message: str, system: str | None) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": message})
    return messages


async def _cmd_chat(client: AnyClient, args: argparse.Namespace) -> None:
    message = _read_message(args)
    messages = _build_messages(message, args.system)
    model = args.model or os.environ.get("LOOM_MODEL") or None

    if args.stream:
        try:
            async for token in client.chat_stream(
                messages,
                model=model,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            ):
                print(token, end="", flush=True)
            print()
        except (RuntimeError, OSError) as exc:
            print(f"\nStream error: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        resp = await client.chat(
            messages,
            model=model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
        if args.json_output:
            _print_json(resp)
        else:
            print(resp.get("content", resp.get("response", "")))


async def _cmd_consensus(client: AnyClient, args: argparse.Namespace) -> None:
    models = [m.strip() for m in args.models.split(",")]
    resp = await client.consensus_synthesize(
        args.prompt,
        models,
        arbiter_model=args.arbiter,
        tool_name=args.tool,
        temperature=args.temperature,
    )
    if args.json_output:
        _print_json(resp)
    else:
        synthesis = resp.get("synthesis", {})
        print(synthesis.get("content", ""))
        failed = resp.get("failed_models", [])
        if failed:
            print(f"\nFailed models: {', '.join(failed)}", file=sys.stderr)


async def _cmd_models(client: AnyClient) -> None:
    models = await client.list_models()
    for m in models:
        print(m)


async def _cmd_health(client: AnyClient) -> None:
    resp = await client.health()
    _print_json(resp)


async def _cmd_ready(client: AnyClient) -> None:
    resp = await client.ready()
    _print_json(resp)


async def _cmd_search(client: AnyClient, args: argparse.Namespace) -> None:
    resp = await client.search_text(args.query, limit=args.limit)
    results = resp.get("results", [])
    if not results:
        print("No results found.")
        return
    for i, r in enumerate(results, 1):
        score = r.get("score", 0)
        title = r.get("document_title", "")
        content = r.get("content", "")[:200]
        print(f"{i}. [{score:.3f}] {title}")
        print(f"   {content}")
        print()


async def _cmd_docs(client: AnyClient, args: argparse.Namespace) -> None:
    if args.docs_command == "store":
        content = args.content
        if args.file:
            try:
                content = await asyncio.to_thread(pathlib.Path(args.file).read_text)
            except (FileNotFoundError, PermissionError) as exc:
                print(f"Error reading file: {exc}", file=sys.stderr)
                sys.exit(1)
        if not content:
            print("Error: provide --content or --file", file=sys.stderr)
            sys.exit(1)
        resp = await client.store_document(args.title, content, category=args.category)
        _print_json(resp)
    elif args.docs_command == "list":
        resp = await client.list_documents()
        _print_json(resp)
    elif args.docs_command == "stats":
        resp = await client.knowledge_stats()
        _print_json(resp)
    else:
        print("Usage: loom docs {store|list|stats}", file=sys.stderr)


async def _cmd_secrets(client: AnyClient, args: argparse.Namespace) -> None:
    if args.secrets_command == "list":
        names = await client.list_secrets()
        for name in names:
            print(name)
    elif args.secrets_command == "get":
        value = await client.get_secret(args.name)
        print(value)
    else:
        print("Usage: loom secrets {list|get}", file=sys.stderr)


async def _cmd_graph(client: AnyClient, args: argparse.Namespace) -> None:
    if args.graph_command == "add-node":
        resp = await client.add_node(args.label, node_id=args.id)
        _print_json(resp)
    elif args.graph_command == "get-node":
        resp = await client.get_node(args.node_id)
        _print_json(resp)
    elif args.graph_command == "neighbors":
        resp = await client.get_neighbors(args.node_id, edge_label=args.edge_label)
        _print_json(resp)
    else:
        print("Usage: loom graph {add-node|get-node|neighbors}", file=sys.stderr)


async def _repl_models(client: AnyClient, current: str) -> None:
    try:
        models = await client.list_models()
        for m in models:
            marker = " *" if m == current else ""
            print(f"  {m}{marker}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)


async def _repl_consensus(client: AnyClient) -> None:
    try:
        prompt = (await asyncio.to_thread(input, "prompt> ")).strip()
        model_str = (
            await asyncio.to_thread(input, "models (comma-separated)> ")
        ).strip()
        if prompt and model_str:
            models = [m.strip() for m in model_str.split(",")]
            print("Gathering consensus...", file=sys.stderr)
            resp = await client.consensus_synthesize(
                prompt,
                models,
            )
            synthesis = resp.get("synthesis", {})
            print(f"\n{synthesis.get('content', '')}")
            failed = resp.get("failed_models", [])
            if failed:
                print(
                    f"\nFailed: {', '.join(failed)}",
                    file=sys.stderr,
                )
    except (EOFError, KeyboardInterrupt):
        print()


async def _repl_chat(
    client: AnyClient,
    line: str,
    history: list[dict[str, str]],
    system_prompt: str,
    model: str,
) -> None:
    messages = _build_messages(line, system_prompt or None)
    for msg in history:
        messages.insert(-1, msg)
    try:
        resp = await client.chat(
            messages,
            model=model or None,
            temperature=0.7,
        )
        content = resp.get(
            "content",
            resp.get("response", ""),
        )
        print(f"\nloom> {content}\n")
        history.append({"role": "user", "content": line})
        history.append(
            {"role": "assistant", "content": content},
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)


async def _repl(client: AnyClient) -> None:
    """Interactive chat REPL."""
    model = os.environ.get("LOOM_MODEL", "")

    try:
        health = await client.health()
        print(f"Connected to loom-ai ({client.base_url})")
        backends = health.get("backends", {})
        llm = backends.get("llm", "none")
        print(f"LLM backend: {llm}")
    except Exception as exc:
        print(
            f"Warning: could not connect to {client.base_url}: {exc}",
            file=sys.stderr,
        )

    print("Type a message to chat, or use commands:")
    print("  /models     — list available models")
    print("  /model NAME — switch model")
    print("  /system MSG — set system prompt")
    print("  /consensus  — multi-model consensus mode")
    print("  /clear      — clear conversation")
    print("  /quit       — exit")
    print()

    history: list[dict[str, str]] = []
    system_prompt: str = ""

    while True:
        try:
            line = (await asyncio.to_thread(input, "you> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        if line in ("/quit", "/exit"):
            break
        elif line == "/clear":
            history.clear()
            print("Conversation cleared.")
        elif line == "/models":
            await _repl_models(client, model)
        elif line.startswith("/model "):
            model = line[7:].strip()
            print(f"Model set to: {model}")
        elif line.startswith("/system "):
            system_prompt = line[8:].strip()
            print("System prompt set.")
        elif line == "/consensus":
            await _repl_consensus(client)
        else:
            await _repl_chat(
                client,
                line,
                history,
                system_prompt,
                model,
            )


async def _async_main(args: argparse.Namespace) -> None:
    client = await _build_client(args)

    if args.command == "chat":
        await _cmd_chat(client, args)
    elif args.command == "consensus":
        await _cmd_consensus(client, args)
    elif args.command == "models":
        await _cmd_models(client)
    elif args.command == "health":
        await _cmd_health(client)
    elif args.command == "ready":
        await _cmd_ready(client)
    elif args.command == "search":
        await _cmd_search(client, args)
    elif args.command == "docs":
        await _cmd_docs(client, args)
    elif args.command == "secrets":
        await _cmd_secrets(client, args)
    elif args.command == "graph":
        await _cmd_graph(client, args)
    else:
        await _repl(client)


def main() -> None:
    parser = _make_parser()
    args = parser.parse_args()
    asyncio.run(_async_main(args))
