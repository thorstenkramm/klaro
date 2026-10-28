"""Public HTTP routes, error presentation, and response hardening."""

from __future__ import annotations

from datetime import UTC

from flask import (
    Blueprint,
    Response,
    current_app,
    g,
    jsonify,
    make_response,
    render_template,
    request,
)
from werkzeug.exceptions import InternalServerError, RequestEntityTooLarge

from klaro.answers import AnswerValidationError, validate_answers
from klaro.assets import static_cache_control
from klaro.filestore import QuestionnaireNotFound, QuestionnaireStateConflict
from klaro.limits import MAX_ANSWER_BODY_BYTES, MAX_BODY_BYTES
from klaro.logging_utils import redact_text
from klaro.models import SchemaValidationError, validate_questionnaire
from klaro.parsing import ParseError, parse_questionnaire_body
from klaro.pushover import PushoverError, PushoverRecipientRejected
from klaro.records import Questionnaire, Status, format_time
from klaro.responses import (
    error_response,
    explicitly_wants_html,
    is_htmx,
    not_found,
    state_conflict,
    wants_json,
    wants_sse,
)
from klaro.runtime import get_runtime
from klaro.sse import sse_response
from klaro.validation import validate_creation_headers

CONTENT_SECURITY_POLICY = (
    "default-src 'none'; style-src 'self'; script-src 'self'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
    "form-action 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'"
)

PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), "
    "microphone=(), payment=(), usb=()"
)
SECURITY_HEADERS = {
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "Permissions-Policy": PERMISSIONS_POLICY,
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}

bp = Blueprint("questionnaires", __name__)


@bp.after_app_request
def secure_response(response: Response) -> Response:
    # Questionnaire responses carry secrets and state; only versioned assets may be cached.
    is_asset = request.endpoint == "static" and response.status_code in {200, 304}
    response.headers["Cache-Control"] = static_cache_control() if is_asset else "no-store"
    response.headers.update(SECURITY_HEADERS)
    current_app.logger.info(
        "%s %s %d", request.method, redact_text(request.full_path), response.status_code
    )
    return response


@bp.app_errorhandler(RequestEntityTooLarge)
def body_too_large(_: RequestEntityTooLarge) -> Response:
    limit = request.max_content_length or MAX_BODY_BYTES
    # Only the browser answer form has a page to return to; every other caller is an API.
    if g.get("answer_form") and not is_htmx() and not wants_json():
        return make_response(render_template("request_too_large.html", limit=limit), 413)
    return error_response("payload_too_large", f"Request body exceeds {limit:,} bytes.", 413)


@bp.app_errorhandler(InternalServerError)
def internal_error(error: InternalServerError) -> Response | InternalServerError:
    if explicitly_wants_html():
        return error
    return error_response("internal_error", "An unexpected error occurred.", 500)


def render_record(
    record: Questionnaire,
    *,
    status: int = 200,
    errors: dict[str, list[str]] | None = None,
    selected: dict[str, list[str]] | None = None,
) -> Response:
    template = "_questionnaire_fragment.html" if is_htmx() else "questionnaire.html"
    return make_response(
        render_template(
            template,
            record=record,
            expires_at=format_time(record.expires_at),
            expires_label=record.expires_at.astimezone(UTC).strftime("%a, %d %b · %H:%M UTC"),
            errors=errors or {},
            selected=selected or {},
        ),
        status,
    )


@bp.post("/")
def create_questionnaire() -> Response:
    runtime = get_runtime()
    client_ip = runtime.client_ips.resolve(
        request.remote_addr or "127.0.0.1", request.headers.get("X-Forwarded-For")
    )
    abuse = runtime.abuse.check(client_ip)
    if not abuse.allowed:
        return error_response(
            abuse.code or "rate_limited",
            "Too many creation attempts; retry later.",
            429,
            headers={"Retry-After": str(abuse.retry_after)},
        )

    try:
        recipient, questioner = validate_creation_headers(
            request.headers.get("X-Pushover-User"), request.headers.get("X-Questioner")
        )
        allowed_questioners = runtime.config.klaro.questioners
        if allowed_questioners is not None and questioner not in allowed_questioners:
            return error_response("forbidden", "This questioner is not allowed.", 403)
        body = request.get_data(cache=False)
        decoded = parse_questionnaire_body(body, request.content_type or "")
        questions = validate_questionnaire(decoded)
    except SchemaValidationError as exc:
        return error_response("invalid_request", "The request is invalid.", 400, fields=exc.fields)
    except ParseError as exc:
        return error_response(exc.code, "The request body is invalid.", exc.status)

    try:
        created = runtime.creator.create(
            recipient=recipient, questioner=questioner, questions=questions
        )
    except PushoverRecipientRejected as exc:
        runtime.abuse.record_recipient_rejection(client_ip)
        current_app.logger.warning("Pushover rejected a recipient; pending questionnaire discarded")
        return error_response(exc.code, "Pushover rejected the recipient key.", exc.http_status)
    except PushoverError as exc:
        # Only recipient rejections change backoff; every other failure leaves it untouched.
        current_app.logger.warning(
            "Pushover notification failed (%s); pending questionnaire discarded",
            type(exc).__name__,
        )
        return error_response(
            exc.code,
            "Pushover did not accept the notification; the questionnaire was not published.",
            exc.http_status,
        )
    runtime.abuse.record_acceptance(client_ip)
    if wants_sse():
        return Response(status=303, headers={"Location": f"/{created.record.token}"})
    response = jsonify({"url": created.url, "expires_at": format_time(created.record.expires_at)})
    response.status_code = 201
    return response


@bp.get("/<token>")
def retrieve_questionnaire(token: str) -> Response:
    runtime = get_runtime()
    answer_only = request.args.get("answer_only") == "1"
    if not answer_only and wants_sse():
        try:
            subscription = runtime.subscribers.register(token)
        except QuestionnaireNotFound:
            return not_found()
        return sse_response(
            subscription,
            url=runtime.config.klaro.questionnaire_url(token),
            heartbeat_seconds=runtime.config.klaro.sse_heartbeat_seconds,
            clock=runtime.clock,
        )
    try:
        record = runtime.store.get_public(token)
    except QuestionnaireNotFound:
        return not_found()
    if answer_only:
        return jsonify(record.answer_only_dict())
    if wants_json():
        return jsonify(record.public_dict())
    return render_record(record)


@bp.post("/<token>")
def update_questionnaire(token: str) -> Response:
    if request.args.get("confirmed") == "1":
        return confirm_questionnaire(token)
    return submit_answer_form(token)


def confirm_questionnaire(token: str) -> Response:
    request.get_data(cache=False)
    try:
        get_runtime().store.confirm(token)
    except QuestionnaireNotFound:
        return not_found()
    except QuestionnaireStateConflict:
        return state_conflict()
    return jsonify({"status": "confirmed"})


def submit_answer_form(token: str) -> Response:
    """Accept the browser answer form; responses are HTML pages or HTMX fragments."""
    store = get_runtime().store
    g.answer_form = True
    request.max_content_length = MAX_ANSWER_BODY_BYTES
    request.max_form_memory_size = MAX_ANSWER_BODY_BYTES
    submission = request.form.to_dict(flat=False)
    try:
        record = store.get_public(token)
        if record.status is not Status.AWAITING_ANSWER:
            return state_conflict()
        answers = validate_answers(record.questions, submission)
        answered = store.submit_answers(token, answers)
    except QuestionnaireNotFound:
        return not_found()
    except QuestionnaireStateConflict:
        return state_conflict()
    except AnswerValidationError as exc:
        return render_record(record, status=422, errors=exc.fields, selected=submission)
    return render_record(answered)
