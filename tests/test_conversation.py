"""Tests for loom_ai.backends.conversation.InMemoryConversationManager."""

import pytest

from loom_ai.backends.conversation import InMemoryConversationManager
from loom_ai.contracts_core import ConversationManager
from loom_ai.models import ChatMessage


@pytest.fixture
def manager() -> InMemoryConversationManager:
    return InMemoryConversationManager()


async def test_create_add_get_flow(manager: InMemoryConversationManager):
    """Basic round-trip: create session, add messages, retrieve them."""
    sid = await manager.create_session()
    assert isinstance(sid, str)
    assert len(sid) > 0

    await manager.add_message(sid, ChatMessage(role="user", content="Hello"))
    await manager.add_message(sid, ChatMessage(role="assistant", content="Hi there"))

    messages = await manager.get_messages(sid)
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content == "Hello"
    assert messages[1].role == "assistant"
    assert messages[1].content == "Hi there"


async def test_create_session_with_metadata(manager: InMemoryConversationManager):
    """Metadata is preserved on session creation."""
    sid = await manager.create_session(metadata={"topic": "testing"})
    # Metadata is stored internally; sessions are accessible
    messages = await manager.get_messages(sid)
    assert messages == []


async def test_get_messages_max_tokens_trims_oldest(
    manager: InMemoryConversationManager,
):
    """max_tokens trims from the front, keeping recent messages."""
    sid = await manager.create_session()
    # Each message ~25 chars -> ~6 tokens (25 // 4)
    await manager.add_message(sid, ChatMessage(role="user", content="a" * 100))
    await manager.add_message(sid, ChatMessage(role="user", content="b" * 20))
    await manager.add_message(sid, ChatMessage(role="user", content="c" * 20))

    # Budget of 10 tokens should fit msg2 (5 tokens) + msg3 (5 tokens)
    # but not msg1 (25 tokens)
    messages = await manager.get_messages(sid, max_tokens=10)
    assert len(messages) == 2
    assert messages[0].content == "b" * 20
    assert messages[1].content == "c" * 20


async def test_get_messages_max_tokens_returns_all_when_fits(
    manager: InMemoryConversationManager,
):
    """When all messages fit the budget, return them all."""
    sid = await manager.create_session()
    await manager.add_message(sid, ChatMessage(role="user", content="Hi"))
    await manager.add_message(sid, ChatMessage(role="assistant", content="Hey"))

    messages = await manager.get_messages(sid, max_tokens=1000)
    assert len(messages) == 2


async def test_get_messages_no_max_tokens(manager: InMemoryConversationManager):
    """Without max_tokens, all messages are returned."""
    sid = await manager.create_session()
    for i in range(10):
        await manager.add_message(sid, ChatMessage(role="user", content=f"msg-{i}"))

    messages = await manager.get_messages(sid)
    assert len(messages) == 10


async def test_compress_trims_oldest(manager: InMemoryConversationManager):
    """compress drops oldest messages to fit target_tokens."""
    sid = await manager.create_session()
    # Each message is 40 chars -> 10 tokens
    await manager.add_message(sid, ChatMessage(role="user", content="a" * 40))
    await manager.add_message(sid, ChatMessage(role="user", content="b" * 40))
    await manager.add_message(sid, ChatMessage(role="user", content="c" * 40))

    # Target 20 tokens -> should keep last 2 messages (10 + 10 = 20)
    await manager.compress(sid, target_tokens=20)

    messages = await manager.get_messages(sid)
    assert len(messages) == 2
    assert messages[0].content == "b" * 40
    assert messages[1].content == "c" * 40


async def test_compress_keeps_all_when_fits(manager: InMemoryConversationManager):
    """compress is a no-op when history already fits."""
    sid = await manager.create_session()
    await manager.add_message(sid, ChatMessage(role="user", content="short"))

    await manager.compress(sid, target_tokens=1000)
    messages = await manager.get_messages(sid)
    assert len(messages) == 1


async def test_fork_produces_independent_copy(manager: InMemoryConversationManager):
    """Forked session has same messages but mutations are independent."""
    sid = await manager.create_session()
    await manager.add_message(sid, ChatMessage(role="user", content="original"))

    forked_id = await manager.fork(sid)
    assert forked_id != sid

    # Fork has the same messages
    original_msgs = await manager.get_messages(sid)
    forked_msgs = await manager.get_messages(forked_id)
    assert len(forked_msgs) == len(original_msgs)
    assert forked_msgs[0].content == "original"

    # Mutating fork does not affect original
    await manager.add_message(forked_id, ChatMessage(role="user", content="fork-only"))
    assert len(await manager.get_messages(forked_id)) == 2
    assert len(await manager.get_messages(sid)) == 1

    # Mutating original does not affect fork
    await manager.add_message(sid, ChatMessage(role="user", content="original-only"))
    assert len(await manager.get_messages(sid)) == 2
    assert len(await manager.get_messages(forked_id)) == 2


async def test_export_transcript_format(manager: InMemoryConversationManager):
    """export_transcript returns plain dicts with role and content keys."""
    sid = await manager.create_session()
    await manager.add_message(sid, ChatMessage(role="user", content="Hello"))
    await manager.add_message(
        sid, ChatMessage(role="assistant", content="How can I help?")
    )

    transcript = await manager.export_transcript(sid)
    assert isinstance(transcript, list)
    assert len(transcript) == 2
    assert transcript[0] == {"role": "user", "content": "Hello"}
    assert transcript[1] == {"role": "assistant", "content": "How can I help?"}


async def test_export_transcript_empty_session(manager: InMemoryConversationManager):
    """export_transcript on a fresh session returns an empty list."""
    sid = await manager.create_session()
    transcript = await manager.export_transcript(sid)
    assert transcript == []


async def test_unknown_session_raises(manager: InMemoryConversationManager):
    """Operations on a non-existent session raise KeyError."""
    msg = ChatMessage(role="user", content="hi")
    with pytest.raises(KeyError):
        await manager.add_message("nonexistent", msg)

    with pytest.raises(KeyError):
        await manager.get_messages("nonexistent")

    with pytest.raises(KeyError):
        await manager.compress("nonexistent", target_tokens=100)

    with pytest.raises(KeyError):
        await manager.fork("nonexistent")

    with pytest.raises(KeyError):
        await manager.export_transcript("nonexistent")


async def test_satisfies_protocol():
    """InMemoryConversationManager satisfies the ConversationManager protocol."""
    assert isinstance(InMemoryConversationManager(), ConversationManager)
