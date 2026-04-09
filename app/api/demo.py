import tornado.web

from app.core.config import get_settings


class GoogleAuthDemoHandler(tornado.web.RequestHandler):
    async def get(self):
        settings = get_settings()
        client_id = settings.google_client_id or ""

        html = f"""<!doctype html>
<html>
  <head>
    <meta charset='utf-8' />
    <meta name='viewport' content='width=device-width, initial-scale=1' />
    <title>Marzlive Google Auth Demo</title>
    <script src='https://accounts.google.com/gsi/client' async defer></script>
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
          const r = await fetch('/auth/login', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ id_token: response.credential }})
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


class LoginPageHandler(tornado.web.RequestHandler):
    async def get(self):
        settings = get_settings()
        self.render(
            "login.html",
            google_client_id=settings.google_client_id or "",
        )


class MissingProfilesPageHandler(tornado.web.RequestHandler):
    async def get(self):
        cards = [
            {
                "title": "Amor en tiempo de Coronavirus",
                "description": "Busqueda de contacto en zona metropolitana.",
                "image": (
                    "https://images.unsplash.com/photo-1516589178581-"
                    "6cd7833ae3b2?auto=format&fit=crop&w=900&q=80"
                ),
                "kind": "images",
            },
            {
                "title": "Lo que mas me gusta de estas fechas",
                "description": (
                    "Ficha comunitaria para rastreo por puntos clave."
                ),
                "image": (
                    "https://images.unsplash.com/photo-1531968455001-"
                    "5c5272a41129?auto=format&fit=crop&w=900&q=80"
                ),
                "kind": "images",
            },
            {
                "title": "Catrina floral",
                "description": (
                    "Perfil visual con senas particulares y redes de apoyo."
                ),
                "image": (
                    "https://images.unsplash.com/photo-1544717305-"
                    "2782549b5136?auto=format&fit=crop&w=900&q=80"
                ),
                "kind": "images",
            },
            {
                "title": "Video de ubicacion reciente",
                "description": (
                    "Testimonio audiovisual de posible avistamiento."
                ),
                "image": (
                    "https://images.unsplash.com/photo-1492691527719-"
                    "9d1e07e534b4?auto=format&fit=crop&w=900&q=80"
                ),
                "kind": "videos",
            },
            {
                "title": "Actualizacion de brigada",
                "description": (
                    "Texto con nuevas rutas y coordenadas de busqueda."
                ),
                "image": (
                    "https://images.unsplash.com/photo-1454165804606-"
                    "c3d57bc86b40?auto=format&fit=crop&w=900&q=80"
                ),
                "kind": "texts",
            },
        ]

        self.render(
            "missing_profiles.html",
            current_section="reciente",
            images_cards=[c for c in cards if c["kind"] == "images"],
            videos_cards=[c for c in cards if c["kind"] == "videos"],
            texts_cards=[c for c in cards if c["kind"] == "texts"],
            is_authenticated=bool(self.current_user),
        )
