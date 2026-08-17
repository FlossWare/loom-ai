"""Conformance tests for ResourceProvider implementations.

Any backend that satisfies the ResourceProvider protocol should pass all
tests in this module.  Override the ``resource_provider`` fixture in a
downstream ``conftest.py`` to plug in a different implementation.
"""

from __future__ import annotations

import pytest

from loom_ai.models import ResourceContent, ResourceDefinition

# -- list_resources() ------------------------------------------------------


async def test_list_resources_returns_list(resource_provider):
    """list_resources() returns a list of ResourceDefinition instances."""
    resources = await resource_provider.list_resources()

    assert isinstance(resources, list)
    assert len(resources) >= 1
    assert all(isinstance(r, ResourceDefinition) for r in resources)


async def test_resource_definition_has_uri_and_name(resource_provider):
    """Each ResourceDefinition has a non-empty uri and name."""
    resources = await resource_provider.list_resources()

    for resource in resources:
        assert isinstance(resource.uri, str)
        assert len(resource.uri) > 0
        assert isinstance(resource.name, str)
        assert len(resource.name) > 0


# -- read_resource() ------------------------------------------------------


async def test_read_resource_returns_content(resource_provider):
    """read_resource() returns a ResourceContent instance."""
    resources = await resource_provider.list_resources()
    uri = resources[0].uri

    content = await resource_provider.read_resource(uri)

    assert isinstance(content, ResourceContent)
    assert content.uri == uri
    assert isinstance(content.mime_type, str)
    assert len(content.mime_type) > 0


async def test_read_resource_has_nonempty_content(resource_provider):
    """The content field of a ResourceContent is non-empty."""
    resources = await resource_provider.list_resources()
    uri = resources[0].uri

    result = await resource_provider.read_resource(uri)

    assert result.content
    assert len(result.content) > 0


async def test_read_resource_unknown_raises(resource_provider):
    """Reading an unknown URI raises KeyError."""
    with pytest.raises(KeyError):
        await resource_provider.read_resource("loom://does-not-exist")
