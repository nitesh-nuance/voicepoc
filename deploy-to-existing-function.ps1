# Enhanced Function Code Deployment Script for Voice POC Healthcare Agent
# Compatible with Modular Endpoint Architecture v3.0
# Supports: Health, Phone, VoIP, Bot, Patient, and Appointment endpoints
Write-Host "Deploying Voice POC Healthcare Agent Function to Azure..." -ForegroundColor Green
Write-Host "Using Modular Endpoint Architecture v3.0" -ForegroundColor Cyan

# Configuration - UPDATE THESE VALUES
$functionAppName = "nurse-voice-agent-function"        # Replace with your function app name
$resourceGroup = "nurse-voice-agent-rg"         # Updated to match new subscription
$subscriptionId = "eb07a656-0cab-472b-8725-c175d2d8ae22"            # HLS-PEI-Nursing-Prototype subscription

# Required Environment Variables - UPDATED FOR HLS-PEI-Nursing-Prototype
$envVariables = @{
    # Azure Communication Services Configuration
    "ACS_CONNECTION_STRING" = "endpoint=https://nurse-voice-agent-acs.unitedstates.communication.azure.com/;accesskey=1U8o8R5VI69cOoMUgfBpErMWEyiCLq9e2jV3sqM6WrPFQfQ6qA5iJQQJ99BGACULyCpAArohAAAAAZCS7Hak"
    "TARGET_USER_ID" = "8:acs:YOUR-ACS-USER-ID-HERE"
    "COGNITIVE_SERVICES_ENDPOINT" = "https://nurse-voice-agent-cognitive-serv.cognitiveservices.azure.com/"
    "COGNITIVE_SERVICES_KEY" = "BhMHQvcmg5DUgpcuIiQ3mKXhKAxto4vfDLepNxhFR2RuhJbfKbl7JQQJ99BGACHYHv6XJ3w3AAAEACOGd6nv"
    
    # Bot Service Configuration
    "BOT_APP_ID" = "39188ba4-899a-4c87-a7a9-a35b52eb1891"
    "BOT_APP_PASSWORD" = "jz48Q~VxYZN_uLM6TgypoZbMUxSsHxCX1~oDta7y"
    "BOT_SERVICE_ENDPOINT" = ""
    
    # OpenAI Configuration - Updated for new subscription
    "OPENAI_API_KEY" = "AnGHReGBiy6iGtBoBgPqhY6j8CFY2EHFyENYrcRYGBOLiz7mGucyJQQJ99BGACHYHv6XJ3w3AAABACOGCBRr"
    "OPENAI_ENDPOINT" = "https://nurse-voice-agent-openai.openai.azure.com/"
    "OPENAI_MODEL" = "gpt-4o-mini"
    
    # Cosmos DB Configuration (Optional)
    "COSMOS_CONNECTION_STRING" = "AccountEndpoint=https://healthcareagent-cosmos-ng01.documents.azure.com:443/;AccountKey=YOUR_COSMOS_DB_KEY_HERE;"
    
    # TTS Configuration
    "WELCOME_MESSAGE" = "Hello! This is your Azure Communication Services assistant. The call connection is working perfectly. You can now hear automated messages through Azure's text-to-speech service. Thank you for testing the voice integration."
    "TTS_VOICE" = "en-US-JennyNeural"
    
    # Function App Configuration (will be set automatically)
    "CALLBACK_URL_BASE" = ""  # This will be set to the function app URL
    "FUNCTIONS_WORKER_RUNTIME" = "python"
    "AzureWebJobsStorage" = ""  # This will be set automatically
}

Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "   Function App: $functionAppName" -ForegroundColor White
Write-Host "   Resource Group: $resourceGroup" -ForegroundColor White
Write-Host "   Subscription ID: $subscriptionId" -ForegroundColor White
Write-Host ""

# Display current environment variables that will be set
Write-Host "Environment Variables to Configure:" -ForegroundColor Yellow
foreach ($key in $envVariables.Keys) {
    $value = $envVariables[$key]
    if ($value -and $value.Length -gt 50) {
        $displayValue = $value.Substring(0, 50) + "..."
    } elseif ($value) {
        $displayValue = $value
    } else {
        $displayValue = "[Will be set automatically]"
    }
    Write-Host "   $key = $displayValue" -ForegroundColor White
}
Write-Host ""

# Prompt user to confirm/update configuration
Write-Host "Please update the configuration above in this script, or provide the details now:" -ForegroundColor Cyan
$userFunctionApp = Read-Host "Function App Name [$functionAppName]"
$userResourceGroup = Read-Host "Resource Group Name [$resourceGroup]"
$updateEnvVars = Read-Host "Do you want to update environment variables interactively? [y/N]"

if ($userFunctionApp) { $functionAppName = $userFunctionApp }
if ($userResourceGroup) { $resourceGroup = $userResourceGroup }

# Interactive environment variable updates if requested
if ($updateEnvVars -eq "y" -or $updateEnvVars -eq "Y") {
    Write-Host ""
    Write-Host "Updating Environment Variables Interactively..." -ForegroundColor Cyan
    
    # ACS Configuration
    $acsConnectionString = Read-Host "ACS Connection String (current: $($envVariables['ACS_CONNECTION_STRING'].Substring(0, 50))...)"
    if ($acsConnectionString) { $envVariables["ACS_CONNECTION_STRING"] = $acsConnectionString }
    
    $targetUserId = Read-Host "Target User ID (current: $($envVariables['TARGET_USER_ID']))"
    if ($targetUserId) { $envVariables["TARGET_USER_ID"] = $targetUserId }
    
    $cognitiveServicesEndpoint = Read-Host "Cognitive Services Endpoint (current: $($envVariables['COGNITIVE_SERVICES_ENDPOINT']))"
    if ($cognitiveServicesEndpoint) { 
        # Normalize the endpoint URL
        $cognitiveServicesEndpoint = $cognitiveServicesEndpoint.Trim()
        if (-not $cognitiveServicesEndpoint.EndsWith("/")) {
            $cognitiveServicesEndpoint += "/"
        }
        $envVariables["COGNITIVE_SERVICES_ENDPOINT"] = $cognitiveServicesEndpoint 
    }
    
    # OpenAI Configuration
    $openaiApiKey = Read-Host "OpenAI API Key (current: $($envVariables['OPENAI_API_KEY'].Substring(0, 20))...)"
    if ($openaiApiKey) { $envVariables["OPENAI_API_KEY"] = $openaiApiKey }
    
    $openaiEndpoint = Read-Host "OpenAI Endpoint (current: $($envVariables['OPENAI_ENDPOINT']))"
    if ($openaiEndpoint) { $envVariables["OPENAI_ENDPOINT"] = $openaiEndpoint }
    
    # Cosmos DB Configuration
    $cosmosConnectionString = Read-Host "Cosmos DB Connection String (optional, current: $($envVariables['COSMOS_CONNECTION_STRING'].Substring(0, 50))...)"
    if ($cosmosConnectionString) { $envVariables["COSMOS_CONNECTION_STRING"] = $cosmosConnectionString }
}

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
        Write-Host "Current subscription: $($account.name)" -ForegroundColor White
        Write-Host "Current subscription ID: $($account.id)" -ForegroundColor White
        
        # Check if we need to switch subscriptions
        if ($subscriptionId -and $account.id -ne $subscriptionId) {
            Write-Host ""
            Write-Host "⚠️  SUBSCRIPTION MISMATCH!" -ForegroundColor Yellow
            Write-Host "   Script is configured for subscription ID: $subscriptionId" -ForegroundColor White
            Write-Host "   Currently logged into subscription ID: $($account.id)" -ForegroundColor White
            Write-Host ""
            
            $switchSubscription = Read-Host "Do you want to switch to the configured subscription? [y/N]"
            if ($switchSubscription -eq "y" -or $switchSubscription -eq "Y") {
                Write-Host "Switching to subscription: $subscriptionId..." -ForegroundColor Cyan
                az account set --subscription $subscriptionId
                
                if ($LASTEXITCODE -eq 0) {
                    # Verify the switch was successful
                    $newAccount = az account show --output json | ConvertFrom-Json
                    Write-Host "✅ Successfully switched to subscription: $($newAccount.name)" -ForegroundColor Green
                    $account = $newAccount
                } else {
                    Write-Host "❌ Failed to switch subscription. Please check if you have access to subscription: $subscriptionId" -ForegroundColor Red
                    Write-Host "Available subscriptions:" -ForegroundColor Yellow
                    az account list --query "[].{Name:name, Id:id, State:state}" --output table
                    exit 1
                }
            } else {
                Write-Host "Continuing with current subscription..." -ForegroundColor Yellow
                Write-Host "⚠️  Warning: This may cause deployment to fail if resources are in a different subscription" -ForegroundColor Yellow
            }
        } else {
            Write-Host "✅ Subscription matches configuration" -ForegroundColor Green
        }
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

    # Validate environment variables before deployment
    Write-Host "[3.5] Validating Environment Variables..." -ForegroundColor Cyan

    $validationErrors = @()

    # Validate COGNITIVE_SERVICES_ENDPOINT
    if ($envVariables["COGNITIVE_SERVICES_ENDPOINT"]) {
        $cognitiveEndpoint = $envVariables["COGNITIVE_SERVICES_ENDPOINT"]
        if ($cognitiveEndpoint -notmatch "^https://.*\.cognitiveservices\.azure\.com/?$") {
            $validationErrors += "COGNITIVE_SERVICES_ENDPOINT format is invalid. Expected: https://your-resource.cognitiveservices.azure.com/"
        }
        Write-Host "  COGNITIVE_SERVICES_ENDPOINT: $cognitiveEndpoint" -ForegroundColor White
    } else {
        $validationErrors += "COGNITIVE_SERVICES_ENDPOINT is required"
    }

    # Validate ACS_CONNECTION_STRING
    if ($envVariables["ACS_CONNECTION_STRING"]) {
        $acsConnection = $envVariables["ACS_CONNECTION_STRING"]
        if ($acsConnection -notmatch "^endpoint=https://.*\.communication\.azure\.com/;accesskey=.*$") {
            $validationErrors += "ACS_CONNECTION_STRING format is invalid"
        }
        Write-Host "  ACS_CONNECTION_STRING: [CONFIGURED]" -ForegroundColor White
    } else {
        $validationErrors += "ACS_CONNECTION_STRING is required"
    }

    # Validate OPENAI_ENDPOINT
    if ($envVariables["OPENAI_ENDPOINT"]) {
        $openaiEndpoint = $envVariables["OPENAI_ENDPOINT"]
        if ($openaiEndpoint -notmatch "^https://.*\.openai\.azure\.com/?$") {
            $validationErrors += "OPENAI_ENDPOINT format is invalid. Expected: https://your-resource.openai.azure.com/"
        }
        Write-Host "  OPENAI_ENDPOINT: $openaiEndpoint" -ForegroundColor White
    }

    # Display validation results
    if ($validationErrors.Count -gt 0) {
        Write-Host "VALIDATION ERRORS:" -ForegroundColor Red
        foreach ($error in $validationErrors) {
            Write-Host "  - $error" -ForegroundColor Yellow
        }
        Write-Host ""
        $continueAnyway = Read-Host "Continue with deployment anyway? [y/N]"
        if ($continueAnyway -ne "y" -and $continueAnyway -ne "Y") {
            Write-Host "Deployment cancelled. Please fix the validation errors and try again." -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "SUCCESS: All environment variables validated" -ForegroundColor Green
    }
    Write-Host ""

    # Deploy function code
    Write-Host "[4] Deploying Function Code..." -ForegroundColor Cyan
    Write-Host "Publishing to: $functionAppName" -ForegroundColor Yellow
    
    # Build and publish with Python runtime
    $publishResult = func azure functionapp publish $functionAppName --python
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "SUCCESS: Function Code deployed successfully!" -ForegroundColor Green
        
        # Get function app URL
        $functionUrl = "https://$($functionApp.defaultHostName)"
        
        # Update environment variables automatically
        Write-Host "[5] Configuring Environment Variables..." -ForegroundColor Cyan
        
        # Set the callback URL base first
        $envVariables["CALLBACK_URL_BASE"] = $functionApp.defaultHostName
        
        # Get storage connection string for the function app
        $storageConnectionString = az functionapp config appsettings list --name $functionAppName --resource-group $resourceGroup --query "[?name=='AzureWebJobsStorage'].value" --output tsv
        if ($storageConnectionString) {
            $envVariables["AzureWebJobsStorage"] = $storageConnectionString
        }
        
        # Build settings string for batch update
        $settingsArray = @()
        foreach ($key in $envVariables.Keys) {
            if ($envVariables[$key]) {
                # Properly escape the value to handle URLs and special characters
                $escapedValue = $envVariables[$key] -replace '"', '\"'
                $settingsArray += "$key=`"$escapedValue`""
            }
        }
        
        # Update all environment variables in batch
        if ($settingsArray.Count -gt 0) {
            Write-Host "Updating $($settingsArray.Count) environment variables..." -ForegroundColor Yellow
            
            # Split into smaller batches to avoid command line length limits
            $batchSize = 5  # Reduced batch size to avoid issues with long URLs
            for ($i = 0; $i -lt $settingsArray.Count; $i += $batchSize) {
                $batch = $settingsArray[$i..([Math]::Min($i + $batchSize - 1, $settingsArray.Count - 1))]
                
                Write-Host "Updating batch $([Math]::Floor($i / $batchSize) + 1)..." -ForegroundColor Gray
                
                # Use individual setting updates to avoid command line parsing issues
                foreach ($setting in $batch) {
                    $parts = $setting -split '=', 2
                    $settingKey = $parts[0]
                    $settingValue = $parts[1] -replace '^"|"$', ''  # Remove surrounding quotes
                    
                    Write-Host "  Setting: $settingKey" -ForegroundColor DarkGray
                    az functionapp config appsettings set --name $functionAppName --resource-group $resourceGroup --settings "$settingKey=$settingValue"
                    
                    if ($LASTEXITCODE -eq 0) {
                        Write-Host "  SUCCESS: $settingKey updated" -ForegroundColor Green
                    } else {
                        Write-Host "  WARNING: Failed to update $settingKey" -ForegroundColor Yellow
                    }
                }
            }
        }
        
        # Enable CORS for the function app to allow web client access
        Write-Host "[6] Configuring CORS..." -ForegroundColor Cyan
        az functionapp cors add --name $functionAppName --resource-group $resourceGroup --allowed-origins "*" 2>$null
        Write-Host "SUCCESS: CORS configured to allow all origins" -ForegroundColor Green
        
        Write-Host ""
        Write-Host "DEPLOYMENT COMPLETE!" -ForegroundColor Green
        Write-Host "Function URL: $functionUrl" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Available Endpoints (Modular Architecture v3.0):" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "   Health & Token Endpoints:" -ForegroundColor Cyan
        Write-Host "     Health Check:          $functionUrl/api/health_check" -ForegroundColor White
        Write-Host "     Get Token:             $functionUrl/api/get_token" -ForegroundColor White
        Write-Host ""
        Write-Host "   Phone Calling Endpoints (PSTN):" -ForegroundColor Cyan
        Write-Host "     Make Phone Call:       $functionUrl/api/make_phone_call" -ForegroundColor White
        Write-Host "     Phone Call Webhook:    $functionUrl/api/phone_call_webhook" -ForegroundColor White
        Write-Host "     Get Call Status:       $functionUrl/api/get_call_status" -ForegroundColor White
        Write-Host ""
        Write-Host "   VoIP Calling Endpoints:" -ForegroundColor Cyan
        Write-Host "     Make VoIP Call:        $functionUrl/api/make_voip_call" -ForegroundColor White
        Write-Host "     VoIP Call Webhook:     $functionUrl/api/voip_call_webhook" -ForegroundColor White
        Write-Host "     Make Test Call:        $functionUrl/api/make_test_call" -ForegroundColor White
        Write-Host ""
        Write-Host "   Bot Service Endpoints:" -ForegroundColor Cyan
        Write-Host "     Bot Messages:          $functionUrl/api/bot/messages" -ForegroundColor White
        Write-Host "     Test Bot Call:         $functionUrl/api/test_bot_call" -ForegroundColor White
        Write-Host ""
        Write-Host "   Patient Management Endpoints:" -ForegroundColor Cyan
        Write-Host "     Patients (CRUD):       $functionUrl/api/patients" -ForegroundColor White
        Write-Host "     Patient by ID:         $functionUrl/api/patients/{patient_id}" -ForegroundColor White
        Write-Host ""
        Write-Host "   Appointment Management Endpoints:" -ForegroundColor Cyan
        Write-Host "     Appointments (CRUD):   $functionUrl/api/appointments" -ForegroundColor White
        Write-Host "     Appointment by ID:     $functionUrl/api/appointments/{appointment_id}" -ForegroundColor White
        Write-Host ""
        Write-Host "   Architecture Information:" -ForegroundColor Cyan
        Write-Host "     Architecture Info:     $functionUrl/api/architecture_info" -ForegroundColor White
        Write-Host ""
        Write-Host "Test Clients:" -ForegroundColor Yellow
        Write-Host "   Use any HTML client in your repository" -ForegroundColor Cyan
        Write-Host "   Enter this URL in the client: $functionUrl" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Bot Service Configuration:" -ForegroundColor Yellow
        Write-Host "   Bot Messaging Endpoint: $functionUrl/api/bot/messages" -ForegroundColor Cyan
        Write-Host "   Configure this URL in your Azure Bot Service" -ForegroundColor Gray
        
        # Test the deployment
        Write-Host ""
        Write-Host "[7] Testing Deployment..." -ForegroundColor Cyan
        try {
            $testResponse = Invoke-RestMethod -Uri "$functionUrl/api/health_check" -Method GET -TimeoutSec 30
            if ($testResponse) {
                Write-Host "SUCCESS: Function app is responding" -ForegroundColor Green
                Write-Host "Health check endpoint test passed" -ForegroundColor Green
                if ($testResponse.status -eq "healthy") {
                    Write-Host "All services are properly configured" -ForegroundColor Green
                } elseif ($testResponse.status -eq "partial") {
                    Write-Host "Some services may need configuration (this is normal)" -ForegroundColor Yellow
                }
            } else {
                Write-Host "WARNING: Function app response was empty" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "WARNING: Function app test failed: $($_.Exception.Message)" -ForegroundColor Yellow
            Write-Host "The function may still be starting up. Wait a few minutes and test manually." -ForegroundColor Gray
        }
        
        # Test architecture info endpoint
        try {
            $archResponse = Invoke-RestMethod -Uri "$functionUrl/api/architecture_info" -Method GET -TimeoutSec 30
            if ($archResponse -and $archResponse.version) {
                Write-Host "Architecture version: $($archResponse.version)" -ForegroundColor Green
                Write-Host "Total endpoints: $($archResponse.total_endpoints)" -ForegroundColor Green
            }
        } catch {
            Write-Host "Note: Architecture info endpoint test failed (not critical)" -ForegroundColor Gray
        }
        
        # Final instructions
        Write-Host ""
        Write-Host "POST-DEPLOYMENT STEPS:" -ForegroundColor Yellow
        Write-Host "1. Test the function endpoints using the URLs above" -ForegroundColor White
        Write-Host "2. Configure your Azure Bot Service with the messaging endpoint" -ForegroundColor White
        Write-Host "3. Update any hardcoded values in the environment variables if needed" -ForegroundColor White
        Write-Host "4. Test the calling functionality with the web clients" -ForegroundColor White
        Write-Host "5. Verify modular architecture is working: $functionUrl/api/architecture_info" -ForegroundColor White
        Write-Host ""
        Write-Host "MODULAR ARCHITECTURE BENEFITS:" -ForegroundColor Green
        Write-Host "✅ Maximum code organization and maintainability" -ForegroundColor White
        Write-Host "✅ Clear separation of endpoint concerns by functional area" -ForegroundColor White
        Write-Host "✅ Each endpoint module can be independently modified and tested" -ForegroundColor White
        Write-Host "✅ Minimal function_app.py with focused responsibility as orchestrator" -ForegroundColor White
        Write-Host "✅ Easy to add new endpoint modules without touching existing code" -ForegroundColor White
        Write-Host ""
        Write-Host "IMPORTANT NOTES:" -ForegroundColor Red
        Write-Host "- Update ACS_CONNECTION_STRING with your actual ACS access key" -ForegroundColor Yellow
        Write-Host "- Update TARGET_USER_ID with your actual ACS user ID" -ForegroundColor Yellow
        Write-Host "- Update OPENAI_API_KEY if you have your own OpenAI resource" -ForegroundColor Yellow
        Write-Host "- Update COSMOS_CONNECTION_STRING if using Cosmos DB" -ForegroundColor Yellow
        
    } else {
        Write-Host "ERROR: Function deployment failed" -ForegroundColor Red
        Write-Host "Check the output above for error details" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Common issues:" -ForegroundColor Yellow
        Write-Host "- Ensure you're in the correct directory with function_app.py" -ForegroundColor White
        Write-Host "- Check that requirements.txt is present and contains all dependencies" -ForegroundColor White
        Write-Host "- Verify Azure CLI is authenticated and has proper permissions" -ForegroundColor White
        Write-Host "- Ensure the function app exists and is accessible" -ForegroundColor White
    }
}
catch {
    Write-Host "ERROR: Deployment failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Stack trace: $($_.Exception.StackTrace)" -ForegroundColor Red
    
    Write-Host ""
    Write-Host "TROUBLESHOOTING TIPS:" -ForegroundColor Yellow
    Write-Host "1. Ensure Azure CLI is installed and authenticated: az login" -ForegroundColor White
    Write-Host "2. Verify Azure Functions Core Tools: npm install -g azure-functions-core-tools@4" -ForegroundColor White
    Write-Host "3. Check that the function app and resource group exist" -ForegroundColor White
    Write-Host "4. Ensure you have proper permissions on the Azure subscription" -ForegroundColor White
    Write-Host "5. Try running the script from the directory containing function_app.py" -ForegroundColor White
}

Write-Host ""
Write-Host "DEPLOYMENT SCRIPT COMPLETED" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "1. Test your endpoints using the URLs provided above" -ForegroundColor White
Write-Host "2. Open your calling client and enter the function URL" -ForegroundColor White
Write-Host "3. Configure your Azure Bot Service messaging endpoint" -ForegroundColor White
Write-Host "4. Test bot calls using: $functionUrl/api/test_bot_call" -ForegroundColor White
Write-Host "5. Explore the modular architecture: $functionUrl/api/architecture_info" -ForegroundColor White
Write-Host ""
Write-Host "For support, check the Azure Function logs in the Azure portal" -ForegroundColor Gray
Write-Host "Press Enter to continue..." -ForegroundColor Gray
Read-Host
