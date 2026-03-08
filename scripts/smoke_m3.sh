#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8888}"
COOKIE_JAR="${COOKIE_JAR:-./.cookies.txt}"
GOOGLE_ID_TOKEN="${GOOGLE_ID_TOKEN:-}"
TARGET_USER_ID="${TARGET_USER_ID:-}"

if ! command -v jq >/dev/null 2>&1; then
  echo "[error] jq is required"
  exit 1
fi

if [[ -z "$GOOGLE_ID_TOKEN" ]]; then
  echo "[error] Set GOOGLE_ID_TOKEN env var"
  exit 1
fi

echo "[1/7] health"
curl -s "$BASE_URL/health" | jq

echo "[2/7] login with google"
curl -sS -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -c "$COOKIE_JAR" \
  -d "{\"id_token\":\"$GOOGLE_ID_TOKEN\"}" | jq

echo "[3/7] create post"
POST_RES="$(curl -sS -X POST "$BASE_URL/posts" \
  -H "Content-Type: application/json" \
  -b "$COOKIE_JAR" \
  -d '{"text":"smoke m3 post","media_type":"text"}')"
echo "$POST_RES" | jq

if [[ -n "$TARGET_USER_ID" ]]; then
  echo "[4/7] follow $TARGET_USER_ID"
  curl -sS -o /dev/null -w "status=%{http_code}\n" -X POST "$BASE_URL/social/follow" \
    -H "Content-Type: application/json" \
    -b "$COOKIE_JAR" \
    -d "{\"target_user_id\":\"$TARGET_USER_ID\"}"
else
  echo "[4/7] follow skipped (set TARGET_USER_ID to enable)"
fi

echo "[5/7] read feed"
curl -sS "$BASE_URL/feed?limit=20&offset=0" \
  -b "$COOKIE_JAR" | jq

if [[ -n "$TARGET_USER_ID" ]]; then
  echo "[6/7] unfollow $TARGET_USER_ID"
  curl -sS -o /dev/null -w "status=%{http_code}\n" -X POST "$BASE_URL/social/unfollow" \
    -H "Content-Type: application/json" \
    -b "$COOKIE_JAR" \
    -d "{\"target_user_id\":\"$TARGET_USER_ID\"}"
else
  echo "[6/7] unfollow skipped (set TARGET_USER_ID to enable)"
fi

echo "[7/7] logout"
curl -sS -o /dev/null -w "status=%{http_code}\n" -X POST "$BASE_URL/auth/logout" \
  -b "$COOKIE_JAR"

echo "done"
