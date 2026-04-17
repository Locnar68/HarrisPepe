# Share Google Drive folder with service account
# Usage: .\share-drive-folder.ps1

# Load .env file
$envPath = ".\secrets\.env"
if (-not (Test-Path $envPath)) {
    Write-Error ".env file not found at: $envPath"
    Write-Host "Please run bootstrap first to generate .env"
    exit 1
}

# Parse .env
$env = @{}
Get-Content $envPath | ForEach-Object {
    if ($_ -match '^([^#][^=]+)=(.+)$') {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim('"')
        $env[$key] = $value
    }
}

# Get SA email and folder IDs
$projectId = $env['GCP_PROJECT_ID']
$saEmail = "$projectId-sa@$projectId.iam.gserviceaccount.com"
$folderIds = $env['GDRIVE_FOLDER_IDS'] -split ','

if (-not $folderIds) {
    Write-Error "No Drive folders configured in GDRIVE_FOLDER_IDS"
    exit 1
}

Write-Host "Service Account: $saEmail" -ForegroundColor Cyan
Write-Host "Folders to share: $($folderIds.Count)" -ForegroundColor Cyan
Write-Host ""

# Function to share a folder using Drive API
function Share-DriveFolder {
    param(
        [string]$FolderId,
        [string]$Email
    )
    
    Write-Host "Sharing folder $FolderId with $Email..." -ForegroundColor Yellow
    
    # Build the API request
    $body = @{
        role = "reader"
        type = "user"
        emailAddress = $Email
    } | ConvertTo-Json
    
    # Use gcloud to get access token
    $token = gcloud auth print-access-token
    
    if (-not $token) {
        Write-Error "Failed to get access token. Run: gcloud auth login"
        return $false
    }
    
    # Call Drive API to share
    $uri = "https://www.googleapis.com/drive/v3/files/$FolderId/permissions"
    
    try {
        $response = Invoke-RestMethod -Uri $uri `
            -Method Post `
            -Headers @{
                "Authorization" = "Bearer $token"
                "Content-Type" = "application/json"
            } `
            -Body $body
        
        Write-Host "✓ Shared successfully" -ForegroundColor Green
        return $true
    }
    catch {
        $errorDetails = $_.ErrorDetails.Message | ConvertFrom-Json -ErrorAction SilentlyContinue
        if ($errorDetails.error.message -like "*already has access*") {
            Write-Host "✓ Already shared (skipping)" -ForegroundColor Green
            return $true
        }
        Write-Error "Failed to share: $($_.Exception.Message)"
        return $false
    }
}

# Share all folders
$successCount = 0
foreach ($folderId in $folderIds) {
    if (Share-DriveFolder -FolderId $folderId.Trim() -Email $saEmail) {
        $successCount++
    }
    Start-Sleep -Milliseconds 500  # Rate limiting
}

Write-Host ""
Write-Host "Shared $successCount of $($folderIds.Count) folders" -ForegroundColor Cyan
Write-Host ""
Write-Host "To verify, check folder permissions at:" -ForegroundColor Yellow
foreach ($folderId in $folderIds) {
    Write-Host "  https://drive.google.com/drive/folders/$($folderId.Trim())"
}
