import tornado.escape
import tornado.web

from app.api._auth import SessionAwareHandler
from app.core.config import get_settings
from app.services.missing_persons import list_public_missing_persons


class GoogleAuthDemoHandler(tornado.web.RequestHandler):
    async def get(self):
        settings = get_settings()
        client_id = settings.google_client_id or ""
        recaptcha_site_key = settings.recaptcha_site_key or ""
        recaptcha_script = (
            ""
            if not recaptcha_site_key
            else (
                "<script src='https://www.google.com/recaptcha/api.js"
                f"?render={recaptcha_site_key}'></script>"
            )
        )

        html = f"""<!doctype html>
<html>
  <head>
    <meta charset='utf-8' />
    <meta name='viewport' content='width=device-width, initial-scale=1' />
    <title>Marzlive Google Auth Demo</title>
    <script src='https://accounts.google.com/gsi/client' async defer></script>
    {recaptcha_script}
    <style>
      body {{
        font-family: system-ui, sans-serif;
        max-width: 720px;
        margin: 40px auto;
        padding: 0 16px;
      }}
      button {{ margin-top: 8px; }}
      pre {{
        background: #111;
        color: #eee;
        padding: 12px;
        border-radius: 8px;
        overflow: auto;
      }}
      .warn {{ color: #a12; font-weight: 600; }}
    </style>
  </head>
  <body>
    <h1>Google Login Demo</h1>
    <p>
      This page gets a Google ID token and sends it to
      <code>/auth/login</code>.
    </p>
    <p class='warn'>
      {'Set GOOGLE_CLIENT_ID in .env first.' if not client_id else ''}
    </p>

    <div id='g_id_onload'
         data-client_id='{client_id}'
         data-context='signin'
         data-callback='onGoogleCredential'
         data-auto_prompt='false'>
    </div>
    <div class='g_id_signin' data-type='standard'></div>

    <button onclick='logout()'>Logout (app session)</button>

    <h3>Response</h3>
    <pre id='out'>Waiting...</pre>

    <script>
      const out = document.getElementById('out');

      async function onGoogleCredential(response) {{
        try {{
          let recaptchaToken = '';
          if ('{recaptcha_site_key}') {{
            if (!window.grecaptcha) {{
              out.textContent = 'Missing grecaptcha global';
              return;
            }}
            recaptchaToken = await window.grecaptcha.execute(
              '{recaptcha_site_key}',
              {{ action: 'auth_login' }}
            );
          }}

          const r = await fetch('/auth/login', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{
              id_token: response.credential,
              accept_terms: true,
              accept_privacy: true,
              recaptcha_token: recaptchaToken,
            }})
          }});
          const text = await r.text();
          out.textContent = `STATUS ${{r.status}}\n${{text}}`;
        }} catch (e) {{
          out.textContent = String(e);
        }}
      }}

      async function logout() {{
        const r = await fetch('/auth/logout', {{ method: 'POST' }});
        out.textContent = `STATUS ${{r.status}}\nLogged out`;
      }}

      window.onGoogleCredential = onGoogleCredential;
    </script>
  </body>
</html>"""
        self.set_header("Content-Type", "text/html; charset=utf-8")
        self.finish(html)


class LoginPageHandler(SessionAwareHandler):
    async def get(self):
        settings = get_settings()
        self.render(
            "login.html",
            google_client_id=settings.google_client_id or "",
            recaptcha_site_key=settings.recaptcha_site_key or "",
          static_version="20260409-6",
        )


class MissingProfilesPageHandler(SessionAwareHandler):
    async def get(self):
        db = self.application.settings["db"]
        settings = get_settings()
        gcs_prefix = ""
        if settings.gcs_bucket:
            gcs_prefix = (
                "https://storage.googleapis.com/"
                f"{settings.gcs_bucket}/"
            )

        # Check if user needs to acknowledge security agreement
        if self.current_user:
            user_id = self.current_user.get("_id")
            user_doc = await db.users.find_one({"_id": user_id})

            if user_doc and not user_doc.get(
                "security_agreement_acknowledged_at"
            ):
                self.redirect("/security-agreement")
                return

        docs = await list_public_missing_persons(
            db,
            limit=60,
            offset=0,
            status=None,
        )

        cards: list[dict] = []
        for doc in docs:
            public = doc.get("public_ficha") or {}
            location = public.get("location_last_seen") or {}
            physical = public.get("physical_description") or {}
            first_name = str(public.get("first_name") or "").strip()
            last_name = str(public.get("last_name") or "").strip()
            display_name = (
                f"{first_name} {last_name}".strip()
                or "Perfil sin nombre"
            )
            date_missing = str(public.get("date_missing") or "").split("T")[0]
            city = str(location.get("city") or "").strip()
            state = str(location.get("state") or "").strip()
            image_url = str(public.get("primary_image_url") or "").strip()
            neighborhood = str(location.get("neighborhood") or "").strip()
            age = public.get("age_at_disappearance")
            gender = str(public.get("gender") or "").strip()
            height_cm = physical.get("height_cm")
            weight_kg = physical.get("weight_kg")
            identifying_marks = list(physical.get("identifying_marks") or [])
            clothing_last_seen = str(physical.get("clothing_last_seen") or "").strip()
            profile_id = str(doc.get("_id") or "")
            status = str(doc.get("status") or "ACTIVE_SEARCH")

            if not image_url:
                continue

            if gcs_prefix and image_url.startswith(gcs_prefix):
                object_key = image_url.removeprefix(gcs_prefix)
                if object_key:
                    escaped = tornado.escape.url_escape(
                        object_key,
                        plus=False,
                    )
                    image_url = (
                        "/missing-persons/image-proxy?object_key="
                        f"{escaped}"
                    )

            description_parts = [
                f"Desaparecio: {date_missing}" if date_missing else "",
                f"Zona: {city}, {state}" if city or state else "",
            ]
            description = " | ".join([p for p in description_parts if p])

            cards.append(
                {
                    "profile_id": profile_id,
                    "title": display_name,
                    "description": description,
                    "image": image_url,
                    "kind": "images",
                    "date_missing": date_missing,
                    "city": city,
                    "state": state,
                    "neighborhood": neighborhood,
                    "age": age,
                    "gender": gender,
                    "height_cm": height_cm,
                    "weight_kg": weight_kg,
                    "identifying_marks": identifying_marks,
                    "clothing_last_seen": clothing_last_seen,
                    "status": status,
                }
            )

        self.render(
            "missing_profiles.html",
            current_section="reciente",
            images_cards=[c for c in cards if c["kind"] == "images"],
            videos_cards=[c for c in cards if c["kind"] == "videos"],
            texts_cards=[c for c in cards if c["kind"] == "texts"],
            is_authenticated=bool(self.current_user),
        )


class MissingPersonCreatePageHandler(SessionAwareHandler):
    async def get(self):
        if not self.current_user:
            self.redirect("/login")
            return

        settings = get_settings()

        self.render(
            "missing_person_create.html",
            is_authenticated=True,
            current_section="crear",
            static_version=(
              "20260409-6"
                if settings.app_env == "production"
                else "dev"
            ),
        )
