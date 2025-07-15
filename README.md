# Azure Healthcare Voice Assistant

An Azure Function implementation using Python for Azure Communication Services (ACS) based voice calling and Azure Cosmos DB based managing data. Features include voice calling capabilities, patient management, appointment scheduling, and text-to-speech integration.

## 🏗️ Project Architecture

### Core Components
- **Azure Functions** - Backend API with Python runtime
- **Azure Communication Services** - Voice calling and text-to-speech
- **Azure Cosmos DB** - NoSQL database for patient and appointment data
- **Azure Cognitive Services** - Neural voice synthesis

### File Structure
- `function_app.py` - Main Azure Function with healthcare and voice endpoints
- `local.settings.json` - Local development configuration
- `requirements.txt` - Python dependencies
- `test_cosmos_integration.py` - Database integration testing
- `deploy-to-existing-function.ps1` - Azure deployment script

## 🚀 Project Setup

### Prerequisites

1. **Azure Subscription** with access to:
   - Azure Functions
   - Azure Communication Services
   - Azure Cosmos DB
   - Azure Cognitive Services

2. **Development Environment**:
   - Python 3.9+ 
   - Azure Functions Core Tools
   - VS Code (recommended)
   - Git

### Step 1: Clone and Setup Local Environment

```bash
# Clone the repository
git clone <your-repo-url>
cd voicepoc

# Create Python virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Azure Functions Core Tools (if not already installed)
npm install -g azure-functions-core-tools@4 --unsafe-perm true
```

### Step 2: Create Azure Resources

#### 2.1 Azure Communication Services
1. Create an Azure Communication Services resource in Azure Portal
2. Navigate to **Keys** and copy the **Connection String**
3. Go to **Phone Numbers** → **Get** → Purchase a phone number (optional, for PSTN calling)

#### 2.2 Azure Cosmos DB
1. Create a **Cosmos DB** resource with **NoSQL API**
2. Choose a region (recommend East US 2 for consistency)
3. Create database: `HealthcareDB`
4. Create containers:
   - `patients` (partition key: `/patientId`)
   - `appointments` (partition key: `/patientId`)
5. Navigate to **Keys** and copy the **PRIMARY CONNECTION STRING**

#### 2.3 Azure Cognitive Services
1. Create a **Cognitive Services** resource
2. Choose same region as other resources
3. Copy the **Endpoint URL**

#### 2.4 Azure Cosmos DB
1. Create a **NoSQL Azure Cosmos** resource
2. Choose same region as other resources
3. Copy the **Connection String**

### Step 3: Configure Local Settings

Create `local.settings.json` in the project root:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "ACS_CONNECTION_STRING": "YOUR_ACS_CONNECTION_STRING",
    "TARGET_USER_ID": "YOUR_ACS_USER_ID",
    "CALLBACK_URL_BASE": "your-function-app.azurewebsites.net",
    "COGNITIVE_SERVICES_ENDPOINT": "https://your-cognitive-services.cognitiveservices.azure.com/",
    "WELCOME_MESSAGE": "Hello! This is your healthcare assistant. How can I help you today?",
    "TTS_VOICE": "en-US-AriaNeural",
    "COSMOS_CONNECTION_STRING": "YOUR_COSMOS_DB_CONNECTION_STRING"
  }
}
```

### Step 4: Run and Test Locally

```bash
# Start Azure Functions host
func host start

# In another terminal, test the integration
python test_cosmos_integration.py

```

### Step 5: Verify Setup

1. **Functions Endpoint**: Visit `http://localhost:7071/api/MakeTestCallWithWebhookTTS`
2. **Database Integration**: Successful test should show ✅ for all operations
3. **Voice Integration**: Test voice endpoints with web client

## 🎯 Quick Start Guide

### 1. Test the Healthcare API

Once your Azure Functions host is running (`func host start`), test the endpoints:

**Health Check**
```bash
curl http://localhost:7071/api/GetToken
```

**Patient Management**
```bash
# List patients
curl http://localhost:7071/api/patients

# Create a patient
curl -X POST http://localhost:7071/api/patients \
  -H "Content-Type: application/json" \
  -d '{
    "firstName": "John",
    "lastName": "Doe", 
    "email": "john.doe@example.com",
    "phone": "+1234567890",
    "dateOfBirth": "1990-01-01"
  }'

# Get patient by ID
curl http://localhost:7071/api/patients/{patient-id}
```

**Appointment Management**
```bash
# List appointments
curl http://localhost:7071/api/appointments

# Create appointment
curl -X POST http://localhost:7071/api/appointments \
  -H "Content-Type: application/json" \
  -d '{
    "patientId": "patient-id",
    "appointmentDate": "2025-08-15T10:00:00Z",
    "appointmentType": "Consultation",
    "provider": "Dr. Smith"
  }'
```

### 2. Test Voice Integration

**Voice API Testing**
```bash
# Get ACS token
curl http://localhost:7071/api/GetToken

# Make test call (most reliable method)
curl http://localhost:7071/api/MakeTestCallWithWebhookTTS

# Test different voices
curl "http://localhost:7071/api/MakeTestCallWithWebhookTTS?voice=en-US-ElizabethNeural&message=Hello%20from%20your%20healthcare%20assistant"
```

## 📊 API Reference

### Healthcare Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/patients` | List all patients |
| POST | `/api/patients` | Create new patient |
| GET | `/api/patients/{id}` | Get patient by ID |
| PUT | `/api/patients/{id}` | Update patient |
| DELETE | `/api/patients/{id}` | Delete patient |
| GET | `/api/appointments` | List appointments |
| GET | `/api/appointments?patientId={id}` | List patient appointments |
| POST | `/api/appointments` | Create appointment |
| GET | `/api/appointments/{id}?patientId={pid}` | Get appointment |
| PUT | `/api/appointments/{id}?patientId={pid}` | Update appointment |
| DELETE | `/api/appointments/{id}?patientId={pid}` | Delete appointment |

### Voice Communication Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/GetToken` | Get ACS authentication token |
| GET | `/api/MakeTestCallWithWebhookTTS` | Most reliable call method |
| GET | `/api/MakeTestCallWithAutoTTS` | Call with automatic TTS |
| GET | `/api/PlayMessage?callId={id}` | Play TTS on active call |

## 🚀 Deployment

### Azure Functions Deployment

1. **Deploy Azure Function**
```Powershell
.\deploy-to-existing-function.ps1
```

## 🔧 Troubleshooting

### Common Issues

**1. Functions Host Won't Start**
```bash
# Check if port 7071 is in use
netstat -ano | findstr :7071

# Kill any existing func processes
Get-Process -Name "func" | Stop-Process -Force

# Restart with verbose logging
func start --verbose
```

**2. Cosmos DB Connection Issues**
- Verify connection string in `local.settings.json`
- Check if database and containers exist in Azure Portal
- Ensure proper network connectivity

**3. Voice Services Not Working**
- Verify ACS connection string is correct
- Check Cognitive Services endpoint configuration
- Test voice synthesis with `/api/TestCognitiveServices`

**4. Phone/Voice Call Issues**
- Ensure phone number / target ID is in correct format (+1234567890)
- Verify ACS calling permissions
- Check webhook URLs for production deployment

### Debug Tools

Run integration tests:
```bash
python test_cosmos_integration.py
```

## 📝 API Examples

### Patient Management

**Create Patient**
```json
POST /api/patients
{
    "id": "patient-123",
    "name": "John Doe",
    "dateOfBirth": "1990-01-15",
    "email": "john.doe@email.com",
    "phone": "+1234567890",
    "medicalHistory": ["hypertension", "diabetes"],
    "emergencyContact": {
        "name": "Jane Doe",
        "phone": "+1987654321",
        "relationship": "spouse"
    }
}
```

**Create Appointment**
```json
POST /api/appointments
{
    "id": "apt-456",
    "patientId": "patient-123",
    "doctorName": "Dr. Smith",
    "appointmentType": "checkup",
    "dateTime": "2024-01-20T10:00:00",
    "status": "scheduled",
    "notes": "Regular checkup"
}
```
