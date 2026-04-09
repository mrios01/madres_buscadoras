# marzlive_upgrade

Fresh rewrite of Marzlive, using the legacy `marzlive` project only as functional context.

## Goals

- Modern, maintainable architecture
- Tornado 6 + Python 3.12
- Clear module boundaries (auth, feed, media, social graph, messaging)
- Dual video streaming backend:
  1. Nginx-served HLS
  2. Google Cloud Storage HLS

## Local development (first milestone)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
python -m app.main --port=8888
```

## Quick auth demo (Google)

1. Set `GOOGLE_CLIENT_ID` in `.env`
2. Run app (`python -m app.main --port=8888`)
3. Open: `http://localhost:8888/demo/google-auth`
4. Sign in with Google (browser)

The demo posts the Google `id_token` to `/auth/login` and stores app session cookie.

## VM service (media worker)

A systemd unit template is included:

- `deploy/systemd/marzlive-media-worker.service`
- `deploy/systemd/INSTALL.md`

Use it on the VM to run the media worker continuously.

## Milestone status

- Milestone 1 ✅
- Milestone 2 ✅ (Google login + app sessions)
- Milestone 3 ✅ (follow/unfollow, create post, feed + pagination)
- Milestone 4 🚧 in progress (media adapters + playback URL strategy + ingest/upload/finalize APIs + local ffmpeg worker with one-shot/loop modes)
- UI milestone A ✅ (login page + Missing Person Profile landing)
- Security schema milestone ✅ (Google OAuth-only + Tier 0/Tier 2 case model)

## Authentication model (Google OAuth only)

- `/auth/login` accepts Google `id_token` and creates app session cookie.
- `/auth/register` is intentionally disabled (`405`, google_oauth_only).
- User documents now live in Mongo `users` collection with OpSec fields:
  - `display_name`, `collective_id`, `role`, `verification_status`
  - `phone_number_hash`
  - `security.duress_pin_hash`, `security.last_known_device_id`,
    `security.force_logout`
  - `google_oauth.sub`, `google_oauth.email`, `google_oauth.email_verified`
  - `joined_at`, `last_active`
- Middleware enforces force-logout kill switch by revoking session when
  `security.force_logout=true`.

## Missing person schema (Tier separation)

- Added BSON-aligned data model in `app/models/missing_person.py`.
- Collection: `missing_persons`.
- Public-safe tier: `public_ficha`.
- Restricted tier: `private_dossier`.
- API uses explicit projection behavior to avoid accidental leakage:
  - Public list/detail excludes `private_dossier`.
  - Private dossier only available through authenticated endpoint with
    authorization checks (owner, authorized collective, or admin).

## New missing-person endpoints

- `GET /missing-persons` public listing (Tier 0 only)
- `GET /missing-persons/:id` public detail (Tier 0 only)
- `POST /missing-persons/create` authenticated create (includes Tier 2)
- `GET /missing-persons/private/:id?include_private=true` authenticated private
  access with authorization checks

## New UI routes (2026-04-08)

- / and /login render the new social login page for Madres Buscadoras.
- /missing-profiles renders a first profile feed style page inspired by the legacy layout.
- Google Sign-In posts ID token to /auth/login and redirects to /missing-profiles on success.
- Preview button allows entering the new UI flow without Google setup during early design iterations.

## Template architecture update (2026-04-08)

- Added shared base template at app/templates/_layout.html.
- Added Bootstrap-based header, nav, search, and footer blocks inspired by legacy structure.
- Refactored app/templates/missing_profiles.html to extend _layout.html.
- Added tabbed sections (Images, Videos, Textos) for Missing Person Profile page.
- Added new shared frontend assets: app/static/layout.css and app/static/layout.js.
- Added page script app/static/js/missing_profiles.js for tab interaction hooks.

## Codebase analysis snapshot (2026-04-08)

- Entry point and routing: app/main.py wires Tornado handlers and async index initialization.
- Configuration: app/core/config.py loads .env via pydantic settings.
- Database access: app/core/db.py uses Motor (async MongoDB client).
- Auth domain: app/api/auth.py + app/services/auth.py provide register/login/logout, session cookies, and Google ID token verification.
- Social/feed domain: app/api/social.py + app/api/feed.py + app/services/social.py implement follow graph, posting, and paginated feed retrieval.
- Media domain: app/api/media.py + app/services/media.py implement ingest planning, upload ticket issuance, status transitions, playback URL resolution, and worker processing hooks.
- Worker path: scripts/media_worker_once.py processes planned media assets (one-shot or polling loop).
- Tests: tests/test_health.py validates /health endpoint baseline.

## Setup and dependency status (2026-04-08)

- Project virtual environment created at .venv.
- Installed project and dev dependencies with pip install -e .[dev].
- Runtime dependency import check passed (tornado, motor, pymongo, pydantic, dotenv, yaml, google cloud storage).
- Test suite passed: 1 passed.
- External binaries check: ffmpeg missing, mongod missing.
- Added Tornado template/static wiring for app/templates and app/static.
- Added first frontend assets under app/static/css, app/static/js, and app/templates.

## Notes for full local runtime

- Media worker in local backend mode requires ffmpeg installed on the host.
- App features requiring persistence need a reachable MongoDB instance configured via MONGODB_URI.
