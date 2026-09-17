"""
Smart AI Job Agent — Mobile & WhatsApp Notifier Utility
Candidate: Janardhan Devarala
========================================================
Dispatches real-time application updates to Janardhan's mobile (WhatsApp/SMS via Twilio)
and email notifications.
"""

from __future__ import annotations

from typing import Any
import structlog

logger = structlog.get_logger(__name__)


class MobileNotifier:
    """
    Mobile Notifier — Twilio WhatsApp & SMS integration for Janardhan Devarala.
    """

    def __init__(
        self,
        account_sid: str = "",
        auth_token: str = "",
        to_phone: str = "+917093435561",
    ) -> None:
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.to_phone = to_phone
        self._twilio_client = None

        if account_sid and auth_token:
            try:
                from twilio.rest import Client
                self._twilio_client = Client(account_sid, auth_token)
                logger.info("notifier.twilio_ready", phone=to_phone)
            except Exception as e:
                logger.warning("notifier.twilio_init_failed", error=str(e))

    async def notify_application_submitted(
        self, job_title: str, company: str, location: str, fit_score: float, status: str = "APPLIED"
    ) -> dict[str, Any]:
        """
        Send instant application alert to mobile.
        """
        msg = (
            f"🚀 *Smart AI Job Agent Alert*\n\n"
            f"✅ *Application Sent!*\n"
            f"📌 *Role:* {job_title}\n"
            f"🏢 *Company:* {company}\n"
            f"📍 *Location:* {location}\n"
            f"✨ *ATS Fit Score:* {fit_score}%\n"
            f"📑 *Status:* {status}\n\n"
            f"Janardhan, your agent has submitted an ATS-optimized application & cover letter!"
        )

        sent_whatsapp = False
        if self._twilio_client:
            try:
                self._twilio_client.messages.create(
                    body=msg,
                    from_="whatsapp:+14155238886",
                    to=f"whatsapp:{self.to_phone}",
                )
                sent_whatsapp = True
                logger.info("notifier.whatsapp_sent", company=company, role=job_title)
            except Exception as e:
                logger.error("notifier.whatsapp_send_error", error=str(e))

        logger.info("notifier.alert_logged", message=msg)
        return {"status": "dispatched", "sent_whatsapp": sent_whatsapp, "message": msg}
