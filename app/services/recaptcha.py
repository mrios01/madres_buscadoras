from urllib.parse import urlencode

import google.auth
from google.auth.transport.requests import Request
import tornado.escape
import tornado.httpclient

from app.core.config import get_settings


_RECAPTCHA_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"
_RECAPTCHA_ENTERPRISE_URL = (
    "https://recaptchaenterprise.googleapis.com/v1/projects"
)


def _enterprise_access_token() -> str:
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(Request())
    if not credentials.token:
        raise RuntimeError("recaptcha_enterprise_auth_failed")
    return str(credentials.token)


async def _verify_classic(
    token: str,
    expected_action: str,
    remote_ip: str | None,
) -> dict:
    settings = get_settings()

    body = urlencode(
        {
            "secret": settings.recaptcha_secret_key,
            "response": token,
            "remoteip": remote_ip or "",
        }
    )

    request = tornado.httpclient.HTTPRequest(
        url=_RECAPTCHA_VERIFY_URL,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=body,
    )

    client = tornado.httpclient.AsyncHTTPClient()
    response = await client.fetch(request, raise_error=False)
    if response.code != 200:
        raise ValueError("recaptcha_verification_failed")

    payload = tornado.escape.json_decode(response.body)
    if not payload.get("success"):
        raise ValueError("recaptcha_failed")

    if payload.get("action") != expected_action:
        raise ValueError("recaptcha_action_mismatch")

    score = float(payload.get("score") or 0.0)
    if score < settings.recaptcha_min_score:
        raise ValueError("recaptcha_low_score")

    return payload


async def _verify_enterprise(
    token: str,
    expected_action: str,
    remote_ip: str | None,
) -> dict:
    settings = get_settings()
    project_id = settings.recaptcha_project_id or settings.gcs_project_id
    if not project_id:
        raise RuntimeError("recaptcha_project_not_configured")
    if not settings.recaptcha_site_key:
        raise RuntimeError("recaptcha_site_key_not_configured")

    access_token = _enterprise_access_token()
    request_payload = {
        "event": {
            "token": token,
            "siteKey": settings.recaptcha_site_key,
            "expectedAction": expected_action,
        }
    }
    if remote_ip:
        request_payload["event"]["userIpAddress"] = remote_ip

    request = tornado.httpclient.HTTPRequest(
        url=(f"{_RECAPTCHA_ENTERPRISE_URL}/{project_id}/assessments"),
        method="POST",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        body=tornado.escape.json_encode(request_payload),
    )

    client = tornado.httpclient.AsyncHTTPClient()
    response = await client.fetch(request, raise_error=False)
    if response.code != 200:
        raise ValueError("recaptcha_enterprise_verification_failed")

    payload = tornado.escape.json_decode(response.body)
    token_props = payload.get("tokenProperties") or {}
    if not token_props.get("valid"):
        raise ValueError("recaptcha_failed")

    if token_props.get("action") != expected_action:
        raise ValueError("recaptcha_action_mismatch")

    risk = payload.get("riskAnalysis") or {}
    score = float(risk.get("score") or 0.0)
    if score < settings.recaptcha_min_score:
        raise ValueError("recaptcha_low_score")

    return payload


async def verify_recaptcha_v3(
    token: str,
    expected_action: str,
    remote_ip: str | None,
) -> dict:
    settings = get_settings()
    if settings.recaptcha_secret_key:
        return await _verify_classic(token, expected_action, remote_ip)

    if settings.recaptcha_site_key:
        return await _verify_enterprise(token, expected_action, remote_ip)

    raise RuntimeError("recaptcha_not_configured")
