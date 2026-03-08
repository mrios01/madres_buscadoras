# Schema Notes from legacy `marzlive/schemas.txt`

## Identity-related collections observed

### `login` (count ~3983)
Key fields:
- `email` (string)
- `screen_name` (string)
- `password_hash` (string)
- `salt` (string)
- `pepper` (string)
- `first_name`, `last_name`, `birth_date`
- `account`, `opt_in`
- `dateCreated`

### `chat` / `chats`
Not identity source of truth; content/channel metadata.

## Decisions for `marzlive_upgrade` Milestone 2

- Reuse legacy-compatible `login` collection name for users during transition.
- Introduce dedicated `sessions` collection for auth sessions.
- Enforce indexes:
  - `login.email` unique
  - `login.screen_name` unique
  - `sessions.token_hash` unique
  - TTL index on `sessions.expires_at`

## Endpoints added

- `POST /auth/register` (legacy/email-password compatibility)
- `POST /auth/login` (Google ID token)
- `POST /auth/logout`

`/auth/login` now expects `{ "id_token": "<google-id-token>" }` and auto-provisions users in `login` on first Google sign-in.

## Cookie/session policy

- HttpOnly secure cookie name: `AUTH_COOKIE_NAME` (default `ml_session`)
- SameSite configurable (`AUTH_COOKIE_SAMESITE`, default `lax`)
- Secure flag configurable (`AUTH_COOKIE_SECURE`, default `false` for local)
- Session TTL configurable in days (`AUTH_SESSION_TTL_DAYS`, default `14`)
- Google OAuth audience configurable (`GOOGLE_CLIENT_ID`)
