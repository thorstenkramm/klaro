"""Bounded, duplicate-safe JSON and YAML request parsing."""

from __future__ import annotations

import json
from email.message import Message
from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode

from klaro.limits import MAX_BODY_BYTES

__all__ = ["MAX_BODY_BYTES", "ParseError", "parse_questionnaire_body"]


class ParseError(ValueError):
    """A client-visible request parsing failure."""

    def __init__(self, message: str, *, status: int = 400, code: str = "invalid_request") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate object key: {key}")
        result[key] = value
    return result


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that also rejects duplicate mapping keys."""


def _yaml_mapping(
    loader: _UniqueKeySafeLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "unhashable key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _yaml_mapping)


def _media_type(content_type: str) -> tuple[str, str | None]:
    message = Message()
    message["content-type"] = content_type
    charset = message.get_param("charset", header="content-type")
    return message.get_content_type().lower(), charset if isinstance(charset, str) else None


def _decode_body(body: bytes, content_type: str) -> tuple[str, str]:
    """Validate size, media type, and encoding; return the media type and decoded text."""
    if len(body) > MAX_BODY_BYTES:
        raise ParseError(
            f"Request body exceeds {MAX_BODY_BYTES:,} bytes", status=413, code="payload_too_large"
        )
    media_type, charset = _media_type(content_type)
    if media_type not in {"application/json", "application/yaml"}:
        raise ParseError(
            "Use Content-Type application/json or application/yaml",
            status=415,
            code="unsupported_media_type",
        )
    if charset and charset.lower() not in {"utf-8", "utf8"}:
        raise ParseError("Request body charset must be UTF-8")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParseError("Request body must be valid UTF-8") from exc
    if not text.strip():
        raise ParseError("Request body must not be empty")
    return media_type, text


def parse_questionnaire_body(body: bytes, content_type: str) -> Any:
    """Parse a JSON or YAML request body without executing YAML object constructors."""
    media_type, text = _decode_body(body, content_type)
    try:
        if media_type == "application/json":
            return json.loads(text, object_pairs_hook=_json_object)
        # _UniqueKeySafeLoader subclasses yaml.SafeLoader; it only adds duplicate-key checks.
        return yaml.load(text, Loader=_UniqueKeySafeLoader)  # noqa: S506
    except (json.JSONDecodeError, yaml.YAMLError, ValueError) as exc:
        raise ParseError(f"Malformed {media_type.split('/')[-1]} request body: {exc}") from exc
    except RecursionError:
        # The thousand-frame parser traceback is noise; nesting depth is the only cause.
        raise ParseError(
            f"Malformed {media_type.split('/')[-1]} request body: nesting is too deep"
        ) from None
