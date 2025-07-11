# TTS Audio Issue Diagnostic Guide

## Current Issue
- **Problem**: TTS is not audible on the web client
- **ACS Logs**: No `ACSCallAutomationIncomingOperations` logs found
- **Status**: Calls connect but no audio playback

---

## Step 1: Enable ACS Diagnostic Settings

### Check if Diagnostic Settings are Enabled
1. Go to **Azure Portal** > Your **Communication Services** resource
2. Navigate to **Monitoring** > **Diagnostic settings**
3. Check if any diagnostic settings exist

### Enable Diagnostic Settings (if missing)
1. Click **+ Add diagnostic setting**
2. **Name**: `ACS-CallAutomation-Logs`
3. **Categories to Enable**:
   - ✅ **Call Automation** (most important for TTS)
   - ✅ **Call Summary**
   - ✅ **Call Diagnostics**
   - ✅ **Chat**
   - ✅ **SMS**
4. **Destination**: Select your **Log Analytics workspace**
5. Click **Save**

**⚠️ Note**: It can take 5-15 minutes for logs to start appearing after enabling diagnostic settings.

---

## Step 2: Check Function App Logs

### Application Insights Query
```kql
traces
| where timestamp >= ago(2h)
| where message contains "TTS" or message contains "play_media" or message contains "PlayMessage"
| project timestamp, severityLevel, message, operation_Name
| order by timestamp desc
```

### Look for These Key Log Messages
- `"Created TextSource with voice: ..."`
- `"Initiating play_media request..."`
- `"play_media request completed"`
- `"TTS playback initiated. Operation ID: ..."`

---

## Step 3: Test Configuration

### Test Endpoint
Call this endpoint to verify your configuration:
```
GET https://healthcareagent-functions-ng1.azurewebsites.net/api/DebugConfig
```

### Expected Response Should Show:
```json
{
  "acsConnectionString": { "configured": true },
  "cognitiveServicesEndpoint": { 
    "configured": true, 
    "isEastUS2": true 
  },
  "targetUserId": { "configured": true },
  "ttsSettings": {
    "voice": "en-US-JennyNeural"
  }
}
```

---

## Step 4: Manual TTS Test

### Step-by-Step Manual Test
1. **Make a call**: 
   ```
   GET https://healthcareagent-functions-ng1.azurewebsites.net/api/MakeTestCall
   ```

2. **Answer the call** on your web client

3. **Copy the Call ID** from the response

4. **Manually trigger TTS**:
   ```
   GET https://healthcareagent-functions-ng1.azurewebsites.net/api/PlayMessage?callId=YOUR_CALL_ID&message=Testing TTS playback
   ```

5. **Check the response** - should show success and operation ID

---

## Step 5: Alternative Log Queries

### Check All Azure Diagnostics for Communication Services
```kql
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.COMMUNICATION"
| where TimeGenerated >= ago(2h)
| project TimeGenerated, ResourceType, Category, OperationName, ResultSignature, Level
| order by TimeGenerated desc
```

### Check for Any Call Automation Activity
```kql
search "*"
| where TimeGenerated >= ago(2h)
| where * contains "CallAutomation" or * contains "PlayMedia"
| project TimeGenerated, $table, *
| order by TimeGenerated desc
```

### Find All Available Tables Related to Communication
```kql
union withsource=TableName *
| where TimeGenerated >= ago(2h)
| where TableName contains "Communication" or TableName contains "Call" or TableName contains "ACS"
| summarize count() by TableName
| order by count_ desc
```

---

## Step 6: Common Issues and Solutions

### 🔥 FOUND ISSUE: "Action failed due to a bad request to Cognitive Services"

This error means ACS is successfully calling Cognitive Services, but the request is being rejected. This is typically caused by:

#### **Most Likely Causes:**
1. **Authentication failure** - ACS doesn't have permission to use Cognitive Services
2. **Wrong endpoint format** - The Cognitive Services endpoint URL is incorrect
3. **Missing managed identity** - ACS is not configured to authenticate with Cognitive Services
4. **Regional mismatch** - ACS and Cognitive Services are in different regions

#### **Immediate Solutions:**

### Issue 1: Fix Cognitive Services Authentication
**Error**: `Action failed due to a bad request to Cognitive Services`
**Solution**: 
1. **Enable Managed Identity for ACS**:
   - Go to Azure Portal → Your ACS resource → Identity
   - Turn on **System assigned** managed identity
   - Copy the **Object (principal) ID**

2. **Grant Permissions to Cognitive Services**:
   - Go to Your Cognitive Services resource → Access control (IAM)
   - Click **+ Add** → **Add role assignment**
   - Select **Cognitive Services User** role
   - Assign access to **Managed Identity**
   - Select your ACS resource
   - Click **Save**

### Issue 2: Fix Endpoint Format
**Current endpoint**: `https://eastus2.api.cognitive.microsoft.com/`
**Correct format should be**: `https://eastus2.api.cognitive.microsoft.com`
**Solution**: Remove the trailing slash from the endpoint

### Issue 3: Verify Regional Alignment
**Both resources must be in the same region**:
- ACS: Check in resource overview
- Cognitive Services: Check in resource overview
- Both should be **East US 2**

### Issue 3: Audio Routing Issues
**Symptoms**: TTS logs show success but no audio heard
**Solution**:
- Check if `play_to` parameter targets the correct participant
- Verify web client audio permissions and device selection

### Issue 4: Regional Mismatch
**Symptoms**: Intermittent failures or high latency
**Solution**:
- Ensure both ACS and Cognitive Services are in **East US 2**
- Verify endpoint URLs match the region

---

## Step 7: Enable Managed Identity for ACS (If Not Done)

### Azure CLI Commands
```bash
# Get your ACS resource ID
az communication list --query "[].{name:name, id:id, location:location}"

# Enable system-assigned managed identity
az communication identity assign --ids YOUR_ACS_RESOURCE_ID

# Get your Cognitive Services resource ID
az cognitiveservices account list --query "[].{name:name, id:id, location:location}"

# Grant Cognitive Services User role to ACS managed identity
az role assignment create \
  --assignee-object-id ACS_MANAGED_IDENTITY_OBJECT_ID \
  --assignee-principal-type ServicePrincipal \
  --role "Cognitive Services User" \
  --scope YOUR_COGNITIVE_SERVICES_RESOURCE_ID
```

---

## Step 8: Immediate Debugging Actions

### 1. Check Function Logs Now
After deploying the updated function:
```kql
traces
| where timestamp >= ago(30m)
| where message contains "TextSource" or message contains "play_media"
| order by timestamp desc
```

### 2. Test with Enhanced Logging
Use the `MakeTestCallWithAutoTTS` endpoint and watch for these log entries:
- Call creation
- TTS initiation with voice details
- Cognitive Services endpoint usage
- play_media completion

### 3. Monitor Both Services
Watch logs in both:
- **Function App Application Insights**
- **Communication Services Diagnostic Logs** (after enabling)

---

## Expected Timeline for Resolution

1. **Enable diagnostic settings**: 5-15 minutes for logs to appear
2. **Test enhanced logging**: Immediate feedback
3. **Configure managed identity**: If needed, 10-15 minutes
4. **Audio should work**: Within 30 minutes if configuration is correct

---

## Next Steps Based on Findings

### If Still No ACS Logs After 15 Minutes:
- Verify diagnostic settings are actually saved
- Check Log Analytics workspace permissions
- Try different log categories

### If Function Logs Show TTS Requests but No Audio:
- Focus on web client audio debugging
- Check browser permissions
- Test different audio devices

### If TTS Requests Fail:
- Focus on Cognitive Services authentication
- Verify regional configuration
- Check managed identity setup
