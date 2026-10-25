"""Flask application factory and public HTTP routes."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC
from typing import Any

from flask import Flask, Response, jsonify, make_response, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge

from klaro.abuse import CreationAbuseControls
from klaro.answers import AnswerValidationError, validate_answers
from klaro.client_ip import ClientIPResolver
from klaro.clock import Clock, SystemClock
from klaro.config import Config, load_config
from klaro.creation import Notifier, QuestionnaireCreator
from klaro.logging_utils import install_redacting_filter, redact_text
from klaro.models import SchemaValidationError, validate_questionnaire
from klaro.parsing import MAX_BODY_BYTES, ParseError, parse_questionnaire_body
from klaro.pushover import PushoverClient, PushoverError, PushoverRecipientRejected
from klaro.scheduler import CleanupScheduler
from klaro.sse import sse_response
from klaro.storage import (
    FileStore,
    Questionnaire,
    QuestionnaireNotFound,
    QuestionnaireStateConflict,
    format_time,
    generate_token,
)
from klaro.subscribers import SubscriberHub
from klaro.validation import validate_creation_headers


@dataclass
class Runtime:
    config: Config
    clock: Clock
    store: FileStore
    subscribers: SubscriberHub
    creator: QuestionnaireCreator
    abuse: CreationAbuseControls
    client_ips: ClientIPResolver
    scheduler: CleanupScheduler


def error_response(
    code: str,
    message: str,
    status: int,
    *,
    fields: dict[str, list[str]] | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    error: dict[str, Any] = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    response = jsonify({"error": error})
    response.status_code = status
    if headers:
        response.headers.update(headers)
    return response


def not_found() -> Response:
    return error_response("not_found", "Questionnaire not found.", 404)


def state_conflict() -> Response:
    return error_response(
        "state_conflict", "The questionnaire is not in a state that allows this operation.", 409
    )


def _wants_json() -> bool:
    return request.accept_mimetypes["application/json"] > request.accept_mimetypes["text/html"]


def _wants_sse() -> bool:
    event_stream = request.accept_mimetypes["text/event-stream"]
    return event_stream > max(
        request.accept_mimetypes["application/json"],
        request.accept_mimetypes["text/html"],
    )


def create_app(
    config: Config | None = None,
    *,
    clock: Clock | None = None,
    notifier: Notifier | None = None,
    token_factory: Callable[[], str] = generate_token,
    start_scheduler: bool = False,
) -> Flask:
    selected = config or load_config()
    runtime_clock = clock or SystemClock()
    store = FileStore(selected.klaro.data_dir, token_factory=token_factory, clock=runtime_clock)
    subscribers = SubscriberHub(store)
    actual_notifier = notifier or PushoverClient(selected.pushover)
    runtime = Runtime(
        config=selected,
        clock=runtime_clock,
        store=store,
        subscribers=subscribers,
        creator=QuestionnaireCreator(selected, store, actual_notifier),
        abuse=CreationAbuseControls(runtime_clock),
        client_ips=ClientIPResolver(selected.klaro.trusted_proxies),
        scheduler=CleanupScheduler(store),
    )

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_BODY_BYTES
    app.extensions["klaro"] = runtime
    for logger in (
        app.logger,
        logging.getLogger("gunicorn.access"),
        logging.getLogger("gunicorn.error"),
        logging.getLogger("werkzeug"),
    ):
        install_redacting_filter(logger)

    @app.after_request
    def secure_response(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'self'; script-src 'self'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
            "form-action 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'"
        )
        app.logger.info(
            "%s %s %d", request.method, redact_text(request.full_path), response.status_code
        )
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def body_too_large(_: RequestEntityTooLarge) -> Response:
        return error_response("payload_too_large", "Request body exceeds 65,536 bytes.", 413)

    def render_record(
        record: Questionnaire,
        *,
        status: int = 200,
        errors: dict[str, list[str]] | None = None,
        selected: dict[str, list[str]] | None = None,
    ) -> Response:
        template = (
            "_questionnaire_fragment.html"
            if request.headers.get("HX-Request") == "true"
            else "questionnaire.html"
        )
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

    @app.post("/")
    def create_questionnaire() -> Response:
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
            allowed_questioners = selected.klaro.questioners
            if allowed_questioners is not None and questioner not in allowed_questioners:
                return error_response("forbidden", "This questioner is not allowed.", 403)
            body = request.get_data(cache=False)
            decoded = parse_questionnaire_body(body, request.content_type or "")
            questions = validate_questionnaire(decoded)
        except SchemaValidationError as exc:
            return error_response(
                "invalid_request", "The request is invalid.", 400, fields=exc.fields
            )
        except ParseError as exc:
            return error_response(exc.code, "The request body is invalid.", exc.status)

        try:
            created = runtime.creator.create(
                recipient=recipient, questioner=questioner, questions=questions
            )
        except PushoverRecipientRejected:
            runtime.abuse.record_recipient_rejection(client_ip)
            app.logger.warning("Pushover rejected a recipient; pending questionnaire discarded")
            return error_response("recipient_rejected", "Pushover rejected the recipient key.", 422)
        except PushoverError as exc:
            runtime.abuse.record_other_failure(client_ip)
            app.logger.warning(
                "Pushover notification failed (%s); pending questionnaire discarded",
                type(exc).__name__,
            )
            return error_response(
                "pushover_unavailable",
                "Pushover did not accept the notification; the questionnaire was not published.",
                502,
            )
        runtime.abuse.record_acceptance(client_ip)
        return jsonify(
            {
                "url": created.url,
                "expires_at": format_time(created.record.expires_at),
            }
        ), 201

    @app.get("/<token>")
    def retrieve_questionnaire(token: str) -> Response:
        if request.args.get("answer_only") != "1" and _wants_sse():
            try:
                subscription = runtime.subscribers.register(token)
            except QuestionnaireNotFound:
                return not_found()
            return sse_response(
                subscription,
                heartbeat_seconds=selected.klaro.sse_heartbeat_seconds,
                clock=runtime_clock,
            )
        try:
            record = runtime.store.get_public(token)
        except QuestionnaireNotFound:
            return not_found()
        if request.args.get("answer_only") == "1":
            return jsonify({"status": record.status, "answers": record.answer_dict()})
        if _wants_json():
            return jsonify(record.public_dict())
        return render_record(record)

    @app.post("/<token>")
    def update_questionnaire(token: str) -> Response:
        if request.args.get("confirmed") == "1":
            try:
                runtime.store.confirm(token)
            except QuestionnaireNotFound:
                return not_found()
            except QuestionnaireStateConflict:
                return state_conflict()
            return jsonify({"status": "confirmed"})

        submission = request.form.to_dict(flat=False)
        try:
            record = runtime.store.get_public(token)
            if record.status != "awaiting_answer":
                return state_conflict()
            answers = validate_answers(record.questions, submission)
            answered = runtime.store.submit_answers(token, answers)
        except QuestionnaireNotFound:
            return not_found()
        except QuestionnaireStateConflict:
            return state_conflict()
        except AnswerValidationError as exc:
            return render_record(record, status=422, errors=exc.fields, selected=submission)
        return render_record(answered)

    if start_scheduler:
        runtime.scheduler.start()
    return app
