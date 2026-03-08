# API Quick Test (curl)

Base URL:

```bash
BASE_URL="http://localhost:8888"
COOKIE_JAR="./.cookies.txt"
```

## 0) Health

```bash
curl -s "$BASE_URL/health" | jq
```

## 1) Login with Google ID token

> You need a valid Google ID token for your configured `GOOGLE_CLIENT_ID`.

```bash
GOOGLE_ID_TOKEN="<paste_google_id_token_here>"

curl -i -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -c "$COOKIE_JAR" \
  -d "{\"id_token\":\"$GOOGLE_ID_TOKEN\"}"
```

## 2) Create a post

```bash
curl -i -s -X POST "$BASE_URL/posts" \
  -H "Content-Type: application/json" \
  -b "$COOKIE_JAR" \
  -d '{
    "text":"Hello from milestone 3!",
    "media_type":"text"
  }'
```

## 3) Follow a user

```bash
TARGET_USER_ID="<target_user_objectid>"

curl -i -s -X POST "$BASE_URL/social/follow" \
  -H "Content-Type: application/json" \
  -b "$COOKIE_JAR" \
  -d "{\"target_user_id\":\"$TARGET_USER_ID\"}"
```

## 4) Read feed (paginated)

```bash
curl -s "$BASE_URL/feed?limit=20&offset=0" \
  -b "$COOKIE_JAR" | jq
```

## 5) Unfollow a user

```bash
curl -i -s -X POST "$BASE_URL/social/unfollow" \
  -H "Content-Type: application/json" \
  -b "$COOKIE_JAR" \
  -d "{\"target_user_id\":\"$TARGET_USER_ID\"}"
```

## 6) Create media ingest plan (Milestone 4)

```bash
PLAN_JSON=$(curl -s -X POST "$BASE_URL/media/ingest/plan" \
  -H "Content-Type: application/json" \
  -b "$COOKIE_JAR" \
  -d '{"filename":"sample.mp4","visibility":"private"}')

echo "$PLAN_JSON" | jq
MEDIA_ASSET_ID=$(echo "$PLAN_JSON" | jq -r '.id')
```

## 7) Request upload ticket

```bash
curl -s -X POST "$BASE_URL/media/upload-ticket" \
  -H "Content-Type: application/json" \
  -b "$COOKIE_JAR" \
  -d "{\"media_asset_id\":\"$MEDIA_ASSET_ID\"}" | jq
```

## 8) Run worker (one-shot or daemon mode)

One-shot:

```bash
python scripts/media_worker_once.py --backend local
```

Daemon/poll mode:

```bash
python scripts/media_worker_once.py --backend local --loop --interval-seconds 5
```

## 9) (Optional fallback) Finalize ingest status manually

```bash
curl -s -X POST "$BASE_URL/media/ingest/finalize" \
  -H "Content-Type: application/json" \
  -b "$COOKIE_JAR" \
  -d "{\"media_asset_id\":\"$MEDIA_ASSET_ID\",\"status\":\"ready\"}" | jq
```

## 10) Create post linked to media asset

```bash
curl -i -s -X POST "$BASE_URL/posts" \
  -H "Content-Type: application/json" \
  -b "$COOKIE_JAR" \
  -d "{\"text\":\"My first upgraded video post\",\"media_asset_id\":\"$MEDIA_ASSET_ID\"}"
```

## 11) Get playback URL directly (public/signed)

```bash
OBJECT_KEY="videos/<media_id>/hls/index.m3u8"

curl -i -s -X POST "$BASE_URL/media/playback-url" \
  -H "Content-Type: application/json" \
  -b "$COOKIE_JAR" \
  -d "{\"object_key\":\"$OBJECT_KEY\",\"visibility\":\"private\"}" | jq
```

## 12) Logout

```bash
curl -i -s -X POST "$BASE_URL/auth/logout" \
  -b "$COOKIE_JAR"
```

---

## Optional: quick way to get a target user id from Mongo

```bash
mongosh "$MONGODB_URI/$MONGODB_DBNAME" --eval 'db.login.find({}, {email:1,screen_name:1}).limit(10).toArray()'
```
