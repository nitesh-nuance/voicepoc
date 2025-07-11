# Azure Communication Services Voice POC

A complete implementation of Azure Communication Services (ACS) call automation with Python Azure Functions and a web-based test client.

## 🏗️ Project Structure

- `function_app.py` - Main Azure Function with ACS endpoints
- `test-client-local-server.html` - Web test client with voice calling capabilities
- `deploy-to-existing-function.ps1` - Deployment script for Azure
- `serve-test-client.py` - Python HTTP server for local testing
- `start-test-client.bat` / `start-test-client.ps1` - Quick start scripts
- `server.js` / `package.json` - Node.js server alternative

## 🚀 Quick Start

### 1. Test the Web Client Locally

The web client needs to be served over HTTP/HTTPS (not file://) to avoid CORS issues with the Azure Communication Services SDK.

**Option A: Python Server (Recommended)**
```bash
# Run the Python server
python serve-test-client.py

# Or use the quick start script
start-test-client.bat
# OR
start-test-client.ps1
```

**Option B: Node.js Server**
```bash
# If you have Node.js installed
node server.js
# OR
npm start
```

**Option C: Any HTTP Server**
```bash
# Python 3
python -m http.server 8000

# Python 2
python -m SimpleHTTPServer 8000

# Node.js (if you have http-server installed)
npx http-server -p 8000 --cors

# PHP
php -S localhost:8000
```

### 2. Open the Test Client

1. Start any of the servers above
2. Open: `http://localhost:8000/test-client-local-server.html`
3. You should see the Azure Communication Services test interface

### 3. Test the Interface

1. **Check SDK Loading**: The page should show "Ready to initialize" in green
2. **Initialize Client**: Click the "Initialize Client" button
3. **Get Token**: Enter your Azure Function URL and click "Get Token"
4. **Make Test Call**: Use the provided phone number to test calling

## 🔧 Configuration

### Environment Variables (for Azure Function)

Set these in your Azure Function App settings or `local.settings.json`:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "ACS_CONNECTION_STRING": "your_acs_connection_string",
    "ACS_PHONE_NUMBER": "your_acs_phone_number"
  }
}
```

### Required Azure Resources

1. **Azure Communication Services Resource**
   - Get the connection string
   - Purchase a phone number for outbound calls

2. **Azure Function App** (if deploying)
   - Python 3.9+ runtime
   - Linux hosting recommended

## 📱 Testing Voice Calls

### Outbound Calls
1. Get a token from your Azure Function
2. Use the "Make Test Call" feature in the web client
3. Call will be made to the configured phone number

### Inbound Calls (Webhook)
1. Configure your ACS phone number webhook to point to your Function: `/CallWebhook`
2. The function will handle incoming call events
3. Calls can be answered programmatically

## 🐛 Troubleshooting

### "SDK loading failed"
- **Cause**: CORS issues when opening HTML file directly
- **Solution**: Use one of the HTTP servers listed above

### "Cannot read properties of undefined"
- **Cause**: Azure Communication Services SDK not loaded
- **Solution**: Check browser console, ensure HTTP server is used

### "Failed to get token"
- **Cause**: Azure Function not running or environment variables missing
- **Solution**: Check Function App logs and environment configuration

### "Call failed"
- **Cause**: Various network, token, or ACS configuration issues
- **Solution**: Check browser console and Azure Function logs

## 📋 Features

### Azure Function Endpoints

- `GET /` - Health check
- `POST /GetToken` - Get ACS user access token
- `POST /MakeTestCall` - Initiate outbound call
- `POST /CallWebhook` - Handle incoming call events

### Web Client Features

- ✅ Azure Communication Services SDK integration
- ✅ User token management
- ✅ Audio device management
- ✅ Call state monitoring
- ✅ Real-time logging
- ✅ CORS-compliant serving
- ✅ Fallback SDK loading
- ✅ Responsive design

## 🚢 Deployment

Deploy to Azure using the provided script:

```powershell
# Make sure you have:
# 1. An existing Azure Function App
# 2. ACS connection string and phone number
# 3. Azure CLI installed and logged in

.\deploy-to-existing-function.ps1
```

## 📚 Documentation

- [Azure Communication Services Documentation](https://docs.microsoft.com/en-us/azure/communication-services/)
- [ACS JavaScript SDK](https://docs.microsoft.com/en-us/azure/communication-services/quickstarts/voice-video-calling/calling-client-samples)
- [Azure Functions Python Guide](https://docs.microsoft.com/en-us/azure/azure-functions/functions-reference-python)

## 🔐 Security Notes

- Never commit connection strings or secrets to version control
- Use Azure Key Vault for production secrets
- Configure proper CORS settings for production
- Implement authentication for production use

## 🆘 Support

If you encounter issues:

1. Check the browser console for JavaScript errors
2. Check Azure Function logs in the Azure portal
3. Verify all environment variables are set correctly
4. Ensure the ACS resource and phone number are properly configured
