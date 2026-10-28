"""Explicit expected wire representations for the two-question integration fixture."""


def expected_answers(answered_at=None, drink=None, sides=None):
    return {
        "answered_at": answered_at,
        "questions": [
            {
                "name": "Drink?",
                "answered": drink,
                "other": None,
                "comment": None,
                "recommendations": [],
            },
            {
                "name": "Sides?",
                "answered": sides,
                "other": None,
                "comment": None,
                "recommendations": [],
            },
        ],
    }


def expected_full(answered_at=None, drink=None, sides=None):
    result = expected_answers(answered_at, drink, sides)
    result["expires_at"] = "2026-10-25T12:01:00Z"
    result["questions"][0].update(
        type="radio", answers=["beer", "water"], allow_other=False, allow_comments=False
    )
    result["questions"][1].update(
        type="checkbox", answers=["rice", "salad"], allow_other=False, allow_comments=False
    )
    return result


def selected_by_id(record) -> dict[str, list[str] | None]:
    """Selected offered strings per question ID, read through the public answer projection."""
    projection = record.answer_only_dict()["questions"]
    return {
        question.id: item["answered"]
        for question, item in zip(record.questions, projection, strict=True)
    }
