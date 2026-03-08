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
