# Azure Debugging Queries for Voice Issue

## Prerequisites
1. Ensure diagnostic settings are enabled for both ACS and Azure AI Services
2. Logs are being sent to a Log Analytics workspace
3. Run these queries in Azure Portal > Log Analytics workspace > Logs

---

## 1. Azure Communication Services (ACS) Logs

### Basic ACS Logs (All Events)
```kql
ACSCallAutomationIncomingOperations
| union ACSCallDiagnostics
| union ACSCallSummary
| union ACSCallClientOperations
| union ACSCallRecordingIncomingOperations
| union AzureDiagnostics
| where ResourceProvider == "MICROSOFT.COMMUNICATION" or ResourceType == "COMMUNICATIONSERVICES"
| order by TimeGenerated desc
| take 100
```

### ACS Call Events (Call Creation, Connection, Disconnection)
```kql
ACSCallAutomationIncomingOperations
| where TimeGenerated >= ago(1h)
| project TimeGenerated, OperationName, OperationVersion, ResultSignature, DurationMs, CallerIpAddress, CorrelationId, Properties
| order by TimeGenerated desc
```

### ACS Call Diagnostics (Media and Audio Issues)
```kql
ACSCallDiagnostics
| where TimeGenerated >= ago(1h)
| project TimeGenerated, ParticipantId, EndpointId, MediaType, StreamDirection, Codec, PacketLossRate, Jitter, RoundTripTime
| order by TimeGenerated desc
```

### ACS Media Operations (TTS Related)
```kql
ACSCallAutomationIncomingOperations
| where OperationName contains "PlayMedia" or OperationName contains "Media"
| where TimeGenerated >= ago(1h)
| project TimeGenerated, OperationName, ResultSignature, DurationMs, CorrelationId, Properties
| order by TimeGenerated desc
```

### ACS Errors and Failures
```kql
ACSCallAutomationIncomingOperations
| union ACSCallDiagnostics
| union ACSCallSummary
| where ResultSignature != "Success" or Level == "Error" or Level == "Warning"
| where TimeGenerated >= ago(1h)
| project TimeGenerated, OperationName, ResultSignature, Level, ResultDescription, CorrelationId
| order by TimeGenerated desc
```

---

## 2. Azure AI Services (Cognitive Services) Logs

### Basic Azure AI Services Logs
```kql
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.COGNITIVESERVICES"
| where TimeGenerated >= ago(1h)
| project TimeGenerated, ResourceType, OperationName, ResultType, ResultSignature, DurationMs, CorrelationId, Resource, Category
| order by TimeGenerated desc
```

### Alternative AI Services Logs (if above doesn't work)
```kql
// First, check what columns are available
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.COGNITIVESERVICES"
| where TimeGenerated >= ago(1h)
| take 1
| project *
```

### Speech Services (TTS) Specific Logs
```kql
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.COGNITIVESERVICES"
| where OperationName contains "SpeechServices" or OperationName contains "tts" or OperationName contains "speech" or Category contains "Speech"
| where TimeGenerated >= ago(1h)
| project TimeGenerated, OperationName, ResultType, ResultSignature, DurationMs, CorrelationId, Category, Resource
| order by TimeGenerated desc
```

### Azure AI Services Errors
```kql
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.COGNITIVESERVICES"
| where ResultType != "Success" or Level == "Error" or Level == "Warning"
| where TimeGenerated >= ago(1h)
| project TimeGenerated, OperationName, ResultType, ResultSignature, Level, CorrelationId, Resource, Category
| order by TimeGenerated desc
```

### TTS Request Details (Updated)
```kql
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.COGNITIVESERVICES"
| where Category contains "Speech" or OperationName contains "tts"
| where TimeGenerated >= ago(1h)
| project TimeGenerated, OperationName, ResultType, DurationMs, CorrelationId, Category, Resource
| order by TimeGenerated desc
```

---

## 3. Azure Function App Logs

### Application Insights Traces
```kql
traces
| where timestamp >= ago(1h)
| where message contains "TTS" or message contains "Call" or message contains "MakeTestCall"
| project timestamp, severityLevel, message, operation_Name, operation_Id
| order by timestamp desc
```

### Application Function Errors
```kql
exceptions
| union traces
| where timestamp >= ago(1h)
| where severityLevel >= 2
| project timestamp, severityLevel, message, operation_Name, type, outerMessage
| order by timestamp desc
```

### Function App Requests
```kql
requests
| where timestamp >= ago(1h)
| where name contains "MakeTestCall" or name contains "PlayMessage"
| project timestamp, name, resultCode, duration, operation_Id, url
| order by timestamp desc
```

---

## 4. Combined Correlation Analysis

### Trace Operations Across Services
```kql
let correlationIds = 
    traces
    | where timestamp >= ago(1h)
    | where message contains "Call created with ID"
    | extend CallId = extract(@"Call ID: ([a-zA-Z0-9\-]+)", 1, message)
    | distinct operation_Id, CallId;
//
union
(traces | where operation_Id in ((correlationIds | project operation_Id))),
(ACSCallAutomationIncomingOperations | where CorrelationId in ((correlationIds | project operation_Id))),
(AzureDiagnostics | where ResourceProvider == "MICROSOFT.COGNITIVESERVICES" and CorrelationId in ((correlationIds | project operation_Id)))
| order by TimeGenerated desc, timestamp desc
```

### End-to-End Call Flow
```kql
let timeRange = ago(1h);
union
(traces | where timestamp >= timeRange | extend EventTime = timestamp, Source = "FunctionApp", EventType = "Trace"),
(requests | where timestamp >= timeRange | extend EventTime = timestamp, Source = "FunctionApp", EventType = "Request"),
(ACSCallAutomationIncomingOperations | where TimeGenerated >= timeRange | extend EventTime = TimeGenerated, Source = "ACS", EventType = "CallAutomation"),
(AzureDiagnostics | where ResourceProvider == "MICROSOFT.COGNITIVESERVICES" and TimeGenerated >= timeRange | extend EventTime = TimeGenerated, Source = "CognitiveServices", EventType = "AI")
| project EventTime, Source, EventType, OperationName, message, ResultSignature, DurationMs
| order by EventTime desc
```

---

## 5. Specific Debugging Queries for Your Issue

### Check if TTS Requests are Reaching Cognitive Services
```kql
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.COGNITIVESERVICES"
| where TimeGenerated >= ago(1h)
| where Category contains "Speech" or OperationName contains "tts" or OperationName contains "Speech"
| summarize Count = count() by bin(TimeGenerated, 5m), ResultType
| render timechart
```

### Alternative: Check All AI Services Activity
```kql
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.COGNITIVESERVICES"
| where TimeGenerated >= ago(1h)
| summarize Count = count() by bin(TimeGenerated, 5m), OperationName, ResultType
| render timechart
```

### Check ACS Media Operations Success Rate
```kql
ACSCallAutomationIncomingOperations
| where OperationName contains "PlayMedia"
| where TimeGenerated >= ago(1h)
| summarize Total = count(), Successful = countif(ResultSignature == "Success") by bin(TimeGenerated, 5m)
| extend SuccessRate = Successful * 100.0 / Total
| render timechart
```

### Find Failed Operations
```kql
union
(traces | where severityLevel >= 3 | extend Source = "FunctionApp"),
(ACSCallAutomationIncomingOperations | where ResultSignature != "Success" | extend Source = "ACS"),
(AzureDiagnostics | where ResourceProvider == "MICROSOFT.COGNITIVESERVICES" and ResultType != "Success" | extend Source = "CognitiveServices")
| where TimeGenerated >= ago(1h) or timestamp >= ago(1h)
| project TimeGenerated, timestamp, Source, OperationName, message, ResultSignature, ResultType
| order by TimeGenerated desc, timestamp desc
```

---

## 6. Schema Discovery Queries (Run First to Find Correct Column Names)

### Discover Available Tables for Azure AI Services
```kql
search "*"
| where TimeGenerated >= ago(1h)
| where $table contains "Cognitive" or $table contains "Speech" or $table contains "AI"
| distinct $table
```

### Check Azure AI Services Schema
```kql
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.COGNITIVESERVICES"
| where TimeGenerated >= ago(1h)
| take 1
| getschema 
```

### Alternative: Check All Available Columns
```kql
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.COGNITIVESERVICES"
| where TimeGenerated >= ago(1h)
| take 1
| project *
```

### Look for Specific AI Services Tables
```kql
union withsource=TableName *
| where TimeGenerated >= ago(1h)
| where TableName contains "Speech" or TableName contains "Cognitive" or TableName contains "AI"
| summarize count() by TableName
| order by count_ desc
```

---

## Usage Instructions

1. **Go to Azure Portal > Log Analytics workspace**
2. **Click on "Logs" in the left menu**
3. **Copy and paste the relevant query**
4. **Adjust the time range** (change `ago(1h)` to `ago(2h)`, `ago(1d)`, etc.)
5. **Run the query** and analyze results
6. **Look for**:
   - Failed operations (ResultSignature != "Success")
   - High duration times
   - Missing correlation between services
   - TTS requests that don't have corresponding responses

## Common Issues to Look For

1. **No TTS requests in Cognitive Services logs** → Configuration issue
2. **TTS requests failing** → Authentication or quota issues
3. **ACS media operations failing** → Network or codec issues
4. **Missing correlation IDs** → Services not properly linked
5. **High latency** → Performance issues affecting real-time audio
