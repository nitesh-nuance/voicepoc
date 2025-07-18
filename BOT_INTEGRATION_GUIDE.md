# Azure Bot Service Integration Guide

This guide explains how to integrate Azure Bot Service with your Azure Communication Services voice calling system, enabling bot-initiated calls to the TARGET_USER_ID.

## Overview

The integration allows you to:
- Chat with an Azure Bot Service bot
- Ask the bot to make voice calls to your target user
- Use OpenAI for intelligent bot conversations
- Customize call messages and voices through bot commands

## Architecture

```
User Message → Azure Bot Service → Azure Function (bot/messages) → ACS Call → Target User
                                                ↓
OpenAI Model (for intelligent responses) ← Bot Logic → Call Automation
```

## Setup Instructions

### 1. Azure Bot Service Configuration

1. **Create an Azure Bot Service**:
   ```bash
   # Using Azure CLI
   az bot create \
     --resource-group YOUR_RESOURCE_GROUP \
     --name YOUR_BOT_NAME \
     --kind webapp \
     --app-id YOUR_APP_ID \
     --password YOUR_APP_PASSWORD \
     --endpoint https://YOUR_FUNCTION_APP.azurewebsites.net/api/bot/messages
   ```

2. **Get Bot Credentials**:
   - App ID: From Bot Service → Settings → Configuration
   - App Password: Create in Azure AD App Registration → Certificates & secrets

### 2. OpenAI Configuration

1. **Create Azure OpenAI Service**:
   ```bash
   az cognitiveservices account create \
     --name YOUR_OPENAI_NAME \
     --resource-group YOUR_RESOURCE_GROUP \
     --kind OpenAI \
     --sku S0 \
     --location eastus
   ```

2. **Deploy a Model**:
   - Deploy GPT-4o or GPT-3.5-turbo in Azure OpenAI Studio
   - Note the endpoint and deployment name

### 3. Update Configuration

Update your `local.settings.json` and Azure Function App Settings:

```json
{
  "Values": {
    // Existing settings...
    "BOT_APP_ID": "12345678-1234-1234-1234-123456789012",
    "BOT_APP_PASSWORD": "your-bot-app-password",
    "BOT_SERVICE_ENDPOINT": "https://your-bot-service.azurewebsites.net",
    "OPENAI_API_KEY": "your-openai-api-key",
    "OPENAI_ENDPOINT": "https://your-openai-service.openai.azure.com/",
    "OPENAI_MODEL": "gpt-4o"
  }
}
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

## Available Endpoints

### 1. `/api/bot/messages` (POST)
Main bot endpoint that receives messages from Azure Bot Service.

**Usage**: Configure this as your bot's messaging endpoint in Azure Bot Service.

### 2. `/api/BotCallWebhook` (POST)
Webhook for handling call events from bot-initiated calls.

**Usage**: Automatically handles call connection and TTS playback.

### 3. `/api/TestBotCall` (GET/POST)
Test endpoint to simulate bot interactions without Azure Bot Service.

**Example**:
```bash
# Test basic call request
curl "https://your-function-app.azurewebsites.net/api/TestBotCall?message=call the patient"

# Test with custom message
curl -X POST "https://your-function-app.azurewebsites.net/api/TestBotCall" \
  -H "Content-Type: application/json" \
  -d '{"message": "call the patient and say hello from the bot", "customMessage": "Hello! This is a custom message from your healthcare assistant."}'
```

## Bot Commands

The bot understands various commands to initiate calls:

### Basic Call Commands
- "Call the patient"
- "Make a voice call"
- "Phone the user"
- "Initiate a call"
- "Start a voice call"

### Custom Message Commands
- "Call and say [your message]"
- "Make a call and tell them [your message]"
- "Phone the user and say [your message]"

### Voice Selection Commands
- "Call using Jenny voice"
- "Make a call with Aria voice"
- "Use Guy voice for the call"

### Example Conversations

**Basic Call**:
```
User: "Hi bot, please call the patient"
Bot: "I've initiated a call to the target user as requested. Call ID: abc123. The call should connect shortly and you'll hear: 'Hello! This is your Azure Communication Services assistant...'"
```

**Custom Message**:
```
User: "Call the patient and say 'Your appointment is confirmed for tomorrow at 2 PM'"
Bot: "I've initiated a call to the target user as requested. Call ID: xyz789. The call should connect shortly and you'll hear: 'Your appointment is confirmed for tomorrow at 2 PM'"
```

**Help Request**:
```
User: "What can you do?"
Bot: "I can help you with:
- Making voice calls to patients
- Managing patient appointments  
- Accessing patient data
- Healthcare assistance

To make a call, just say 'call the patient' or 'make a voice call'."
```

## Error Handling

The bot handles various error scenarios:

1. **ACS Not Configured**: "ACS not configured"
2. **Target User Not Set**: "TARGET_USER_ID not configured"
3. **Bot Credentials Missing**: "Sorry, I'm not properly configured. Please check my bot credentials."
4. **Call Failed**: "I wasn't able to initiate the call. Error: [error details]"

## Testing

### 1. Test Bot Integration
```bash
# Test if bot can process messages
curl -X GET "https://your-function-app.azurewebsites.net/api/TestBotCall?message=hello"
```

### 2. Test Call Initiation
```bash
# Test call initiation through bot
curl -X GET "https://your-function-app.azurewebsites.net/api/TestBotCall?message=call the patient"
```

### 3. Test Custom Messages
```bash
# Test custom TTS message
curl -X POST "https://your-function-app.azurewebsites.net/api/TestBotCall" \
  -H "Content-Type: application/json" \
  -d '{"message": "call and say your appointment is tomorrow"}'
```

## Deployment

### 1. Deploy to Azure Functions
```bash
func azure functionapp publish YOUR_FUNCTION_APP_NAME
```

### 2. Update Bot Service Endpoint
In Azure Portal → Bot Service → Settings → Configuration:
- Messaging endpoint: `https://YOUR_FUNCTION_APP.azurewebsites.net/api/bot/messages`

### 3. Test in Bot Framework Emulator
1. Download Bot Framework Emulator
2. Connect to: `https://YOUR_FUNCTION_APP.azurewebsites.net/api/bot/messages`
3. Use your Bot App ID and Password
4. Test conversations and call commands

## Security Considerations

1. **Secure Credentials**: Store bot credentials and API keys in Azure Key Vault
2. **Authentication**: Implement proper bot authentication validation
3. **Rate Limiting**: Add rate limiting for call initiation to prevent abuse
4. **Audit Logging**: Log all bot-initiated calls for compliance

## Monitoring

Monitor your bot integration using:

1. **Azure Functions Logs**: Monitor function execution and errors
2. **Bot Service Analytics**: Track bot conversations and usage
3. **ACS Call Logs**: Monitor call success rates and quality
4. **Application Insights**: Set up comprehensive monitoring

## Troubleshooting

### Common Issues

1. **Bot Not Responding**:
   - Check BOT_APP_ID and BOT_APP_PASSWORD
   - Verify messaging endpoint configuration
   - Check Azure Functions logs

2. **Calls Not Initiating**:
   - Verify ACS_CONNECTION_STRING
   - Check TARGET_USER_ID format
   - Ensure COGNITIVE_SERVICES_ENDPOINT is set

3. **TTS Not Playing**:
   - Check BotCallWebhook is receiving events
   - Verify COGNITIVE_SERVICES_ENDPOINT
   - Check call connection status

4. **OpenAI Errors**:
   - Verify OPENAI_API_KEY and OPENAI_ENDPOINT
   - Check model deployment name
   - Monitor API quota and limits

### Debug Mode

Enable detailed logging by setting log level to DEBUG in your Function App settings:
```json
{
  "logging": {
    "logLevel": {
      "default": "Debug"
    }
  }
}
```

## Next Steps

1. **Enhance Bot Intelligence**: Add more sophisticated conversation flows
2. **Patient Data Integration**: Connect bot to Cosmos DB for patient-specific calls
3. **Multi-User Support**: Extend to support calling different target users
4. **Call Scheduling**: Add ability to schedule calls for later
5. **Call Analytics**: Implement call outcome tracking and reporting

For additional support, refer to:
- [Azure Bot Service Documentation](https://docs.microsoft.com/en-us/azure/bot-service/)
- [Azure Communication Services Documentation](https://docs.microsoft.com/en-us/azure/communication-services/)
- [Azure OpenAI Documentation](https://docs.microsoft.com/en-us/azure/cognitive-services/openai/)
