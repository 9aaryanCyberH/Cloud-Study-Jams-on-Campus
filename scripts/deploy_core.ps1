<#
.SYNOPSIS
  CloudPort: Core GCP Services Deployment Script (Minimal Footprint)
  Deploys strictly the 3 Core Requirements of GDG BPPIMT Cloud Team Selection:
    1. Google Cloud Storage (Static Website Hosting)
    2. Google Cloud Functions (2nd Gen, Python 3.12, HTTP Trigger)
    3. Google Cloud Firestore (Native Mode Database)
  Zero unnecessary bonus services. Maximum Free-Tier compatibility.
#>

param(
    [Parameter(Mandatory=$false)]
    [string]$ProjectId,
    
    [Parameter(Mandatory=$false)]
    [string]$Region = "us-central1"
)

$ErrorActionPreference = "Stop"

# Locate gcloud binary
$gcloud = "C:\Users\Aaryan Kumar\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
if (-not (Test-Path $gcloud)) {
    $gcloud = "gcloud"
}

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " CloudPort: Core GCP Serverless Deployment (GDG BPPIMT)" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 1. Resolve Project ID
if (-not $ProjectId) {
    $ProjectId = (& $gcloud config get-value project 2>$null).Trim()
}

if (-not $ProjectId -or $ProjectId -eq "(unset)") {
    Write-Host "[!] Error: No active GCP project configured." -ForegroundColor Red
    Write-Host "Please set your project first by running:" -ForegroundColor Yellow
    Write-Host "  & '$gcloud' config set project YOUR_PROJECT_ID" -ForegroundColor Yellow
    exit 1
}

Write-Host "[+] Target Project ID: $ProjectId" -ForegroundColor Green
Write-Host "[+] Target Region:     $Region" -ForegroundColor Green

# 2. Verify Billing Status
Write-Host "`n--- Step 1: Checking Billing Status ---" -ForegroundColor Cyan
$billing = (& $gcloud billing projects describe $ProjectId --format="json" 2>$null | ConvertFrom-Json)
if ($billing -and $billing.billingEnabled) {
    Write-Host "[+] Billing is active on project: $ProjectId" -ForegroundColor Green
} else {
    Write-Host "[!] WARNING: Billing does not appear to be linked to project $ProjectId." -ForegroundColor Yellow
    Write-Host "    Cloud Functions (2nd Gen) requires billing enabled to provision Cloud Build and Cloud Run." -ForegroundColor Yellow
}

# 3. Enable Required Core APIs
Write-Host "`n--- Step 2: Enabling Required Core APIs ---" -ForegroundColor Cyan
$coreApis = @(
    "cloudfunctions.googleapis.com",
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "firestore.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com"
)

foreach ($api in $coreApis) {
    Write-Host "  -> Enabling $api..." -NoNewline
    & $gcloud services enable $api --project=$ProjectId --quiet
    Write-Host " [OK]" -ForegroundColor Green
}

# 4. Verify / Create Firestore Database (Native Mode)
Write-Host "`n--- Step 3: Verifying Firestore Database (Native Mode) ---" -ForegroundColor Cyan
$databases = (& $gcloud firestore databases list --project=$ProjectId --format="json" 2>$null | ConvertFrom-Json)
$hasDefaultDb = $false
if ($databases) {
    foreach ($db in $databases) {
        if ($db.name -match "databases/\(default\)$") {
            $hasDefaultDb = $true
            Write-Host "[+] Firestore (default) database already exists in mode: $($db.type)" -ForegroundColor Green
            break
        }
    }
}

if (-not $hasDefaultDb) {
    Write-Host "  -> Creating Firestore database '(default)' in Native mode ($Region)..." -NoNewline
    & $gcloud firestore databases create --location=$Region --type=firestore-native --project=$ProjectId --quiet
    Write-Host " [CREATED]" -ForegroundColor Green
}

# 5. Create Runtime Service Account with Least Privilege
Write-Host "`n--- Step 4: Configuring Least-Privilege IAM Service Account ---" -ForegroundColor Cyan
$saName = "cloudport-register-sa"
$saEmail = "$saName@$ProjectId.iam.gserviceaccount.com"

$existingSa = (& $gcloud iam service-accounts describe $saEmail --project=$ProjectId 2>$null)
if (-not $existingSa) {
    Write-Host "  -> Creating service account: $saName..." -NoNewline
    & $gcloud iam service-accounts create $saName `
        --description="Runtime service account for CloudPort registration function" `
        --display-name="cloudport-register-sa" `
        --project=$ProjectId --quiet
    Write-Host " [CREATED]" -ForegroundColor Green
} else {
    Write-Host "[+] Service account already exists: $saEmail" -ForegroundColor Green
}

# Assign roles/datastore.user
Write-Host "  -> Binding roles/datastore.user..." -NoNewline
& $gcloud projects add-iam-policy-binding $ProjectId `
    --member="serviceAccount:$saEmail" `
    --role="roles/datastore.user" `
    --condition=None --quiet > $null
Write-Host " [BOUND]" -ForegroundColor Green

# 6. Deploy Backend Cloud Function (2nd Gen)
Write-Host "`n--- Step 5: Deploying Backend Cloud Function (Python 3.12) ---" -ForegroundColor Cyan
$functionName = "cloudport-register"

& $gcloud functions deploy $functionName `
    --gen2 `
    --runtime=python312 `
    --region=$Region `
    --source=./backend `
    --entry-point=register_user `
    --trigger-http `
    --allow-unauthenticated `
    --service-account=$saEmail `
    --set-env-vars="PROJECT_ID=$ProjectId,COLLECTION=registrations,ALLOWED_ORIGINS=*" `
    --project=$ProjectId --quiet

$functionUrl = (& $gcloud functions describe $functionName --gen2 --region=$Region --project=$ProjectId --format="value(serviceConfig.uri)" 2>$null).Trim()
Write-Host "[+] Cloud Function Deployed Successfully!" -ForegroundColor Green
Write-Host "[+] Live Function Trigger URL: $functionUrl" -ForegroundColor Yellow

# 7. Update Frontend Runtime Config
Write-Host "`n--- Step 6: Injecting Live URL into Frontend Config ---" -ForegroundColor Cyan
$configContent = @"
// Runtime configuration injected automatically during deployment
window.CLOUDPORT_CONFIG = {
  ENDPOINT: '$functionUrl'
};
"@
Set-Content -Path "frontend/config.js" -Value $configContent -Encoding UTF8
Write-Host "[+] frontend/config.js updated with live endpoint." -ForegroundColor Green

# 8. Create and Deploy Static Frontend to Cloud Storage
Write-Host "`n--- Step 7: Deploying Static Website to Google Cloud Storage ---" -ForegroundColor Cyan
$bucketName = "$ProjectId-cloudport-site"

$existingBucket = (& $gcloud storage buckets describe "gs://$bucketName" 2>$null)
if (-not $existingBucket) {
    Write-Host "  -> Creating public website bucket: gs://$bucketName..." -NoNewline
    & $gcloud storage buckets create "gs://$bucketName" --location=$Region --project=$ProjectId --quiet
    Write-Host " [CREATED]" -ForegroundColor Green
} else {
    Write-Host "[+] Bucket already exists: gs://$bucketName" -ForegroundColor Green
}

# Configure website index page
& $gcloud storage buckets update "gs://$bucketName" --web-main-page-suffix=index.html --web-error-page=index.html --quiet

# Grant public read access (roles/storage.objectViewer on allUsers)
& $gcloud storage buckets add-iam-policy-binding "gs://$bucketName" `
    --member="allUsers" `
    --role="roles/storage.objectViewer" --quiet > $null

# Upload frontend files with correct Content-Types
Write-Host "  -> Uploading frontend assets..." -ForegroundColor Cyan
& $gcloud storage cp frontend/index.html "gs://$bucketName/index.html" --content-type="text/html; charset=utf-8" --quiet
& $gcloud storage cp frontend/style.css "gs://$bucketName/style.css" --content-type="text/css; charset=utf-8" --quiet
& $gcloud storage cp frontend/script.js "gs://$bucketName/script.js" --content-type="application/javascript; charset=utf-8" --quiet
& $gcloud storage cp frontend/config.js "gs://$bucketName/config.js" --content-type="application/javascript; charset=utf-8" --quiet
& $gcloud storage cp -r frontend/assets "gs://$bucketName/" --quiet

$siteUrl = "https://storage.googleapis.com/$bucketName/index.html"
Write-Host "[+] Frontend Deployed Successfully!" -ForegroundColor Green
Write-Host "[+] Live Website URL: $siteUrl" -ForegroundColor Yellow

# 9. Summary & Final Verification
Write-Host "`n=================================================================" -ForegroundColor Green
Write-Host " DEPLOYMENT COMPLETE — CLOUDPORT IS LIVE ON GCP" -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Green
Write-Host "  1. Live Website URL:        $siteUrl" -ForegroundColor Cyan
Write-Host "  2. Live Backend Endpoint:   $functionUrl" -ForegroundColor Cyan
Write-Host "  3. Firestore Collection:    registrations" -ForegroundColor Cyan
Write-Host "  4. Runtime Service Account: $saEmail" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Green
