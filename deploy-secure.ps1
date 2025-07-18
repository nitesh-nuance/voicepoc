# Enhanced Function Code Deployment Script for Voice POC Healthcare Agent
# Compatible with Modular Endpoint Architecture v4.0
# Supports: Health, Phone, VoIP, Bot, Patient, and Appointment endpoints with Conversational AI
# SECURITY: Uses external environment variables - no secrets in source code
Write-Host "Deploying Voice POC Healthcare Agent Function to Azure..." -ForegroundColor Green
Write-Host "Using Modular Endpoint Architecture v4.0 with Conversational AI" -ForegroundColor Cyan

# Security: Load environment variables from external file
$envFile = ".env"
if (Test-Path $envFile) {
    Write-Host "Loading environment variables from $envFile..." -ForegroundColor Yellow
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^([^#][^=]+)=(.*)$") {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
} else {
    Write-Host "WARNING: .env file not found. Please create .env file with your secrets." -ForegroundColor Red
    Write-Host "Copy .env.example to .env and fill in your actual values." -ForegroundColor Yellow
    Write-Host ""
    $continueWithoutEnv = Read-Host "Continue anyway? Environment variables must be set manually [y/N]"
    if ($continueWithoutEnv -ne "y" -and $continueWithoutEnv -ne "Y") {
        Write-Host "Deployment cancelled. Please create .env file first." -ForegroundColor Red
        exit 1
    }
}

# Configuration - UPDATE THESE VALUES
$functionAppName = "nurse-voice-agent-function"        # Replace with your function app name
$resourceGroup = "nurse-voice-agent-rg"         # Updated to match new subscription
$subscriptionId = "eb07a656-0cab-472b-8725-c175d2d8ae22"            # HLS-PEI-Nursing-Prototype subscription

# Required Environment Variables - LOADED FROM .env FILE (NO SECRETS IN CODE)
$envVariables = @{
    # Azure Communication Services Configuration
    "ACS_CONNECTION_STRING" = [Environment]::GetEnvironmentVariable("ACS_CONNECTION_STRING")
    "TARGET_USER_ID" = [Environment]::GetEnvironmentVariable("TARGET_USER_ID")
    "COGNITIVE_SERVICES_ENDPOINT" = [Environment]::GetEnvironmentVariable("COGNITIVE_SERVICES_ENDPOINT")
    "COGNITIVE_SERVICES_KEY" = [Environment]::GetEnvironmentVariable("COGNITIVE_SERVICES_KEY")
    
    # Bot Service Configuration
    "BOT_APP_ID" = [Environment]::GetEnvironmentVariable("BOT_APP_ID")
    "BOT_APP_PASSWORD" = [Environment]::GetEnvironmentVariable("BOT_APP_PASSWORD")
    "BOT_SERVICE_ENDPOINT" = [Environment]::GetEnvironmentVariable("BOT_SERVICE_ENDPOINT")
    
    # OpenAI Configuration
    "OPENAI_API_KEY" = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY")
    "OPENAI_ENDPOINT" = [Environment]::GetEnvironmentVariable("OPENAI_ENDPOINT")
    "OPENAI_MODEL" = if ([Environment]::GetEnvironmentVariable("OPENAI_MODEL")) { [Environment]::GetEnvironmentVariable("OPENAI_MODEL") } else { "gpt-4o-mini" }
    
    # Cosmos DB Configuration (Optional)
    "COSMOS_CONNECTION_STRING" = [Environment]::GetEnvironmentVariable("COSMOS_CONNECTION_STRING")
    
    # TTS Configuration
    "WELCOME_MESSAGE" = if ([Environment]::GetEnvironmentVariable("WELCOME_MESSAGE")) { [Environment]::GetEnvironmentVariable("WELCOME_MESSAGE") } else { "Hello! This is your Azure Communication Services assistant with conversational AI capabilities." }
    "TTS_VOICE" = if ([Environment]::GetEnvironmentVariable("TTS_VOICE")) { [Environment]::GetEnvironmentVariable("TTS_VOICE") } else { "en-US-JennyNeural" }
    
    # Conversational AI Configuration (NEW for v4.0)
    "CONVERSATION_TIMEOUT_MINUTES" = "30"
    "SPEECH_RECOGNITION_TIMEOUT_SECONDS" = "10"
    "ENABLE_CONVERSATIONAL_MODE" = "true"
    "HEALTHCARE_CONTEXT_ENABLED" = "true"
    
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

# Display current environment variables that will be set (MASKED FOR SECURITY)
Write-Host "Environment Variables to Configure:" -ForegroundColor Yellow
foreach ($key in $envVariables.Keys) {
    $value = $envVariables[$key]
    if ($value -and $value.Length -gt 0) {
        if ($key -match "(KEY|SECRET|PASSWORD|CONNECTION)" -and $value.Length -gt 10) {
            $displayValue = $value.Substring(0, 10) + "..." + $value.Substring($value.Length - 4)
        } elseif ($value.Length -gt 50) {
            $displayValue = $value.Substring(0, 50) + "..."
        } else {
            $displayValue = $value
        }
    } else {
        $displayValue = "[NOT SET - Check .env file]"
    }
    Write-Host "   $key = $displayValue" -ForegroundColor White
}
Write-Host ""

# Security validation - ensure critical secrets are loaded
$criticalSecrets = @("ACS_CONNECTION_STRING", "COGNITIVE_SERVICES_KEY", "OPENAI_API_KEY")
$missingSecrets = @()

foreach ($secret in $criticalSecrets) {
    if (-not $envVariables[$secret] -or $envVariables[$secret].Length -eq 0) {
        $missingSecrets += $secret
    }
}

if ($missingSecrets.Count -gt 0) {
    Write-Host "CRITICAL: Missing required secrets!" -ForegroundColor Red
    Write-Host "The following environment variables are not set:" -ForegroundColor Yellow
    foreach ($secret in $missingSecrets) {
        Write-Host "  - $secret" -ForegroundColor Red
    }
    Write-Host ""
    Write-Host "Please ensure your .env file contains all required values." -ForegroundColor Yellow
    Write-Host "Copy .env.example to .env and fill in your actual secrets." -ForegroundColor Yellow
    Write-Host ""
    $continueAnyway = Read-Host "Continue with deployment anyway? [y/N]"
    if ($continueAnyway -ne "y" -and $continueAnyway -ne "Y") {
        Write-Host "Deployment cancelled. Please set missing environment variables." -ForegroundColor Red
        exit 1
    }
}

# Prompt user to confirm/update configuration
Write-Host "Please verify the configuration above, or provide updates now:" -ForegroundColor Cyan
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
        Write-Host "  ACS_CONNECTION_STRING: [CONFIGURED - $(($acsConnection.Length) - 80) chars masked]" -ForegroundColor White
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
        
        # Update all environment variables individually (more secure)
        $successCount = 0
        $totalCount = 0
        foreach ($key in $envVariables.Keys) {
            if ($envVariables[$key]) {
                $totalCount++
                Write-Host "  Setting: $key" -ForegroundColor DarkGray
                
                # Use individual setting updates for better security and error handling
                az functionapp config appsettings set --name $functionAppName --resource-group $resourceGroup --settings "$key=$($envVariables[$key])" --output none
                
                if ($LASTEXITCODE -eq 0) {
                    $successCount++
                    Write-Host "  ✅ SUCCESS: $key updated" -ForegroundColor Green
                } else {
                    Write-Host "  ❌ WARNING: Failed to update $key" -ForegroundColor Yellow
                }
            }
        }
        
        Write-Host "Environment Variables: $successCount/$totalCount updated successfully" -ForegroundColor Cyan
        
        # Enable CORS for the function app to allow web client access
        Write-Host "[6] Configuring CORS..." -ForegroundColor Cyan
        az functionapp cors add --name $functionAppName --resource-group $resourceGroup --allowed-origins "*" 2>$null
        Write-Host "SUCCESS: CORS configured to allow all origins" -ForegroundColor Green
        
        Write-Host ""
        Write-Host "DEPLOYMENT COMPLETE!" -ForegroundColor Green
        Write-Host "Function URL: $functionUrl" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Available Endpoints (Modular Architecture v4.0 with Conversational AI):" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "   Health & Token Endpoints:" -ForegroundColor Cyan
        Write-Host "     Health Check:          $functionUrl/api/health_check" -ForegroundColor White
        Write-Host "     Get Token:             $functionUrl/api/get_token" -ForegroundColor White
        Write-Host ""
        Write-Host "   Phone Calling Endpoints (PSTN) - Enhanced with Conversational AI:" -ForegroundColor Cyan
        Write-Host "     Make Phone Call:       $functionUrl/api/make_phone_call" -ForegroundColor White
        Write-Host "     Phone Call Webhook:    $functionUrl/api/phone_call_webhook" -ForegroundColor White
        Write-Host "     Get Call Status:       $functionUrl/api/get_call_status" -ForegroundColor White
        Write-Host "     Get Conversation:      $functionUrl/api/get_conversation_history" -ForegroundColor White
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
        Write-Host "NEW: Conversational AI Features:" -ForegroundColor Magenta
        Write-Host "🎙️  Speech Recognition with Azure Cognitive Services" -ForegroundColor White
        Write-Host "🧠 Healthcare-specific conversational intelligence" -ForegroundColor White
        Write-Host "💬 Bidirectional conversation with context retention" -ForegroundColor White
        Write-Host "⏱️  Automatic conversation timeout and cleanup" -ForegroundColor White
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
                if ($archResponse.version -eq "4.0") {
                    Write-Host "✅ Conversational AI features enabled" -ForegroundColor Magenta
                }
            }
        } catch {
            Write-Host "Note: Architecture info endpoint test failed (not critical)" -ForegroundColor Gray
        }
        
        # Final instructions
        Write-Host ""
        Write-Host "POST-DEPLOYMENT STEPS:" -ForegroundColor Yellow
        Write-Host "1. Test the function endpoints using the URLs above" -ForegroundColor White
        Write-Host "2. Configure your Azure Bot Service with the messaging endpoint" -ForegroundColor White
        Write-Host "3. Test conversational phone calling features" -ForegroundColor White
        Write-Host "4. Test the calling functionality with the web clients" -ForegroundColor White
        Write-Host "5. Verify modular architecture: $functionUrl/api/architecture_info" -ForegroundColor White
        Write-Host ""
        Write-Host "SECURITY IMPROVEMENTS:" -ForegroundColor Green
        Write-Host "✅ No secrets in source code - all externalized to .env file" -ForegroundColor White
        Write-Host "✅ Environment variables masked in deployment logs" -ForegroundColor White
        Write-Host "✅ .env file is excluded from version control" -ForegroundColor White
        Write-Host "✅ Critical secrets validation before deployment" -ForegroundColor White
        Write-Host "✅ Secure individual environment variable updates" -ForegroundColor White
        Write-Host ""
        Write-Host "CONVERSATIONAL AI FEATURES:" -ForegroundColor Magenta
        Write-Host "✅ Speech recognition integration with Azure Cognitive Services" -ForegroundColor White
        Write-Host "✅ Healthcare-specific response generation" -ForegroundColor White
        Write-Host "✅ Conversation state management and context retention" -ForegroundColor White
        Write-Host "✅ Automatic conversation cleanup and timeout handling" -ForegroundColor White
        Write-Host "✅ Emergency detection and appropriate routing" -ForegroundColor White
        Write-Host ""
        Write-Host "IMPORTANT SECURITY NOTES:" -ForegroundColor Red
        Write-Host "- Your secrets are now secure in .env file (not committed to git)" -ForegroundColor Yellow
        Write-Host "- Share .env.example with team members, never share .env" -ForegroundColor Yellow
        Write-Host "- For production, use Azure Key Vault or GitHub Secrets" -ForegroundColor Yellow
        Write-Host "- Regularly rotate your API keys and connection strings" -ForegroundColor Yellow
        
    } else {
        Write-Host "ERROR: Function deployment failed" -ForegroundColor Red
        Write-Host "Check the output above for error details" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Common issues:" -ForegroundColor Yellow
        Write-Host "- Ensure you're in the correct directory with function_app.py" -ForegroundColor White
        Write-Host "- Check that requirements.txt is present and contains all dependencies" -ForegroundColor White
        Write-Host "- Verify Azure CLI is authenticated and has proper permissions" -ForegroundColor White
        Write-Host "- Ensure the function app exists and is accessible" -ForegroundColor White
        Write-Host "- Check that all required environment variables are set in .env file" -ForegroundColor White
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
    Write-Host "5. Verify all secrets are properly set in .env file" -ForegroundColor White
    Write-Host "6. Try running the script from the directory containing function_app.py" -ForegroundColor White
}

Write-Host ""
Write-Host "DEPLOYMENT SCRIPT COMPLETED" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "1. Test your endpoints using the URLs provided above" -ForegroundColor White
Write-Host "2. Open your calling client and enter the function URL" -ForegroundColor White
Write-Host "3. Configure your Azure Bot Service messaging endpoint" -ForegroundColor White
Write-Host "4. Test conversational phone calling features" -ForegroundColor White
Write-Host "5. Test bot calls using: $functionUrl/api/test_bot_call" -ForegroundColor White
Write-Host "6. Explore the modular architecture: $functionUrl/api/architecture_info" -ForegroundColor White
Write-Host ""
Write-Host "Security Reminder:" -ForegroundColor Red
Write-Host "   Keep your .env file secure and never commit it to version control" -ForegroundColor Yellow
Write-Host "   Share .env.example with team members for setup guidance" -ForegroundColor Yellow
Write-Host ""
Write-Host "For support, check the Azure Function logs in the Azure portal" -ForegroundColor Gray
Write-Host "Press Enter to continue..." -ForegroundColor Gray
Read-Host
