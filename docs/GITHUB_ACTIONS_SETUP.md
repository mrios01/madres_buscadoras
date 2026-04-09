# GitHub Actions Cloud Run Deployment Setup

This workflow automates deployment to Google Cloud Run on every push to the `main` branch. It uses [Workload Identity Federation](https://cloud.google.com/docs/authentication/workload-identity-federation) for secure keyless authentication.

## Prerequisites

- GitHub repository secrets configured (see below)
- Google Cloud service account with appropriate permissions
- Workload Identity Federation set up between GitHub and Google Cloud

## One-Time Setup

### 1. Create a GCP Service Account

```bash
gcloud iam service-accounts create github-actions \
  --display-name "GitHub Actions deployment service account" \
  --project moanarkrocks
```

### 2. Grant Required IAM Roles

```bash
PROJECT_ID="moanarkrocks"
SERVICE_ACCOUNT="github-actions@${PROJECT_ID}.iam.gserviceaccount.com"

# Cloud Run deployment
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${SERVICE_ACCOUNT}" \
  --role roles/run.admin

# Artifact Registry
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${SERVICE_ACCOUNT}" \
  --role roles/artifactregistry.admin

# Cloud Build
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${SERVICE_ACCOUNT}" \
  --role roles/cloudbuild.builds.editor

# Secret Manager
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${SERVICE_ACCOUNT}" \
  --role roles/secretmanager.secretAccessor

# Cloud Storage
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${SERVICE_ACCOUNT}" \
  --role roles/storage.objectAdmin

# IAM
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${SERVICE_ACCOUNT}" \
  --role roles/iam.serviceAccountAdmin
```

### 3. Set Up Workload Identity Federation

Configure OIDC federation so GitHub can assume the service account without long-lived keys:

```bash
PROJECT_ID="moanarkrocks"
GITHUB_REPO="mrios01/madres_buscadoras"

# Enable required APIs
gcloud services enable iamcredentials.googleapis.com \
  cloudresourcemanager.googleapis.com \
  sts.googleapis.com \
  --project "$PROJECT_ID"

# Create Workload Identity Pool
gcloud iam workload-identity-pools create github \
  --project "$PROJECT_ID" \
  --location global \
  --display-name "GitHub Actions"

# Create Workload Identity Provider
gcloud iam workload-identity-providers create-oidc github-provider \
  --project "$PROJECT_ID" \
  --location global \
  --workload-identity-pool github \
  --display-name "GitHub provider" \
  --attribute-mapping "google.subject=assertion.sub,attribute.aud=assertion.aud,attribute.repository=assertion.repository" \
  --issuer-uri "https://token.actions.githubusercontent.com"

# Get the Workload Identity Provider resource name
WIP_RESOURCE_NAME=$(gcloud iam workload-identity-providers describe github-provider \
  --project "$PROJECT_ID" \
  --location global \
  --format='value(name)')

# Grant GitHub repo the ability to assume the service account
SERVICE_ACCOUNT="github-actions@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud iam service-accounts add-iam-policy-binding "${SERVICE_ACCOUNT}" \
  --project "$PROJECT_ID" \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/${WIP_RESOURCE_NAME}/attribute.repository/${GITHUB_REPO}"
```

### 4. Add GitHub Repository Secrets

In your GitHub repository:
1. Go to **Settings → Secrets and variables → Actions**
2. Create the following secrets:

| Secret Name | Value |
|---|---|
| `GCLOUD_WORKLOAD_IDENTITY_PROVIDER` | Output of: `gcloud iam workload-identity-providers describe github-provider --project=moanarkrocks --location=global --format='value(name)'` |
| `GCLOUD_SERVICE_ACCOUNT_EMAIL` | `github-actions@moanarkrocks.iam.gserviceaccount.com` |
| `MONGODB_URI` | Your MongoDB Atlas connection string (from `.env`) |
| `COOKIE_SECRET` | Your cookie secret (from `.env`) |
| `PASSWORD_SALT` | Your password salt (from `.env`) |
| `GOOGLE_CLIENT_ID` | Your Google OAuth client ID (from `.env`) |
| `GCS_BUCKET` | Your GCS bucket name (from `.env`) |

## Usage

### Automatic Deployment (on push to main)

Simply push to the `main` branch:

```bash
git push origin main
```

The workflow will automatically trigger, build the image, and deploy to Cloud Run.

### Manual Deployment

You can also trigger the workflow manually from the GitHub Actions tab:
1. Go to **Actions → Deploy to Cloud Run**
2. Click **Run workflow**
3. Select the branch (default: `main`)
4. Click **Run workflow**

## Workflow Steps

1. **Checkout code** — Retrieves the latest source
2. **Authenticate to Google Cloud** — Uses Workload Identity Federation to assume the service account
3. **Set up Google Cloud CLI** — Installs `gcloud` and authenticates
4. **Create .env file** — Constructs the runtime environment from GitHub secrets
5. **Run Cloud Run deployment** — Executes `scripts/deploy_cloud_run.sh`

## Monitoring

View deployment logs in **GitHub Actions** tab:
- Click on the latest workflow run
- Expand job steps to see build and deployment details

View deployed service in Google Cloud:
```bash
gcloud run services describe madres-buscadoras-web \
  --region us-central1 \
  --project moanarkrocks
```

## Troubleshooting

### "Workload identity provider not found"
Ensure `GCLOUD_WORKLOAD_IDENTITY_PROVIDER` secret is set correctly. Re-run the setup command above and update the secret.

### "Service account not authorized"
Verify the service account has all required IAM roles from step 2 above.

### "Secret not found"
Ensure all required secrets are added to the GitHub repository. Check the table above for the complete list.

### Authentication failures
- Verify `GCLOUD_WORKLOAD_IDENTITY_PROVIDER` and `GCLOUD_SERVICE_ACCOUNT_EMAIL` secrets match the resources created in GCP
- Check that the Workload Identity Provider is configured with the correct GitHub repository path
