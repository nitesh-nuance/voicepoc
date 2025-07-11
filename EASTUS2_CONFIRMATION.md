# East US 2 Cognitive Services Configuration

## ✅ Confirmed: East US 2 is Fully Supported

Based on official Azure documentation, East US 2 is fully supported for Azure Cognitive Services Speech functionality.

### Supported Endpoints for East US 2:
- **General Cognitive Services API**: `https://eastus2.api.cognitive.microsoft.com/`
- **Text-to-Speech Specific**: `https://eastus2.tts.speech.microsoft.com/cognitiveservices/v1`
- **Region Identifier**: `eastus2`

### Current Configuration ✅
Your configuration has been updated to use East US 2:

**function_app.py:**
```python
COGNITIVE_SERVICES_ENDPOINT = os.environ.get("COGNITIVE_SERVICES_ENDPOINT", "https://eastus2.api.cognitive.microsoft.com/")
```

**local.settings.json:**
```json
"COGNITIVE_SERVICES_ENDPOINT": "https://eastus2.api.cognitive.microsoft.com/"
```

### Benefits of Using East US 2:
1. **Resource Locality**: All your resources are in the same region
2. **Lower Latency**: Reduced network latency between services
3. **Cost Optimization**: No cross-region data transfer costs
4. **Compliance**: Resources remain within the same geographical boundary

### Supported Features in East US 2:
✅ Speech-to-Text  
✅ Text-to-Speech  
✅ Neural voices  
✅ Custom voices  
✅ Speech Translation  
✅ Azure Communication Services integration  

### Testing
Your setup is now optimized for East US 2. Test with:
1. `GET /api/TestMessage` - Verify configuration shows East US 2 endpoint
2. `GET /api/MakeTestCallWithAutoTTS?delay=3` - Test TTS functionality
3. `GET /api/PlayMessage?callId=...` - Test manual TTS

All TTS operations should now work seamlessly with your East US 2 resource configuration!
