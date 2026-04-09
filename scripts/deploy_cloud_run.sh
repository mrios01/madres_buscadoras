#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI is required but not installed." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo ".env file not found in $ROOT_DIR" >&2
  exit 1
fi

set -a
. ./.env
set +a

: "${GCS_PROJECT_ID:?GCS_PROJECT_ID must be set in .env}"
: "${GCS_BUCKET:?GCS_BUCKET must be set in .env}"
: "${GOOGLE_CLIENT_ID:?GOOGLE_CLIENT_ID must be set in .env}"
: "${RECAPTCHA_SITE_KEY:?RECAPTCHA_SITE_KEY must be set in .env}"

PROJECT_ID="${PROJECT_ID:-$GCS_PROJECT_ID}"
BULLETIN_PUBSUB_ENABLED="${BULLETIN_PUBSUB_ENABLED:-false}"
BULLETIN_PROJECT_ID="${BULLETIN_PROJECT_ID:-$PROJECT_ID}"
BULLETIN_TOPIC_ID="${BULLETIN_TOPIC_ID:-area-segura-bulletin}"
BULLETIN_SUBSCRIPTION_ID="${BULLETIN_SUBSCRIPTION_ID:-area-segura-bulletin-sub}"
BULLETIN_DLQ_TOPIC_ID="${BULLETIN_DLQ_TOPIC_ID:-area-segura-bulletin-dlq}"
RECAPTCHA_SECRET_KEY="${RECAPTCHA_SECRET_KEY:-}"
RECAPTCHA_PROJECT_ID="${RECAPTCHA_PROJECT_ID:-$PROJECT_ID}"
RECAPTCHA_MIN_SCORE="${RECAPTCHA_MIN_SCORE:-0.5}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-madres-buscadoras-web}"
REPOSITORY="${ARTIFACT_REGISTRY_REPOSITORY:-cloud-run-apps}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-${SERVICE_NAME}}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com}"
DOMAIN_NAME="${DOMAIN_NAME:-madresbuscadoras.zocalo.media}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${SERVICE_NAME}:$(date +%Y%m%d-%H%M%S)"

MONGODB_URI_SECRET_NAME="${MONGODB_URI_SECRET_NAME:-madres-buscadoras-mongodb-uri}"
COOKIE_SECRET_NAME="${COOKIE_SECRET_NAME:-madres-buscadoras-cookie-secret}"
PASSWORD_SALT_SECRET_NAME="${PASSWORD_SALT_SECRET_NAME:-madres-buscadoras-password-salt}"
GOOGLE_CLIENT_SECRET_NAME="${GOOGLE_CLIENT_SECRET_NAME:-madres-buscadoras-google-client-secret}"
RECAPTCHA_SECRET_NAME="${RECAPTCHA_SECRET_NAME:-madres-buscadoras-recaptcha-secret}"

TMP_MANIFEST="$(mktemp)"
trap 'rm -f "$TMP_MANIFEST"' EXIT

echo "Enabling required Google Cloud APIs..."
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  pubsub.googleapis.com \
  run.googleapis.com \
  recaptchaenterprise.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  --project "$PROJECT_ID" >/dev/null

echo "Ensuring Artifact Registry repository exists..."
if ! gcloud artifacts repositories describe "$REPOSITORY" \
  --location "$REGION" \
  --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$REPOSITORY" \
    --repository-format docker \
    --location "$REGION" \
    --description "Cloud Run images for Madres Buscadoras" \
    --project "$PROJECT_ID"
fi

echo "Ensuring runtime service account exists..."
if ! gcloud iam service-accounts describe "$SERVICE_ACCOUNT" \
  --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
    --display-name "Madres Buscadoras Cloud Run runtime" \
    --project "$PROJECT_ID"
fi

echo "Ensuring Secret Manager secrets exist..."
secret_has_versions() {
  local secret_name="$1"
  local first_version

  first_version="$(
    gcloud secrets versions list "$secret_name" \
      --project "$PROJECT_ID" \
      --limit 1 \
      --format='value(name)' 2>/dev/null || true
  )"

  [[ -n "$first_version" ]]
}

ensure_secret() {
  local secret_name="$1"
  local secret_value="$2"
  local allow_empty_payload="${3:-false}"
  local safe_secret_value
  local tmp_secret_file

  if [[ -z "$secret_value" ]]; then
    if [[ "$allow_empty_payload" == "true" ]]; then
      safe_secret_value=" "
    else
      if secret_has_versions "$secret_name"; then
        echo "Using existing latest version for $secret_name"
        return
      fi
      echo "Secret $secret_name has no version and no local value was provided." >&2
      echo "Set this value once in .env or create a secret version manually." >&2
      exit 1
    fi
  else
    safe_secret_value="$secret_value"
  fi

  tmp_secret_file="$(mktemp)"
  printf '%s' "$safe_secret_value" > "$tmp_secret_file"

  if ! gcloud secrets describe "$secret_name" \
    --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud secrets create "$secret_name" \
      --replication-policy=automatic \
      --project "$PROJECT_ID"
  fi

  gcloud secrets versions add "$secret_name" \
    --data-file="$tmp_secret_file" \
    --project "$PROJECT_ID" >/dev/null

  rm -f "$tmp_secret_file"
}

ensure_secret "$MONGODB_URI_SECRET_NAME" "${MONGODB_URI:-}"
ensure_secret "$COOKIE_SECRET_NAME" "${COOKIE_SECRET:-}"
ensure_secret "$PASSWORD_SALT_SECRET_NAME" "${PASSWORD_SALT:-}"
ensure_secret "$GOOGLE_CLIENT_SECRET_NAME" "${GOOGLE_CLIENT_SECRET:-}" true
ensure_secret "$RECAPTCHA_SECRET_NAME" "$RECAPTCHA_SECRET_KEY" true

echo "Granting runtime service account storage permissions..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${SERVICE_ACCOUNT}" \
  --role roles/storage.objectAdmin >/dev/null

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${SERVICE_ACCOUNT}" \
  --role roles/recaptchaenterprise.agent >/dev/null

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${SERVICE_ACCOUNT}" \
  --role roles/pubsub.publisher >/dev/null

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${SERVICE_ACCOUNT}" \
  --role roles/pubsub.subscriber >/dev/null

echo "Setting up Pub/Sub dead-letter topic and subscription retention..."

# Ensure DLQ topic exists
if ! gcloud pubsub topics describe "$BULLETIN_DLQ_TOPIC_ID" --project "$BULLETIN_PROJECT_ID" >/dev/null 2>&1; then
  gcloud pubsub topics create "$BULLETIN_DLQ_TOPIC_ID" --project "$BULLETIN_PROJECT_ID"
fi

# Grant Pub/Sub managed SA rights for dead-letter forwarding
_PUBSUB_PROJECT_NUMBER=$(gcloud projects describe "$BULLETIN_PROJECT_ID" --format="value(projectNumber)")
_PUBSUB_MANAGED_SA="service-${_PUBSUB_PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"

gcloud pubsub topics add-iam-policy-binding "$BULLETIN_DLQ_TOPIC_ID" \
  --member="serviceAccount:${_PUBSUB_MANAGED_SA}" \
  --role="roles/pubsub.publisher" \
  --project "$BULLETIN_PROJECT_ID" >/dev/null

gcloud pubsub subscriptions add-iam-policy-binding "$BULLETIN_SUBSCRIPTION_ID" \
  --member="serviceAccount:${_PUBSUB_MANAGED_SA}" \
  --role="roles/pubsub.subscriber" \
  --project "$BULLETIN_PROJECT_ID" >/dev/null

# Apply dead-letter policy (5 max attempts) and 7-day message retention
if gcloud pubsub subscriptions describe "$BULLETIN_SUBSCRIPTION_ID" --project "$BULLETIN_PROJECT_ID" >/dev/null 2>&1; then
  gcloud pubsub subscriptions update "$BULLETIN_SUBSCRIPTION_ID" \
    --dead-letter-topic="projects/${BULLETIN_PROJECT_ID}/topics/${BULLETIN_DLQ_TOPIC_ID}" \
    --max-delivery-attempts=5 \
    --message-retention-duration=7d \
    --project "$BULLETIN_PROJECT_ID" >/dev/null
fi

gcloud iam service-accounts add-iam-policy-binding "$SERVICE_ACCOUNT" \
  --member "serviceAccount:${SERVICE_ACCOUNT}" \
  --role roles/iam.serviceAccountTokenCreator \
  --project "$PROJECT_ID" >/dev/null

echo "Building container image with Cloud Build..."
gcloud builds submit \
  --tag "$IMAGE" \
  --project "$PROJECT_ID"

echo "Granting runtime service account access to secrets..."
for secret_name in \
  "$MONGODB_URI_SECRET_NAME" \
  "$COOKIE_SECRET_NAME" \
  "$PASSWORD_SALT_SECRET_NAME" \
  "$GOOGLE_CLIENT_SECRET_NAME" \
  "$RECAPTCHA_SECRET_NAME"; do
  gcloud secrets add-iam-policy-binding "$secret_name" \
    --member "serviceAccount:${SERVICE_ACCOUNT}" \
    --role roles/secretmanager.secretAccessor \
    --project "$PROJECT_ID" >/dev/null
done

sed \
  -e "s|__IMAGE__|${IMAGE}|g" \
  -e "s|__SERVICE_ACCOUNT__|${SERVICE_ACCOUNT}|g" \
  -e "s|__GCP_PROJECT_ID__|${PROJECT_ID}|g" \
  -e "s|__GCS_BUCKET__|${GCS_BUCKET}|g" \
  -e "s|__BULLETIN_PUBSUB_ENABLED__|${BULLETIN_PUBSUB_ENABLED}|g" \
  -e "s|__BULLETIN_PROJECT_ID__|${BULLETIN_PROJECT_ID}|g" \
  -e "s|__BULLETIN_TOPIC_ID__|${BULLETIN_TOPIC_ID}|g" \
  -e "s|__BULLETIN_SUBSCRIPTION_ID__|${BULLETIN_SUBSCRIPTION_ID}|g" \
  -e "s|__GOOGLE_CLIENT_ID__|${GOOGLE_CLIENT_ID}|g" \
  -e "s|__RECAPTCHA_SITE_KEY__|${RECAPTCHA_SITE_KEY}|g" \
  -e "s|__RECAPTCHA_PROJECT_ID__|${RECAPTCHA_PROJECT_ID}|g" \
  -e "s|__RECAPTCHA_MIN_SCORE__|${RECAPTCHA_MIN_SCORE}|g" \
  -e "s|__MONGODB_URI_SECRET_NAME__|${MONGODB_URI_SECRET_NAME}|g" \
  -e "s|__COOKIE_SECRET_NAME__|${COOKIE_SECRET_NAME}|g" \
  -e "s|__PASSWORD_SALT_SECRET_NAME__|${PASSWORD_SALT_SECRET_NAME}|g" \
  -e "s|__GOOGLE_CLIENT_SECRET_NAME__|${GOOGLE_CLIENT_SECRET_NAME}|g" \
  -e "s|__RECAPTCHA_SECRET_NAME__|${RECAPTCHA_SECRET_NAME}|g" \
  deploy/cloudrun/service.template.yaml > "$TMP_MANIFEST"

echo "Deploying Cloud Run service..."
gcloud run services replace "$TMP_MANIFEST" \
  --region "$REGION" \
  --project "$PROJECT_ID"

echo "Allowing unauthenticated access..."
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
  --member allUsers \
  --role roles/run.invoker \
  --region "$REGION" \
  --project "$PROJECT_ID" >/dev/null

if [[ -n "$DOMAIN_NAME" ]]; then
  echo "Ensuring gcloud beta commands are installed..."
  gcloud components install beta -q >/dev/null

  echo "Attempting domain mapping for $DOMAIN_NAME..."
  if gcloud beta run domain-mappings create \
    --service "$SERVICE_NAME" \
    --domain "$DOMAIN_NAME" \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    --quiet; then
    echo "Domain mapping request submitted. Complete the DNS records shown by gcloud if prompted."
  else
    echo "Domain mapping could not be completed automatically."
    echo "Use the Cloud Run custom domain UI or rerun:"
    echo "gcloud beta run domain-mappings create --service $SERVICE_NAME --domain $DOMAIN_NAME --region $REGION --project $PROJECT_ID"
  fi
fi

echo "Deployment complete."
gcloud run services describe "$SERVICE_NAME" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --format='value(status.url)'