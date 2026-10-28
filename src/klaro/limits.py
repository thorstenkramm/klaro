"""Single source of truth for every client-visible size and count limit."""

from __future__ import annotations

from typing import Final

MAX_BODY_BYTES: Final = 65_536
MAX_ANSWER_BODY_BYTES: Final = 524_288

MIN_QUESTIONS: Final = 1
MAX_QUESTIONS: Final = 20
MIN_OPTIONS: Final = 2
MAX_OPTIONS: Final = 50
MAX_NAME_CHARACTERS: Final = 500
MAX_OPTION_CHARACTERS: Final = 2_000
MAX_TEXT_CHARACTERS: Final = 2_000
MAX_QUESTIONER_CHARACTERS: Final = 100
