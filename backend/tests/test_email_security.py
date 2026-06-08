from backend.services import email_service


class _PostmarkFailure:
    status_code = 422
    text = "to=user@webflow.com token=secret-token customer transcript"


def _capture_logs(monkeypatch):
    captured_logs: list[tuple[str, tuple, dict]] = []

    def capture(message, *args, **kwargs):
        captured_logs.append((message, args, kwargs))

    monkeypatch.setattr(email_service.logger, "error", capture)
    monkeypatch.setattr(email_service.logger, "info", capture)
    return captured_logs


def test_postmark_failure_logs_only_status(monkeypatch):
    captured_logs = _capture_logs(monkeypatch)

    def fake_post(*args, **kwargs):
        return _PostmarkFailure()

    monkeypatch.setattr(email_service.settings, "POSTMARK_SERVER_TOKEN", "postmark-token")
    monkeypatch.setattr(email_service.httpx, "post", fake_post)

    email_service._send(
        {
            "To": "user@webflow.com",
            "Subject": "customer transcript token=secret-token",
            "HtmlBody": "customer transcript",
        }
    )

    assert captured_logs == [("Postmark send failed status_code=%s", (422,), {})]
    assert "user@webflow.com" not in str(captured_logs)
    assert "secret-token" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)


def test_missing_postmark_token_log_excludes_subject(monkeypatch):
    captured_logs = _capture_logs(monkeypatch)
    monkeypatch.setattr(email_service.settings, "POSTMARK_SERVER_TOKEN", "")

    email_service._send(
        {
            "To": "user@webflow.com",
            "Subject": "customer transcript token=secret-token",
            "HtmlBody": "customer transcript",
        }
    )

    assert captured_logs == [("Skipping email because Postmark token is not configured", (), {})]
    assert "user@webflow.com" not in str(captured_logs)
    assert "secret-token" not in str(captured_logs)
    assert "customer transcript" not in str(captured_logs)
