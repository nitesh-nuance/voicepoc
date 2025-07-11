# Simple Function Code Deployment Script
Write-Host "Deploying Function Code to Existing Azure Function App..." -ForegroundColor Green

# Configuration - UPDATE THESE VALUES
$functionAppName = "HealthcareAgent-Functions-ng1"        # Replace with your function app name
$resourceGroup = "HealthcareAgent-RG"         # Replace with your resource group name
$subscriptionId = "e9388b1b-5aa8-49fd-a0ab-fb7e3c0a90a3"            # Replace with your subscription ID (optional)

Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "   Function App: $functionAppName" -ForegroundColor White
Write-Host "   Resource Group: $resourceGroup" -ForegroundColor White
Write-Host ""

# Prompt user to confirm/update configuration
Write-Host "Please update the configuration above in this script, or provide the details now:" -ForegroundColor Cyan
$userFunctionApp = Read-Host "Function App Name [$functionAppName]"
$userResourceGroup = Read-Host "Resource Group Name [$resourceGroup]"

if ($userFunctionApp) { $functionAppName = $userFunctionApp }
if ($userResourceGroup) { $resourceGroup = $userResourceGroup }

Write-Host ""
Write-Host "Using Configuration:" -ForegroundColor Yellow
Write-Host "   Function App: $functionAppName" -ForegroundColor White
Write-Host "   Resource Group: $resourceGroup" -ForegroundColor White
Write-Host ""

try {
    # Verify Azure CLI is logged in
    Write-Host "[1] Checking Azure CLI authentication..." -ForegroundColor Cyan
    $account = az account show --output json | ConvertFrom-Json
    if ($account) {
        Write-Host "Logged in as: $($account.user.name)" -ForegroundColor Green
        Write-Host "Subscription: $($account.name)" -ForegroundColor White
    } else {
        Write-Host "ERROR: Not logged in to Azure CLI. Please run 'az login'" -ForegroundColor Red
        exit 1
    }

    # Verify function app exists
    Write-Host "[2] Verifying Function App exists..." -ForegroundColor Cyan
    $functionApp = az functionapp show --name $functionAppName --resource-group $resourceGroup --output json 2>$null | ConvertFrom-Json
    
    if ($functionApp) {
        Write-Host "SUCCESS: Function App found: $($functionApp.defaultHostName)" -ForegroundColor Green
        Write-Host "Location: $($functionApp.location)" -ForegroundColor White
        Write-Host "Runtime: $($functionApp.siteConfig.linuxFxVersion)" -ForegroundColor White
    } else {
        Write-Host "ERROR: Function App '$functionAppName' not found in resource group '$resourceGroup'" -ForegroundColor Red
        Write-Host "Please check the function app name and resource group" -ForegroundColor Yellow
        exit 1
    }

    # Check if Azure Functions Core Tools is installed
    Write-Host "[3] Checking Azure Functions Core Tools..." -ForegroundColor Cyan
    $funcVersion = func --version 2>$null
    if ($funcVersion) {
        Write-Host "SUCCESS: Azure Functions Core Tools found: $funcVersion" -ForegroundColor Green
    } else {
        Write-Host "ERROR: Azure Functions Core Tools not found" -ForegroundColor Red
        Write-Host "Please install it: npm install -g azure-functions-core-tools@4 --unsafe-perm true" -ForegroundColor Yellow
        exit 1
    }

    # Deploy function code
    Write-Host "[4] Deploying Function Code..." -ForegroundColor Cyan
    Write-Host "Publishing to: $functionAppName" -ForegroundColor Yellow
    
    $publishResult = func azure functionapp publish $functionAppName --python
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "SUCCESS: Function Code deployed successfully!" -ForegroundColor Green
        
        # Get function app URL
        $functionUrl = "https://$($functionApp.defaultHostName)"
        
        Write-Host ""
        Write-Host "DEPLOYMENT COMPLETE!" -ForegroundColor Green
        Write-Host "Function URL: $functionUrl" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Test Endpoints:" -ForegroundColor Yellow
        Write-Host "   GetToken:     $functionUrl/api/GetToken" -ForegroundColor White
        Write-Host "   MakeTestCall: $functionUrl/api/MakeTestCall" -ForegroundColor White
        Write-Host "   CallWebhook:  $functionUrl/api/CallWebhook" -ForegroundColor White
        Write-Host ""
        Write-Host "Test with: final-production-call-client.html" -ForegroundColor Cyan
        Write-Host "Enter this URL in the client: $functionUrl" -ForegroundColor Cyan
        
        # Update environment variables if needed
        Write-Host ""
        $updateEnvVars = Read-Host "Do you want to update environment variables (ACS_CONNECTION_STRING, etc.)? [y/N]"
        if ($updateEnvVars -eq "y" -or $updateEnvVars -eq "Y") {
            Write-Host "[5] Updating Environment Variables..." -ForegroundColor Cyan
            
            $acsConnectionString = Read-Host "ACS Connection String (leave empty to skip)"
            $targetUserId = Read-Host "Target User ID (leave empty to skip)"
            
            if ($acsConnectionString) {
                az functionapp config appsettings set --name $functionAppName --resource-group $resourceGroup --settings "ACS_CONNECTION_STRING=$acsConnectionString"
                Write-Host "SUCCESS: ACS_CONNECTION_STRING updated" -ForegroundColor Green
            }
            
            if ($targetUserId) {
                az functionapp config appsettings set --name $functionAppName --resource-group $resourceGroup --settings "TARGET_USER_ID=$targetUserId"
                Write-Host "SUCCESS: TARGET_USER_ID updated" -ForegroundColor Green
            }
            
            # Set callback URL base
            $callbackUrlBase = "https://$($functionApp.defaultHostName)"
            az functionapp config appsettings set --name $functionAppName --resource-group $resourceGroup --settings "CALLBACK_URL_BASE=$callbackUrlBase"
            Write-Host "SUCCESS: CALLBACK_URL_BASE updated" -ForegroundColor Green
        }
        
    } else {
        Write-Host "ERROR: Function deployment failed" -ForegroundColor Red
        Write-Host "Check the output above for error details" -ForegroundColor Yellow
    }
}
catch {
    Write-Host "ERROR: Deployment failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Stack trace: $($_.Exception.StackTrace)" -ForegroundColor Red
}

Write-Host ""
Write-Host "Press Enter to continue..." -ForegroundColor Gray
Read-Host
