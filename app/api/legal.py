from app.api._auth import SessionAwareHandler


class PrivacyHandler(SessionAwareHandler):
    async def get(self):
        self.render(
            "privacy.html",
            is_authenticated=bool(self.current_user),
        )


class TermsHandler(SessionAwareHandler):
    async def get(self):
        self.render(
            "terms.html",
            is_authenticated=bool(self.current_user),
        )


class SecurityAgreementHandler(SessionAwareHandler):
    """Show security agreement modal when user first logs in."""

    async def get(self):
        db = self.application.settings["db"]
        user = self.current_user

        if not user:
            self.redirect("/login")
            return

        # Check if user has already acknowledged the security agreement
        user_id = user.get("_id")
        user_doc = await db.users.find_one({"_id": user_id})

        needs_agreement = (
            not user_doc
            or not user_doc.get("security_agreement_acknowledged_at")
        )

        self.render(
            "security_agreement.html",
            needs_agreement=needs_agreement,
            is_authenticated=bool(self.current_user),
        )


class SecurityAcknowledgeHandler(SessionAwareHandler):
    """API endpoint to acknowledge security agreement."""

    async def post(self):
        db = self.application.settings["db"]
        user = self.current_user

        if not user:
            self.set_status(401)
            self.finish({"error": "unauthorized"})
            return

        try:
            from datetime import UTC, datetime

            user_id = user.get("_id")
            await db.users.update_one(
                {"_id": user_id},
                {
                    "$set": {
                        "security_agreement_acknowledged_at": (
                            datetime.now(UTC)
                        )
                    }
                },
            )

            self.finish({"ok": True})
        except Exception as e:
            self.set_status(500)
            self.finish({"error": str(e)})
