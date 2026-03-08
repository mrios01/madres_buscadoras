# Legacy Context Mapping (`marzlive` -> `marzlive_upgrade`)

This project is a clean rewrite. Legacy code is reference-only.

## Legacy capabilities to preserve

- User auth/session
- Profiles
- Text/image/video posting
- Feed + discovery
- Likes/comments
- Followers/following
- Messaging + realtime
- Video playback/streaming

## Legacy architecture observations

- Monolithic route registry in `website/access.py`
- Handlers with mixed concerns
- Legacy Tornado coroutine style (`gen.engine`, callbacks)
- Hardcoded paths/secrets

## Rewrite principles

1. Modular domains
2. Async/await only
3. Explicit config through env
4. Storage abstraction for media
5. Testable services and handlers
6. Security-first defaults
