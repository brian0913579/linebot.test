#!/bin/bash

# Setup script for GitHub Actions deployment to Google App Engine
# Run this script to create the necessary service account and permissions

PROJECT_ID="line-462014"
SERVICE_ACCOUNT_NAME="github-actions"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "Setting up Google Cloud service account for GitHub Actions..."

# Create service account
echo "Creating service account: ${SERVICE_ACCOUNT_EMAIL}"
gcloud iam service-accounts create ${SERVICE_ACCOUNT_NAME} \
    --description="GitHub Actions deployment service account" \
    --display-name="GitHub Actions" \
    --project=${PROJECT_ID}

# Grant necessary permissions
echo "Granting App Engine deployer role..."
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/appengine.deployer"

echo "Granting Cloud Build editor role..."
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/cloudbuild.builds.editor"

echo "Granting Storage admin role..."
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/storage.admin"

echo "Granting Secret Manager accessor role..."
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/secretmanager.secretAccessor"

# Create and download service account key
echo "Creating service account key..."
gcloud iam service-accounts keys create github-actions-key.json \
    --iam-account=${SERVICE_ACCOUNT_EMAIL} \
    --project=${PROJECT_ID}

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Go to your GitHub repository settings"
echo "2. Navigate to: Settings → Secrets and variables → Actions"
echo "3. Add the following repository secrets:"
echo "   - GCP_SA_KEY: Copy the entire content of 'github-actions-key.json'"
echo "   - LINE_CHANNEL_ACCESS_TOKEN: Your LINE bot access token"
echo "   - LINE_CHANNEL_SECRET: Your LINE bot channel secret"
echo ""
echo "4. Delete the github-actions-key.json file after copying its content!"
echo "   rm github-actions-key.json"
echo ""
echo "🚀 After adding the secrets, push to main branch to trigger deployment!"
