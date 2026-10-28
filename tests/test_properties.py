"""Property-based tests for every parser and renderer that handles hostile input."""

from __future__ import annotations

import json
import re

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from klaro.answers import AnswerValidationError, is_consistent_answer, validate_answers
from klaro.markdown import is_text_first_option, plain_name, render_name, render_option
from klaro.models import Question, QuestionKind, SchemaValidationError, validate_questionnaire
from klaro.parsing import ParseError, parse_questionnaire_body
from klaro.records import Questionnaire

PROPERTY_SETTINGS = settings(
    max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
PRIVATE_USE = re.compile("[\ue000-\uf8ff]")
ALLOWED_NAME_TAGS = re.compile(r"</?(?:strong|em|code)>")
ALLOWED_OPTION_TAGS = re.compile(
    r"</?(?:strong|em|code|p)>|<br>|<pre tabindex=\"0\" aria-label=\"Code block\">|</pre>"
)

json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text(max_size=8),
    lambda children: (
        st.lists(children, max_size=4) | st.dictionaries(st.text(max_size=8), children, max_size=4)
    ),
    max_leaves=20,
)
question_like = st.fixed_dictionaries(
    {},
    optional={
        "name": json_values | st.text(max_size=20),
        "type": st.sampled_from(["radio", "checkbox", "text"]) | json_values,
        "answers": st.lists(st.text(max_size=10) | json_values, max_size=5) | json_values,
        "allow_other": json_values,
        "allow_comments": json_values,
        "recommendations": st.lists(st.integers(-2, 6) | json_values, max_size=4) | json_values,
    },
)


def outcome(call, expected: type[Exception]):
    """Return ``(result, None)`` or ``(None, error)`` for the one allowed exception type."""
    try:
        return call(), None
    except expected as error:
        return None, error


def assert_field_errors(error) -> None:
    assert error.fields
    assert all(error.fields.values())


markdown_text = st.lists(
    st.sampled_from([*"[]()<>!\\*_`~#-+|>.1 \n\tab&", "<b>", "</b>", "```", "    "]),
    max_size=40,
).map("".join)


@PROPERTY_SETTINGS
@given(
    body=st.binary(max_size=300), media=st.sampled_from(["application/json", "application/yaml"])
)
def test_parser_only_raises_client_errors_for_arbitrary_bytes(body: bytes, media: str) -> None:
    _, error = outcome(lambda: parse_questionnaire_body(body, media), ParseError)
    if error is not None:
        assert error.status in {400, 413, 415}


@PROPERTY_SETTINGS
@given(value=json_values, media=st.sampled_from(["application/json", "application/yaml"]))
def test_parser_accepts_every_serialized_json_value(value: object, media: str) -> None:
    # JSON is valid YAML 1.2 for these values, so both media types must decode them.
    encoded = json.dumps(value).encode()
    _, error = outcome(lambda: parse_questionnaire_body(encoded, media), ParseError)
    if error is not None:
        assert error.status == 400


@PROPERTY_SETTINGS
@given(raw=json_values | st.fixed_dictionaries({"questions": st.lists(question_like, max_size=3)}))
def test_schema_validation_only_raises_field_errors(raw: object) -> None:
    questions, error = outcome(lambda: validate_questionnaire(raw), SchemaValidationError)
    if error is not None:
        assert_field_errors(error)
    else:
        for question in questions:
            stored = Questionnaire.from_storage(
                "t" * 43,
                {
                    "version": 4,
                    "status": "awaiting_answer",
                    "created_at": "2026-10-25T12:00:00Z",
                    "expires_at": "2026-10-25T12:01:00Z",
                    "questioner": "Q",
                    "questions": [question.as_dict()],
                    "answers": None,
                    "answered_at": None,
                    "pushover_request": None,
                },
            )
            assert stored.questions[0] == question


QUESTIONS = (
    Question(id="q1", name="One", kind=QuestionKind.RADIO, answers=("a", "b"), allow_other=True),
    Question(
        id="q2",
        name="Many",
        kind=QuestionKind.CHECKBOX,
        answers=("x", "y", "z"),
        allow_comments=True,
    ),
)
field_names = st.sampled_from(["q1", "q2", "q1-other", "q2-comment", "q1-comment", "q3", ""])
field_values = st.sampled_from(["1", "2", "3", "0", "01", "other", " ", "x"]) | st.text(max_size=6)


@PROPERTY_SETTINGS
@given(submission=st.dictionaries(field_names, st.lists(field_values, max_size=3), max_size=6))
def test_answer_validation_returns_consistent_answers_or_field_errors(
    submission: dict[str, list[str]],
) -> None:
    answers, error = outcome(lambda: validate_answers(QUESTIONS, submission), AnswerValidationError)
    if error is not None:
        assert_field_errors(error)
    else:
        assert set(answers) == {"q1", "q2"}
        for question in QUESTIONS:
            assert is_consistent_answer(question, answers[question.id])


@PROPERTY_SETTINGS
@given(source=markdown_text)
def test_names_render_only_allowed_markup_and_never_leak_placeholders(source: str) -> None:
    rendered = str(render_name.__wrapped__(source))
    plain = plain_name.__wrapped__(source)

    assert "<" not in ALLOWED_NAME_TAGS.sub("", rendered)
    assert not PRIVATE_USE.search(rendered)
    assert not PRIVATE_USE.search(plain)


@PROPERTY_SETTINGS
@given(source=markdown_text)
def test_text_first_options_render_only_allowed_markup(source: str) -> None:
    option = "Start " + source
    if not is_text_first_option.__wrapped__(option):
        return
    rendered = render_option.__wrapped__(option)
    html = str(rendered.head) + str(rendered.body)

    assert "<" not in ALLOWED_OPTION_TAGS.sub("", html)
    assert not PRIVATE_USE.search(html)
