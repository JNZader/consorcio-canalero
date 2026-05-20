"""Async email sender — opt-in via SMTP_HOST.

When ``settings.smtp_host`` is empty (default in dev / unconfigured
deploys) every helper here is a no-op that just logs. That keeps the
rest of the codebase free of SMTP branches: callers always invoke
``send_email(...)``, and the integration silently degrades to "logged
but not delivered" until the operator wires real SMTP credentials.

Templates are kept inline as small Python f-strings — adding a real
template engine for two messages was out of scope for Phase 2.
"""

from __future__ import annotations

import asyncio
import logging
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    """True when there's enough SMTP config to actually send mail."""
    return bool(settings.smtp_host and settings.smtp_from)


async def send_email(
    *,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> None:
    """Send a single email. Silent no-op when SMTP isn't configured.

    Always logs the attempt (without the body) so operators can trace
    delivery decisions in the structured log.
    """
    if not is_configured():
        logger.info(
            "email send skipped (SMTP not configured)",
            extra={"to_email_domain": to_email.split("@", 1)[-1], "subject": subject},
        )
        return

    msg = EmailMessage()
    msg["From"] = (
        f"{settings.smtp_from_name} <{settings.smtp_from}>"
        if settings.smtp_from_name
        else settings.smtp_from
    )
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    try:
        import aiosmtplib
    except ImportError:
        # Lib not installed in this environment — log and bail. The
        # caller never observes a failure (we don't want a missed
        # email to abort the registration flow).
        logger.warning(
            "email send aborted: aiosmtplib not installed", extra={"subject": subject}
        )
        return

    # aiosmtplib treats ``start_tls`` and ``use_tls`` as mutually
    # exclusive flags. If the operator set both we honour ``use_tls``
    # (the stricter mode) and log a warning — the config fail-fast
    # may add an explicit error later.
    use_tls = settings.smtp_use_tls
    start_tls = settings.smtp_use_starttls and not use_tls
    if settings.smtp_use_tls and settings.smtp_use_starttls:
        logger.warning(
            "SMTP_USE_TLS and SMTP_USE_STARTTLS both true — using SMTPS only"
        )
    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username or None,
            password=settings.smtp_password or None,
            start_tls=start_tls,
            use_tls=use_tls,
            timeout=15,
        )
        logger.info(
            "email sent",
            extra={
                "to_email_domain": to_email.split("@", 1)[-1],
                "subject": subject,
            },
        )
    except Exception as exc:  # noqa: BLE001 — never abort the caller
        # Don't propagate — a flaky SMTP provider must not block the
        # user-facing flow (register / forgot-password).
        logger.exception(
            "email send failed", extra={"subject": subject, "error": str(exc)}
        )


def send_email_blocking(
    *,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> None:
    """Sync wrapper for places that don't have an event loop handy.

    Spins up a one-shot loop. Use ``send_email`` directly from async
    code paths to avoid the overhead.
    """
    asyncio.run(
        send_email(
            to_email=to_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )
    )


# ─────────────────────────────────────────────────────────────────────
# Templates
# ─────────────────────────────────────────────────────────────────────


def build_verification_email(code: str, frontend_url: str) -> dict[str, str]:
    """Email for the post-register email-verification flow.

    Phase 5 / F5-E: the email carries a short ``code``, NOT the JWT
    verify token. The SPA exchanges the code for the real token via
    ``POST /auth/exchange-code``. Provider logs retaining the body
    for 30+ days now only see a code that expires in 15 minutes and
    is one-shot.
    """
    link = f"{frontend_url.rstrip('/')}/auth/verify?code={code}"
    text = (
        "Hola,\n\n"
        "Recibimos tu registro en el Consorcio Canalero 10 de Mayo. "
        "Para activar tu cuenta, abrí este enlace:\n\n"
        f"{link}\n\n"
        f"O ingresá este código en la página de verificación:\n\n"
        f"    {code}\n\n"
        "El código expira en 15 minutos.\n"
        "Si no te registraste, ignorá este correo.\n\n"
        "— Consorcio Canalero 10 de Mayo"
    )
    html = (
        "<p>Hola,</p>"
        "<p>Recibimos tu registro en el Consorcio Canalero 10 de Mayo. "
        "Para activar tu cuenta, hacé click acá:</p>"
        f'<p><a href="{link}">Verificar mi correo</a></p>'
        f"<p>O ingresá este código en la página de verificación: "
        f'<strong style="font-family:monospace;font-size:18px;letter-spacing:2px">{code}</strong></p>'
        "<p>El código expira en 15 minutos.<br>"
        "Si no te registraste, ignorá este correo.</p>"
        '<hr><p style="color:#666;font-size:12px">Consorcio Canalero 10 de Mayo</p>'
    )
    return {
        "subject": "Verificá tu correo — Consorcio Canalero",
        "body_text": text,
        "body_html": html,
    }


def build_reset_email(code: str, frontend_url: str) -> dict[str, str]:
    """Email for the forgot-password flow.

    Phase 5 / F5-E: same hardening as the verify email — body carries
    a short ``code``, not the JWT reset token.
    """
    link = f"{frontend_url.rstrip('/')}/auth/reset?code={code}"
    text = (
        "Hola,\n\n"
        "Alguien (probablemente vos) pidió restablecer la contraseña de "
        "tu cuenta en el Consorcio Canalero. Abrí este enlace para "
        "definir una nueva contraseña:\n\n"
        f"{link}\n\n"
        f"O ingresá este código en la página de restablecimiento:\n\n"
        f"    {code}\n\n"
        "El código expira en 15 minutos. Si no fuiste vos, podés "
        "ignorar este correo — tu contraseña no cambió.\n\n"
        "— Consorcio Canalero 10 de Mayo"
    )
    html = (
        "<p>Hola,</p>"
        "<p>Alguien (probablemente vos) pidió restablecer tu "
        "contraseña. Hacé click acá para elegir una nueva:</p>"
        f'<p><a href="{link}">Restablecer contraseña</a></p>'
        f"<p>O ingresá este código: "
        f'<strong style="font-family:monospace;font-size:18px;letter-spacing:2px">{code}</strong></p>'
        "<p>El código expira en 15 minutos. Si no fuiste vos, podés "
        "ignorar este correo — tu contraseña no cambió.</p>"
        '<hr><p style="color:#666;font-size:12px">Consorcio Canalero 10 de Mayo</p>'
    )
    return {
        "subject": "Restablecer contraseña — Consorcio Canalero",
        "body_text": text,
        "body_html": html,
    }
