import azure.functions as func
import logging
import os
import json
import base64
import time
import threading
from typing import Optional, Any, Dict, List, Union

# Load local.settings.json for development (when not running in Azure Functions runtime)
def load_local_settings():
    """Load environment variables from local.settings.json during development"""
    try:
        if not os.environ.get('AZURE_FUNCTIONS_ENVIRONMENT'):
            with open('local.settings.json', 'r') as f:
                settings = json.load(f)
                for key, value in settings.get('Values', {}).items():
                    if key not in os.environ:
                        os.environ[key] = value
                logging.info("Loaded local.settings.json for development")
    except FileNotFoundError:
        logging.warning("local.settings.json not found")
    except Exception as e:
        logging.error(f"Error loading local.settings.json: {e}")

# Load settings at module level
load_local_settings()

from azure.communication.callautomation import CallAutomationClient, TextSource
from azure.communication.identity import CommunicationUserIdentifier
from azure.communication.callautomation import PhoneNumberIdentifier

# Azure Bot Service imports
from botbuilder.core import TurnContext, ActivityHandler, MessageFactory
from botbuilder.schema import Activity, ChannelAccount, ActivityTypes
from botframework.connector import ConnectorClient
from botframework.connector.auth import MicrosoftAppCredentials

# OpenAI imports for bot intelligence
import openai
from openai import AzureOpenAI

# Azure Cosmos DB imports
from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosResourceExistsError, CosmosResourceNotFoundError

# Your connection string from ACS, stored securely
ACS_CONNECTION_STRING = os.environ.get("ACS_CONNECTION_STRING", "")

# Cognitive Services endpoint for TTS functionality (required for media operations)
# For Global ACS resources, use a global or US endpoint
COGNITIVE_SERVICES_ENDPOINT = os.environ.get("COGNITIVE_SERVICES_ENDPOINT", "").rstrip('/') if os.environ.get("COGNITIVE_SERVICES_ENDPOINT") else ""
 
# The User Identity you generated (the one starting with 8:acs:...)
TARGET_USER_ID = os.environ.get("TARGET_USER_ID", "")

# The target phone number for PSTN calls (e.g., +917447474405)
TARGET_PHONE_NUMBER = os.environ.get("TARGET_PHONE_NUMBER", "+917447474405")

# The source caller ID for PSTN calls (must be a phone number you own in ACS)
SOURCE_CALLER_ID = os.environ.get("SOURCE_CALLER_ID", "") or os.environ.get("ACS_PHONE_NUMBER", "")
 
# The callback URL for your function, so ACS can send back events
CALLBACK_URL_BASE = os.environ.get("CALLBACK_URL_BASE", "")

# Azure Cosmos DB configuration
COSMOS_CONNECTION_STRING = os.environ.get("COSMOS_CONNECTION_STRING", "")
COSMOS_DATABASE_NAME = "adherenceagentdb"
COSMOS_PATIENTS_CONTAINER = "patients"
COSMOS_APPOINTMENTS_CONTAINER = "appointments"

# The message to play when call connects - customize this as needed
WELCOME_MESSAGE = os.environ.get("WELCOME_MESSAGE", 
    "Hello! This is your Azure Communication Services assistant. The call connection is working perfectly. "
    "You can now hear automated messages through Azure's text-to-speech service. "
    "Thank you for testing the voice integration.")

# Voice to use for text-to-speech - can be customized
TTS_VOICE = os.environ.get("TTS_VOICE", "en-US-JennyNeural")

# Azure Bot Service configuration
BOT_APP_ID = os.environ.get("BOT_APP_ID", "39188ba4-899a-4c87-a7a9-a35b52eb1891")
BOT_APP_PASSWORD = os.environ.get("BOT_APP_PASSWORD", "jz48Q~VxYZN_uLM6TgypoZbMUxSsHxCX1~oDta7y")
BOT_SERVICE_ENDPOINT = os.environ.get("BOT_SERVICE_ENDPOINT", "")

# OpenAI configuration for bot intelligence
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "2Xk8IVrD0Nh745tCPUWOhprKdAcMgyCKvUwXpHggf2WnsIHQoFfgJQQJ99BGACHYHv6XJ3w3AAABACOG3Zds")
OPENAI_ENDPOINT = os.environ.get("OPENAI_ENDPOINT", "https://healthcareagent-openai-ng01.openai.azure.com/")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# Temporary variables for webhook-based custom TTS (in production, use proper storage)
# Note: These are global variables that will be used across different functions
TEMP_CUSTOM_MESSAGE = None
TEMP_CUSTOM_VOICE = None

# Cosmos DB Manager Class
class CosmosDBManager:
    """
    Azure Cosmos DB manager for healthcare application
    Handles patient and appointment data with proper error handling and retry logic
    """
    
    def __init__(self):
        """Initialize Cosmos DB client with connection string"""
        if not COSMOS_CONNECTION_STRING:
            logging.warning("COSMOS_CONNECTION_STRING not configured")
            self.client = None
            self.database = None
            self.patients_container = None
            self.appointments_container = None
            return
            
        try:
            self.client = CosmosClient.from_connection_string(COSMOS_CONNECTION_STRING)
            self.database = self.client.get_database_client(COSMOS_DATABASE_NAME)
            self.patients_container = self.database.get_container_client(COSMOS_PATIENTS_CONTAINER)
            self.appointments_container = self.database.get_container_client(COSMOS_APPOINTMENTS_CONTAINER)
            logging.info("CosmosDB client initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize CosmosDB client: {str(e)}")
            self.client = None
            self.database = None
            self.patients_container = None
            self.appointments_container = None
    
    def is_connected(self) -> bool:
        """Check if Cosmos DB is properly connected"""
        return self.client is not None
    
    # Patient Management Methods
    async def create_patient(self, patient_data: dict) -> dict:
        """Create a new patient record"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            # Ensure required fields
            if 'id' not in patient_data:
                patient_data['id'] = patient_data.get('patientId', str(int(time.time())))
            if 'patientId' not in patient_data:
                patient_data['patientId'] = patient_data['id']
                
            # Add metadata
            patient_data['createdAt'] = int(time.time())
            patient_data['updatedAt'] = int(time.time())
            
            response = self.patients_container.create_item(body=patient_data)
            logging.info(f"Patient created successfully: {patient_data['id']}")
            return response
        except CosmosResourceExistsError:
            raise Exception(f"Patient with ID {patient_data['id']} already exists")
        except Exception as e:
            logging.error(f"Error creating patient: {str(e)}")
            raise Exception(f"Failed to create patient: {str(e)}")
    
    async def get_patient(self, patient_id: str) -> dict:
        """Get a patient by ID"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            response = self.patients_container.read_item(item=patient_id, partition_key=patient_id)
            logging.info(f"Patient retrieved successfully: {patient_id}")
            return response
        except CosmosResourceNotFoundError:
            raise Exception(f"Patient with ID {patient_id} not found")
        except Exception as e:
            logging.error(f"Error retrieving patient: {str(e)}")
            raise Exception(f"Failed to retrieve patient: {str(e)}")
    
    async def update_patient(self, patient_id: str, updates: dict) -> dict:
        """Update an existing patient record"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            # First get the existing patient
            existing_patient = await self.get_patient(patient_id)
            
            # Update fields
            existing_patient.update(updates)
            existing_patient['updatedAt'] = int(time.time())
            
            response = self.patients_container.replace_item(item=patient_id, body=existing_patient)
            logging.info(f"Patient updated successfully: {patient_id}")
            return response
        except Exception as e:
            logging.error(f"Error updating patient: {str(e)}")
            raise Exception(f"Failed to update patient: {str(e)}")
    
    async def delete_patient(self, patient_id: str) -> bool:
        """Delete a patient record"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            self.patients_container.delete_item(item=patient_id, partition_key=patient_id)
            logging.info(f"Patient deleted successfully: {patient_id}")
            return True
        except CosmosResourceNotFoundError:
            raise Exception(f"Patient with ID {patient_id} not found")
        except Exception as e:
            logging.error(f"Error deleting patient: {str(e)}")
            raise Exception(f"Failed to delete patient: {str(e)}")
    
    async def list_patients(self, limit: int = 100) -> list:
        """List all patients with optional limit"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            query = "SELECT * FROM c ORDER BY c.createdAt DESC"
            items = list(self.patients_container.query_items(
                query=query,
                max_item_count=limit,
                enable_cross_partition_query=True
            ))
            logging.info(f"Retrieved {len(items)} patients")
            return items
        except Exception as e:
            logging.error(f"Error listing patients: {str(e)}")
            raise Exception(f"Failed to list patients: {str(e)}")
    
    # Appointment Management Methods
    async def create_appointment(self, appointment_data: dict) -> dict:
        """Create a new appointment record"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            # Ensure required fields
            if 'id' not in appointment_data:
                appointment_data['id'] = str(int(time.time() * 1000))  # Unique ID
            if 'patientId' not in appointment_data:
                raise Exception("patientId is required for appointments")
                
            # Add metadata
            appointment_data['createdAt'] = int(time.time())
            appointment_data['updatedAt'] = int(time.time())
            
            response = self.appointments_container.create_item(body=appointment_data)
            logging.info(f"Appointment created successfully: {appointment_data['id']}")
            return response
        except CosmosResourceExistsError:
            raise Exception(f"Appointment with ID {appointment_data['id']} already exists")
        except Exception as e:
            logging.error(f"Error creating appointment: {str(e)}")
            raise Exception(f"Failed to create appointment: {str(e)}")
    
    async def get_appointment(self, appointment_id: str, patient_id: str) -> dict:
        """Get an appointment by ID"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            response = self.appointments_container.read_item(item=appointment_id, partition_key=patient_id)
            logging.info(f"Appointment retrieved successfully: {appointment_id}")
            return response
        except CosmosResourceNotFoundError:
            raise Exception(f"Appointment with ID {appointment_id} not found")
        except Exception as e:
            logging.error(f"Error retrieving appointment: {str(e)}")
            raise Exception(f"Failed to retrieve appointment: {str(e)}")
    
    async def list_appointments_for_patient(self, patient_id: str) -> list:
        """List all appointments for a specific patient"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            query = "SELECT * FROM c WHERE c.patientId = @patientId ORDER BY c.appointmentDate ASC"
            parameters = [{"name": "@patientId", "value": patient_id}]
            
            items = list(self.appointments_container.query_items(
                query=query,
                parameters=parameters,
                partition_key=patient_id
            ))
            logging.info(f"Retrieved {len(items)} appointments for patient {patient_id}")
            return items
        except Exception as e:
            logging.error(f"Error listing appointments: {str(e)}")
            raise Exception(f"Failed to list appointments: {str(e)}")
    
    async def update_appointment(self, appointment_id: str, patient_id: str, updates: dict) -> dict:
        """Update an existing appointment record"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            # First get the existing appointment
            existing_appointment = await self.get_appointment(appointment_id, patient_id)
            
            # Update fields
            existing_appointment.update(updates)
            existing_appointment['updatedAt'] = int(time.time())
            
            response = self.appointments_container.replace_item(item=appointment_id, body=existing_appointment)
            logging.info(f"Appointment updated successfully: {appointment_id}")
            return response
        except Exception as e:
            logging.error(f"Error updating appointment: {str(e)}")
            raise Exception(f"Failed to update appointment: {str(e)}")
    
    async def delete_appointment(self, appointment_id: str, patient_id: str) -> bool:
        """Delete an appointment record"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            self.appointments_container.delete_item(item=appointment_id, partition_key=patient_id)
            logging.info(f"Appointment deleted successfully: {appointment_id}")
            return True
        except CosmosResourceNotFoundError:
            raise Exception(f"Appointment with ID {appointment_id} not found")
        except Exception as e:
            logging.error(f"Error deleting appointment: {str(e)}")
            raise Exception(f"Failed to delete appointment: {str(e)}")

# ================================
# BOT SERVICE INTEGRATION CLASSES
# ================================

class CallInitiatorBot:
    """
    Azure Bot Service integration for initiating voice calls
    Handles bot conversations and triggers ACS calls based on user requests
    """
    
    def __init__(self):
        """Initialize bot with OpenAI and ACS clients"""
        self.app_id = BOT_APP_ID
        self.app_password = BOT_APP_PASSWORD
        
        # Initialize OpenAI client for bot intelligence
        if OPENAI_API_KEY and OPENAI_ENDPOINT:
            self.openai_client = AzureOpenAI(
                api_key=OPENAI_API_KEY,
                api_version="2024-02-01",
                azure_endpoint=OPENAI_ENDPOINT
            )
        else:
            self.openai_client = None
            logging.warning("OpenAI not configured - bot will use basic responses")
        
        # Initialize ACS client for call automation
        if ACS_CONNECTION_STRING:
            self.acs_client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
        else:
            self.acs_client = None
            logging.error("ACS not configured - cannot initiate calls")
    
    async def process_message(self, activity: dict) -> dict:
        """
        Process incoming bot message and determine if a call should be initiated
        Returns response message and call information if applicable
        """
        try:
            user_message = activity.get('text', '').strip()
            user_id = activity.get('from', {}).get('id', 'unknown')
            
            logging.info(f"Bot processing message from {user_id}: {user_message}")
            
            # Check if user is requesting a call
            call_request = self._analyze_call_request(user_message)
            
            if call_request['should_call']:
                # Initiate the call
                call_result = await self._initiate_call(call_request)
                
                if call_result['success']:
                    response_text = f"I've initiated a call to {TARGET_USER_ID[:20]}... as requested. " \
                                  f"Call ID: {call_result['call_id']}. " \
                                  f"The call should connect shortly and you'll hear: '{call_result['message'][:50]}...'"
                else:
                    response_text = f"I wasn't able to initiate the call. Error: {call_result['error']}"
                    
                return {
                    'response_text': response_text,
                    'call_initiated': call_result['success'],
                    'call_id': call_result.get('call_id'),
                    'call_error': call_result.get('error')
                }
            else:
                # Regular bot conversation
                response_text = await self._generate_response(user_message)
                return {
                    'response_text': response_text,
                    'call_initiated': False
                }
                
        except Exception as e:
            logging.error(f"Error processing bot message: {str(e)}")
            return {
                'response_text': "I'm sorry, I encountered an error processing your request.",
                'call_initiated': False,
                'error': str(e)
            }
    
    def _analyze_call_request(self, message: str) -> dict:
        """
        Analyze user message to determine if they want to initiate a call
        Returns dict with should_call flag and extracted parameters including phone numbers
        """
        import re
        
        message_lower = message.lower()
        
        # Keywords that indicate call request
        call_keywords = [
            'call', 'phone', 'dial', 'ring', 'contact',
            'make a call', 'place a call', 'call the user',
            'initiate call', 'start call', 'voice call'
        ]
        
        should_call = any(keyword in message_lower for keyword in call_keywords)
        
        # Extract phone number patterns
        phone_number = None
        # Look for phone numbers in various formats
        phone_patterns = [
            r'\+[1-9]\d{1,14}',  # International format: +1234567890
            r'\+\d{1,3}[\s-]?\d{3,14}',  # International with separators
            r'\b\d{10,15}\b',  # 10-15 digits
        ]
        
        for pattern in phone_patterns:
            match = re.search(pattern, message)
            if match:
                phone_number = match.group().strip()
                # Ensure it starts with + for international format
                if not phone_number.startswith('+'):
                    # Add default country code if none provided (this is basic - you might want to be more sophisticated)
                    if len(phone_number) == 10:  # Assume US number if 10 digits
                        phone_number = '+1' + phone_number
                    elif len(phone_number) == 11 and phone_number.startswith('1'):  # US number with country code
                        phone_number = '+' + phone_number
                    else:
                        phone_number = '+' + phone_number  # Just add + and hope for the best
                break
        
        # Extract custom message if provided
        custom_message = None
        custom_voice = None
        
        if 'say ' in message_lower:
            try:
                say_index = message_lower.find('say ')
                custom_message = message[say_index + 4:].strip().strip('"\'')
            except:
                pass
        
        if 'voice ' in message_lower or 'using ' in message_lower:
            # Extract voice preference (basic implementation)
            if 'jenny' in message_lower:
                custom_voice = 'en-US-JennyNeural'
            elif 'aria' in message_lower:
                custom_voice = 'en-US-AriaNeural'
            elif 'guy' in message_lower or 'male' in message_lower:
                custom_voice = 'en-US-GuyNeural'
        
        return {
            'should_call': should_call,
            'phone_number': phone_number,
            'custom_message': custom_message,
            'custom_voice': custom_voice,
            'original_message': message
        }
    
    async def _initiate_call(self, call_request: dict) -> dict:
        """
        Initiate ACS call with custom parameters from bot request
        Supports both VoIP (CommunicationUserIdentifier) and PSTN (PhoneNumberIdentifier) calls
        """
        try:
            if not self.acs_client:
                return {'success': False, 'error': 'ACS client not configured'}
            
            # Determine target and call type
            target_phone = call_request.get('phone_number') or TARGET_PHONE_NUMBER
            target_user_id = call_request.get('user_id') or TARGET_USER_ID
            
            # Decide whether to make PSTN or VoIP call
            use_pstn = bool(target_phone and target_phone.startswith('+'))
            
            if use_pstn:
                # PSTN call to phone number
                target_participant = PhoneNumberIdentifier(target_phone)
                source_caller_id = PhoneNumberIdentifier(SOURCE_CALLER_ID) if SOURCE_CALLER_ID else None
                call_type = "PSTN"
                target_display = target_phone
                callback_uri = f"https://{CALLBACK_URL_BASE}/api/PhoneCallWebhook"
                if 'localhost' in CALLBACK_URL_BASE or '127.0.0.1' in CALLBACK_URL_BASE:
                    callback_uri = f"http://localhost:7071/api/PhoneCallWebhook"
                
                # Check if source caller ID is available for PSTN calls
                if not source_caller_id:
                    return {'success': False, 'error': 'SOURCE_CALLER_ID is required for PSTN calls'}
                    
            elif target_user_id:
                # VoIP call to Communication User
                target_participant = CommunicationUserIdentifier(target_user_id)
                source_caller_id = None  # Not needed for VoIP calls
                call_type = "VoIP"
                target_display = target_user_id[:20] + "..." if len(target_user_id) > 20 else target_user_id
                callback_uri = f"https://{CALLBACK_URL_BASE}/api/BotCallWebhook"
                if 'localhost' in CALLBACK_URL_BASE or '127.0.0.1' in CALLBACK_URL_BASE:
                    callback_uri = f"http://localhost:7071/api/BotCallWebhook"
            else:
                return {'success': False, 'error': 'No valid target configured (no phone number or user ID)'}
            
            # Use custom message or default
            call_message = call_request.get('custom_message') or WELCOME_MESSAGE
            call_voice = call_request.get('custom_voice') or TTS_VOICE
            
            logging.info(f"Bot initiating {call_type} call to {target_display} with message: '{call_message[:50]}...', voice: {call_voice}")
            
            # Store call context for webhook (in production, use proper storage)
            global TEMP_CUSTOM_MESSAGE, TEMP_CUSTOM_VOICE
            TEMP_CUSTOM_MESSAGE = call_message
            TEMP_CUSTOM_VOICE = call_voice
            
            # Create the call with appropriate parameters
            call_params = {
                'target_participant': target_participant,
                'callback_url': callback_uri,
                'cognitive_services_endpoint': COGNITIVE_SERVICES_ENDPOINT
            }
            
            # Add source caller ID for PSTN calls
            if source_caller_id:
                call_params['source_caller_id_number'] = source_caller_id
            
            call_result = self.acs_client.create_call(**call_params)
            
            call_id = getattr(call_result, 'call_connection_id', 'Unknown')
            
            logging.info(f"Bot successfully initiated {call_type} call to {target_display}. Call ID: {call_id}")
            
            return {
                'success': True,
                'call_id': call_id,
                'message': call_message,
                'voice': call_voice,
                'call_type': call_type,
                'target': target_display
            }
            
        except Exception as e:
            logging.error(f"Error initiating call from bot: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _generate_response(self, user_message: str) -> str:
        """
        Generate intelligent response using OpenAI or fallback to basic responses
        """
        try:
            if self.openai_client:
                # Use OpenAI for intelligent responses
                system_prompt = """You are a helpful healthcare assistant bot that can initiate voice calls. 
                
Key capabilities:
- You can make voice calls to patients using Azure Communication Services
- You can access patient and appointment data from Cosmos DB
- You help with healthcare-related tasks and scheduling

If a user wants you to make a call, they can say things like:
- "Call the patient"
- "Make a voice call" 
- "Phone the user"
- "Call and say [custom message]"

You can also help with general healthcare questions and appointment management."""
                
                response = self.openai_client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    max_tokens=150,
                    temperature=0.7
                )
                
                return response.choices[0].message.content.strip()
            else:
                # Fallback to basic responses
                return self._get_basic_response(user_message)
                
        except Exception as e:
            logging.error(f"Error generating bot response: {str(e)}")
            return self._get_basic_response(user_message)
    
    def _get_basic_response(self, user_message: str) -> str:
        """
        Basic response patterns when OpenAI is not available
        """
        message_lower = user_message.lower()
        
        if any(word in message_lower for word in ['hello', 'hi', 'hey', 'start']):
            return "Hello! I'm your healthcare assistant. I can help you make voice calls to patients, manage appointments, and answer healthcare questions. Just ask me to 'call the patient' when you need to initiate a voice call."
        
        elif any(word in message_lower for word in ['help', 'what can you do', 'capabilities']):
            return "I can help you with:\n- Making voice calls to patients\n- Managing patient appointments\n- Accessing patient data\n- Healthcare assistance\n\nTo make a call, just say 'call the patient' or 'make a voice call'."
        
        elif any(word in message_lower for word in ['thank', 'thanks', 'bye', 'goodbye']):
            return "You're welcome! Feel free to ask me to make calls or help with healthcare tasks anytime."
        
        else:
            return "I understand you'd like assistance. I can make voice calls to patients and help with healthcare tasks. Try saying 'call the patient' to initiate a voice call, or ask me about appointments and patient data."

# Initialize global bot instance
call_bot = CallInitiatorBot()

# Initialize global Cosmos DB manager
cosmos_manager = CosmosDBManager()

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="MakeTestCall")
def MakeTestCall(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request to initiate a call.')
 
    # --- Input Validation ---
    if not all([ACS_CONNECTION_STRING, TARGET_USER_ID, CALLBACK_URL_BASE, COGNITIVE_SERVICES_ENDPOINT]):
        logging.error("Missing required configuration. Check Application Settings for ACS_CONNECTION_STRING, TARGET_USER_ID, CALLBACK_URL_BASE, and COGNITIVE_SERVICES_ENDPOINT.")
        return func.HttpResponse(
             "Server configuration error: Missing required settings.",
             status_code=500
        )
 
    try:
        # --- Initialize Clients ---
        logging.info("Initializing CallAutomationClient.")
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
       
        # The user we are going to call (our Web Softphone client)
        target_user = CommunicationUserIdentifier(TARGET_USER_ID)
       
        # The full URL for ACS to send events back to.
        # Using dedicated webhook endpoint for better monitoring
        callback_uri = f"https://{CALLBACK_URL_BASE}/api/CallWebhook"
        
        # For local testing, use localhost
        if 'localhost' in req.url or '127.0.0.1' in req.url:
            callback_uri = f"http://localhost:7071/api/CallWebhook"
            
        logging.info(f"Using callback URI: {callback_uri}")
 
        # --- Create the Call ---
        logging.info(f"Attempting to create a call to user: {TARGET_USER_ID[:10]}...")
        
        # Create call with callback_url (required by SDK) and Cognitive Services endpoint
        call_result = client.create_call(
            target_participant=target_user,
            callback_url=callback_uri,
            cognitive_services_endpoint=COGNITIVE_SERVICES_ENDPOINT
        )
        
        call_connection_id = call_result.call_connection_id if hasattr(call_result, 'call_connection_id') else 'Unknown'
        logging.info(f"Call created with ID: {call_connection_id}")
        
        # Store call connection for later use (for TTS after call is answered)
        # In a production environment, you'd store this in a database or cache
        # For now, we'll add a new endpoint to trigger TTS after call is answered
        
        logging.info("Successfully initiated call to web client.")
        return func.HttpResponse(
             f"Call initiated successfully. Call ID: {call_connection_id}. "
             f"Call should reach web client normally. Use /PlayMessage?callId={call_connection_id} for TTS or try /MakeTestCallWithAutoTTS for automatic TTS.",
             status_code=200
        )
 
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return func.HttpResponse(
             f"An error occurred while trying to initiate the call: {str(e)}",
             status_code=500
        )

@app.route(route="GetToken", methods=["GET", "POST", "OPTIONS"])
def GetToken(req: func.HttpRequest) -> func.HttpResponse:
    """
    Generate an access token for Azure Communication Services client
    This is needed for the web client to authenticate with ACS
    """
    # Handle CORS preflight requests
    if req.method == "OPTIONS":
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '86400'
        }
        return func.HttpResponse("", status_code=200, headers=headers)
    
    logging.info('Token request received.')
    
    try:
        # Get connection string
        connection_string = os.environ.get("ACS_CONNECTION_STRING", "")
        if not connection_string:
            logging.error("ACS_CONNECTION_STRING not found in environment")
            return func.HttpResponse(
                json.dumps({"error": "Server configuration error"}),
                status_code=500,
                mimetype="application/json"
            )
        
        # Initialize the CommunicationIdentityClient
        from azure.communication.identity import CommunicationIdentityClient, CommunicationTokenScope
        logging.info("Initializing CommunicationIdentityClient...")
        identity_client = CommunicationIdentityClient.from_connection_string(connection_string)
        
        # Get user ID from request or use the default one
        user_id = req.params.get('userId')
        if not user_id:
            try:
                req_body = req.get_json()
                if req_body:
                    user_id = req_body.get('userId')
            except ValueError:
                pass
        
        # If no specific user ID provided, use the default from environment
        if not user_id:
            user_id = os.environ.get("TARGET_USER_ID", "")
        
        if user_id:
            # Use existing user
            user = CommunicationUserIdentifier(user_id)
            logging.info(f"Using existing user: {user_id[:20] if len(user_id) > 20 else user_id}...")
        else:
            # Create a new user
            logging.info("Creating new user...")
            user = identity_client.create_user()
            if hasattr(user, 'properties') and user.properties:
                user_id_display = user.properties.get('id', 'Unknown')[:20]
            else:
                user_id_display = str(user)[:20]
            logging.info(f"Created new user: {user_id_display}...")
        
        logging.info("Generating access token...")
        
        # Create access token with calling scope
        token_result = identity_client.get_token(
            user, 
            scopes=[CommunicationTokenScope.VOIP]
        )
        
        # Handle expires_on safely
        try:
            if hasattr(token_result.expires_on, 'isoformat'):
                expires_on = token_result.expires_on.isoformat()
            else:
                expires_on = str(token_result.expires_on)
        except Exception:
            expires_on = "Unknown"
        
        # Handle user ID safely
        try:
            if hasattr(user, 'properties') and user.properties:
                user_id_response = user.properties['id']
            else:
                user_id_response = str(user)
        except Exception:
            user_id_response = "Unknown"
        
        response_data = {
            "token": str(token_result.token),
            "expiresOn": expires_on,
            "userId": user_id_response
        }
        
        logging.info("Access token generated successfully")
        
        # Add CORS headers for browser requests
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        return func.HttpResponse(
            json.dumps(response_data),
            status_code=200,
            mimetype="application/json",
            headers=headers
        )
        
    except Exception as e:
        logging.error(f"Error generating token: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Failed to generate token: {str(e)}"}),
            status_code=500,
            mimetype="application/json"
        )

@app.route(route="PlayMessage", methods=["GET", "POST"])
def PlayMessage(req: func.HttpRequest) -> func.HttpResponse:
    """
    Play a TTS message on an active call
    This endpoint can be called after the call is answered to play the welcome message
    """
    logging.info('PlayMessage: Request to play TTS message on active call')
    
    try:
        # Get call ID from query params or request body
        call_id = req.params.get('callId')
        custom_message = req.params.get('message')
        custom_voice = req.params.get('voice')
        
        if not call_id:
            try:
                req_body = req.get_json()
                if req_body:
                    call_id = req_body.get('callId')
                    custom_message = req_body.get('message')
                    custom_voice = req_body.get('voice')
            except ValueError:
                pass
        
        if not call_id:
            return func.HttpResponse(
                json.dumps({"error": "callId parameter is required"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Use custom message or default
        message_to_play = custom_message or WELCOME_MESSAGE
        voice_to_use = custom_voice or TTS_VOICE
        
        logging.info(f"PlayMessage: Attempting to play message on call ID: {call_id}")
        
        # Initialize the CallAutomationClient
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
        
        # Create text source for the message
        text_source = TextSource(
            text=message_to_play,
            voice_name=voice_to_use
        )
        
        logging.info(f"PlayMessage: Created TextSource with voice: {voice_to_use}, message length: {len(message_to_play)}")
        logging.info(f"PlayMessage: Using Cognitive Services endpoint: {COGNITIVE_SERVICES_ENDPOINT}")
        
        # Get the call connection
        call_connection = client.get_call_connection(call_id)
        logging.info(f"PlayMessage: Retrieved call connection for call ID: {call_id}")
        
        # Play the text message
        logging.info(f"PlayMessage: Initiating play_media request...")
        play_result = call_connection.play_media(
            play_source=text_source,
            play_to=[CommunicationUserIdentifier(TARGET_USER_ID)]
        )
        logging.info(f"PlayMessage: play_media request completed")
        
        operation_id = getattr(play_result, 'operation_id', 'Unknown')
        logging.info(f"PlayMessage: Successfully initiated TTS playback. Operation ID: {operation_id}")
        
        # Add CORS headers
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        response_data = {
            "success": True,
            "message": "TTS playback initiated successfully",
            "operationId": operation_id,
            "callId": call_id,
            "messageText": message_to_play,
            "voice": voice_to_use
        }
        
        return func.HttpResponse(
            json.dumps(response_data),
            status_code=200,
            mimetype="application/json",
            headers=headers
        )
        
    except Exception as e:
        logging.error(f"PlayMessage: Error playing message: {str(e)}")
        
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        return func.HttpResponse(
            json.dumps({"error": f"Failed to play message: {str(e)}"}),
            status_code=500,
            mimetype="application/json",
            headers=headers
        )

@app.route(route="MakeTestCallWithAutoTTS")
def MakeTestCallWithAutoTTS(req: func.HttpRequest) -> func.HttpResponse:
    """
    Create a call and automatically play TTS after a delay
    This gives time for the call to be answered before playing the message
    """
    logging.info('MakeTestCallWithAutoTTS: Initiating call with auto TTS')
    
    # --- Input Validation ---
    if not all([ACS_CONNECTION_STRING, TARGET_USER_ID, COGNITIVE_SERVICES_ENDPOINT]):
        logging.error("Missing required configuration. Check Application Settings for ACS_CONNECTION_STRING, TARGET_USER_ID, and COGNITIVE_SERVICES_ENDPOINT.")
        return func.HttpResponse(
             "Server configuration error: Missing required settings.",
             status_code=500
        )
    
    try:
        # Get optional delay parameter (default 5 seconds)
        delay_seconds = req.params.get('delay', '5')
        try:
            delay_seconds = int(delay_seconds)
        except ValueError:
            delay_seconds = 5
        
        # Get optional custom message
        custom_message = req.params.get('message')
        custom_voice = req.params.get('voice')
        
        # --- Initialize Clients ---
        logging.info("Initializing CallAutomationClient.")
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
       
        # The user we are going to call (our Web Softphone client)
        target_user = CommunicationUserIdentifier(TARGET_USER_ID)
       
        # --- Create the Call ---
        logging.info(f"Attempting to create a call to user: {TARGET_USER_ID[:10]}...")
        
        # Create call WITHOUT webhook to avoid connection issues
        # The SDK requires a callback URL but we'll use a minimal approach
        # We'll use the basic CallWebhook which just logs events
        callback_uri = f"https://{CALLBACK_URL_BASE}/api/CallWebhook"
        
        # For local testing, skip webhook entirely or use a dummy endpoint
        if 'localhost' in req.url or '127.0.0.1' in req.url:
            # Use a working webhook for local testing - just basic logging
            callback_uri = f"http://localhost:7071/api/CallWebhook"
        
        logging.info(f"MakeTestCallWithAutoTTS: Using callback URI: {callback_uri}")
        
        try:
            call_result = client.create_call(
                target_participant=target_user,
                callback_url=callback_uri,
                cognitive_services_endpoint=COGNITIVE_SERVICES_ENDPOINT
            )
        except Exception as call_error:
            # If webhook causes issues, try without specifying cognitive services endpoint
            logging.warning(f"MakeTestCallWithAutoTTS: Call creation with webhook failed: {call_error}")
            logging.info("MakeTestCallWithAutoTTS: Retrying call creation with minimal parameters...")
            
            call_result = client.create_call(
                target_participant=target_user,
                callback_url=callback_uri
            )
        
        call_connection_id = call_result.call_connection_id if hasattr(call_result, 'call_connection_id') else 'Unknown'
        logging.info(f"Call created with ID: {call_connection_id}")
        
        # Import threading for delayed execution
        import threading
        import time
        
        def play_delayed_message():
            """Play TTS message after delay with call state checking"""
            try:
                logging.info(f"MakeTestCallWithAutoTTS: Starting delayed TTS thread, waiting {delay_seconds} seconds...")
                time.sleep(delay_seconds)
                
                # Use custom message or default
                message_to_play = custom_message or WELCOME_MESSAGE
                voice_to_use = custom_voice or TTS_VOICE
                
                logging.info(f"MakeTestCallWithAutoTTS: Delay complete, attempting to play TTS message")
                logging.info(f"MakeTestCallWithAutoTTS: Message: '{message_to_play[:50]}...', Voice: {voice_to_use}")
                
                # Retry logic for call connection - the call might still be connecting
                max_retries = 3
                retry_delay = 2
                
                for attempt in range(max_retries):
                    try:
                        logging.info(f"MakeTestCallWithAutoTTS: Attempt {attempt + 1}/{max_retries} to get call connection")
                        
                        # Get call connection
                        call_connection = client.get_call_connection(call_connection_id)
                        
                        # Try to get call properties to check if call is connected
                        call_properties = call_connection.get_call_properties()
                        call_state = getattr(call_properties, 'call_state', 'Unknown')
                        logging.info(f"MakeTestCallWithAutoTTS: Call state: {call_state}")
                        
                        # Create text source
                        text_source = TextSource(
                            text=message_to_play,
                            voice_name=voice_to_use
                        )
                        
                        logging.info(f"MakeTestCallWithAutoTTS: Created TextSource, initiating play_media request...")
                        logging.info(f"MakeTestCallWithAutoTTS: Using Cognitive Services endpoint: {COGNITIVE_SERVICES_ENDPOINT}")
                        
                        # Attempt to play the message
                        play_result = call_connection.play_media(
                            play_source=text_source,
                            play_to=[CommunicationUserIdentifier(TARGET_USER_ID)]
                        )
                        
                        operation_id = getattr(play_result, 'operation_id', 'Unknown')
                        logging.info(f"MakeTestCallWithAutoTTS: TTS playback initiated successfully! Operation ID: {operation_id}")
                        return  # Success, exit the retry loop
                        
                    except Exception as attempt_error:
                        logging.warning(f"MakeTestCallWithAutoTTS: Attempt {attempt + 1} failed: {str(attempt_error)}")
                        if attempt < max_retries - 1:
                            logging.info(f"MakeTestCallWithAutoTTS: Waiting {retry_delay} seconds before retry...")
                            time.sleep(retry_delay)
                        else:
                            logging.error(f"MakeTestCallWithAutoTTS: All {max_retries} attempts failed")
                            raise attempt_error
                            
            except Exception as e:
                logging.error(f"MakeTestCallWithAutoTTS: Error in delayed TTS: {str(e)}")
                logging.error(f"MakeTestCallWithAutoTTS: Call ID: {call_connection_id}")
                logging.error(f"MakeTestCallWithAutoTTS: This may indicate the call is not connected yet or has been disconnected")
        
        # Start the delayed TTS in a background thread
        threading.Thread(target=play_delayed_message, daemon=True).start()
        
        logging.info(f"Successfully initiated call with auto TTS (delay: {delay_seconds}s). Call ID: {call_connection_id}")
        return func.HttpResponse(
             f"Call initiated successfully with auto TTS. Call ID: {call_connection_id}. "
             f"TTS will play after {delay_seconds} seconds with retry logic. "
             f"Message: '{(custom_message or WELCOME_MESSAGE)[:50]}...' "
             f"Voice: {custom_voice or TTS_VOICE}",
             status_code=200
        )
 
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return func.HttpResponse(
             f"An error occurred while trying to initiate the call: {str(e)}",
             status_code=500
        )

@app.route(route="MakeTestCallWithWebhookTTS", methods=["GET", "POST"])
def MakeTestCallWithWebhookTTS(req: func.HttpRequest) -> func.HttpResponse:
    """
    Create a call using webhook-based TTS (most reliable approach)
    This creates a call and uses the webhook event to trigger TTS when connected
    """
    logging.info('MakeTestCallWithWebhookTTS: Request to create call with webhook-based auto TTS')
    
    try:
        # Get custom message and voice if provided
        custom_message = req.params.get('message')
        custom_voice = req.params.get('voice')
        
        # Check if custom parameters were provided in request body
        if req.method == "POST":
            try:
                req_body = req.get_json()
                if req_body:
                    custom_message = req_body.get('message', custom_message)
                    custom_voice = req_body.get('voice', custom_voice)
            except ValueError:
                pass
        
        # Store custom settings in a simple way (for webhook to use)
        # Note: In production, you'd use a proper storage mechanism
        global TEMP_CUSTOM_MESSAGE, TEMP_CUSTOM_VOICE
        TEMP_CUSTOM_MESSAGE = custom_message or WELCOME_MESSAGE
        TEMP_CUSTOM_VOICE = custom_voice or TTS_VOICE
        
        logging.info(f"MakeTestCallWithWebhookTTS: Using message: '{TEMP_CUSTOM_MESSAGE[:50]}...', voice: {TEMP_CUSTOM_VOICE}")
        
        # Initialize CallAutomationClient
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
        
        # The user we are going to call
        target_user = CommunicationUserIdentifier(TARGET_USER_ID)
        
        # Use the webhook with auto TTS
        callback_uri = f"https://{CALLBACK_URL_BASE}/api/CallWebhookWithAutoTTS"
        
        # For local testing, use localhost
        if 'localhost' in req.url or '127.0.0.1' in req.url:
            callback_uri = f"http://localhost:7071/api/CallWebhookWithAutoTTS"
            
        logging.info(f"MakeTestCallWithWebhookTTS: Using callback URI: {callback_uri}")
        
        # Create the call
        logging.info(f"MakeTestCallWithWebhookTTS: Creating call to user: {TARGET_USER_ID[:10]}...")
        
        call_result = client.create_call(
            target_participant=target_user,
            callback_url=callback_uri,
            cognitive_services_endpoint=COGNITIVE_SERVICES_ENDPOINT
        )
        
        call_connection_id = call_result.call_connection_id if hasattr(call_result, 'call_connection_id') else 'Unknown'
        logging.info(f"MakeTestCallWithWebhookTTS: Call created with ID: {call_connection_id}")
        
        # Add CORS headers
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        response_data = {
            "success": True,
            "message": "Call initiated with webhook-based auto TTS",
            "callId": call_connection_id,
            "ttsMessage": TEMP_CUSTOM_MESSAGE[:100] + "..." if len(TEMP_CUSTOM_MESSAGE) > 100 else TEMP_CUSTOM_MESSAGE,
            "voice": TEMP_CUSTOM_VOICE,
            "webhookUrl": callback_uri
        }
        
        return func.HttpResponse(
            json.dumps(response_data),
            status_code=200,
            mimetype="application/json",
            headers=headers
        )
        
    except Exception as e:
        logging.error(f"MakeTestCallWithWebhookTTS: Error: {str(e)}")
        
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        return func.HttpResponse(
            json.dumps({"error": f"Failed to create call: {str(e)}"}),
            status_code=500,
            mimetype="application/json",
            headers=headers
        )

@app.route(route="CallWebhookWithAutoTTS", methods=["POST"])
def CallWebhookWithAutoTTS(req: func.HttpRequest) -> func.HttpResponse:
    """
    Webhook endpoint that automatically plays TTS when call connects
    This is the original approach that plays TTS via webhook events
    """
    global TEMP_CUSTOM_MESSAGE, TEMP_CUSTOM_VOICE
    logging.info('CallWebhookWithAutoTTS: Received call event')
    
    try:
        # Get the event data
        event_data = req.get_body().decode('utf-8')
        logging.info(f"CallWebhookWithAutoTTS: Raw event data: {event_data}")
        
        # Parse the JSON event
        events = json.loads(event_data)
        if not isinstance(events, list):
            events = [events]
        
        # Initialize the CallAutomationClient for handling events
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
        
        for event in events:
            event_type = event.get('type', 'Unknown')
            call_connection_id = event.get('data', {}).get('callConnectionId', 'Unknown')
            
            logging.info(f"CallWebhookWithAutoTTS: Processing event type: {event_type}, Call ID: {call_connection_id}")
            
            # Handle CallConnected event - this is when we play the message
            if event_type == 'Microsoft.Communication.CallConnected':
                logging.info(f"CallWebhookWithAutoTTS: Call connected! Playing welcome message...")
                
                # Use temporary custom values if set, otherwise use defaults
                message_to_play = TEMP_CUSTOM_MESSAGE or WELCOME_MESSAGE
                voice_to_use = TEMP_CUSTOM_VOICE or TTS_VOICE
                
                logging.info(f"CallWebhookWithAutoTTS: Using message: '{message_to_play[:50]}...', voice: {voice_to_use}")
                
                # Create text source for the message
                text_source = TextSource(
                    text=message_to_play,
                    voice_name=voice_to_use
                )
                
                try:
                    # Get the call connection
                    call_connection = client.get_call_connection(call_connection_id)
                    
                    # Play the text message
                    play_result = call_connection.play_media(
                        play_source=text_source,
                        play_to=[CommunicationUserIdentifier(TARGET_USER_ID)]
                    )
                    
                    logging.info(f"CallWebhookWithAutoTTS: Successfully initiated text playback. Operation ID: {getattr(play_result, 'operation_id', 'Unknown')}")
                    
                except Exception as play_error:
                    logging.error(f"CallWebhookWithAutoTTS: Error playing message: {str(play_error)}")
            
            # Handle other events
            elif event_type == 'Microsoft.Communication.CallDisconnected':
                logging.info(f"CallWebhookWithAutoTTS: Call disconnected")
            elif event_type == 'Microsoft.Communication.PlayCompleted':
                logging.info(f"CallWebhookWithAutoTTS: Message playback completed")
            elif event_type == 'Microsoft.Communication.PlayFailed':
                logging.warning(f"CallWebhookWithAutoTTS: Message playback failed")
            else:
                logging.info(f"CallWebhookWithAutoTTS: Received event type: {event_type}")
        
        # Return success response
        return func.HttpResponse(
            "Webhook processed successfully",
            status_code=200
        )
        
    except json.JSONDecodeError as json_error:
        logging.error(f"CallWebhookWithAutoTTS: Invalid JSON in request body: {str(json_error)}")
        return func.HttpResponse(
            "Invalid JSON in request body",
            status_code=400
        )
        
    except Exception as e:
        logging.error(f"CallWebhookWithAutoTTS: Error processing webhook: {str(e)}")
        return func.HttpResponse(
            f"Error processing webhook: {str(e)}",
            status_code=500
        )

@app.route(route="MakeTestCallNoWebhook")
def MakeTestCallNoWebhook(req: func.HttpRequest) -> func.HttpResponse:
    """
    Create a call WITHOUT webhook - most reliable for client connection
    Uses threading to play TTS after delay, but no webhook dependencies
    """
    logging.info('MakeTestCallNoWebhook: Initiating call without webhook dependencies')
    
    # --- Input Validation ---
    if not all([ACS_CONNECTION_STRING, TARGET_USER_ID, COGNITIVE_SERVICES_ENDPOINT]):
        logging.error("Missing required configuration.")
        return func.HttpResponse(
             "Server configuration error: Missing required settings.",
             status_code=500
        )
    
    try:
        # Get optional delay parameter (default 8 seconds for no-webhook)
        delay_seconds = req.params.get('delay', '8')
        try:
            delay_seconds = int(delay_seconds)
        except ValueError:
            delay_seconds = 8
        
        # Get optional custom message
        custom_message = req.params.get('message')
        custom_voice = req.params.get('voice')
        
        # --- Initialize Clients ---
        logging.info("MakeTestCallNoWebhook: Initializing CallAutomationClient.")
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
       
        # The user we are going to call (our Web Softphone client)
        target_user = CommunicationUserIdentifier(TARGET_USER_ID)
       
        # --- Create the Call WITHOUT webhook ---
        logging.info(f"MakeTestCallNoWebhook: Creating call to user: {TARGET_USER_ID[:10]}... (NO WEBHOOK)")
        
        try:
            # Try creating call with minimal parameters first
            call_result = client.create_call(
                target_participant=target_user
            )
            logging.info("MakeTestCallNoWebhook: Call created successfully without webhook")
            
        except Exception as minimal_error:
            # If that fails, try with cognitive services endpoint but still no webhook
            logging.warning(f"MakeTestCallNoWebhook: Minimal call failed: {minimal_error}")
            logging.info("MakeTestCallNoWebhook: Trying with Cognitive Services endpoint...")
            
            # Create a dummy webhook URL that won't be used
            dummy_callback = f"https://httpbin.org/post"  # Public endpoint that accepts POST
            
            call_result = client.create_call(
                target_participant=target_user,
                callback_url=dummy_callback,
                cognitive_services_endpoint=COGNITIVE_SERVICES_ENDPOINT
            )
            logging.info("MakeTestCallNoWebhook: Call created with dummy webhook")
        
        call_connection_id = call_result.call_connection_id if hasattr(call_result, 'call_connection_id') else 'Unknown'
        logging.info(f"MakeTestCallNoWebhook: Call created with ID: {call_connection_id}")
        
        # Import threading for delayed execution
        import threading
        import time
        
        def play_delayed_message():
            """Play TTS message after delay with robust error handling"""
            try:
                logging.info(f"MakeTestCallNoWebhook: Waiting {delay_seconds} seconds for call to connect...")
                time.sleep(delay_seconds)
                
                # Use custom message or default
                message_to_play = custom_message or WELCOME_MESSAGE
                voice_to_use = custom_voice or TTS_VOICE
                
                logging.info(f"MakeTestCallNoWebhook: Attempting TTS playback")
                logging.info(f"MakeTestCallNoWebhook: Message: '{message_to_play[:50]}...', Voice: {voice_to_use}")
                
                # Retry logic with longer delays for no-webhook approach
                max_retries = 5
                retry_delay = 3
                
                for attempt in range(max_retries):
                    try:
                        logging.info(f"MakeTestCallNoWebhook: Attempt {attempt + 1}/{max_retries}")
                        
                        # Reinitialize client for the thread
                        thread_client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
                        
                        # Get call connection
                        call_connection = thread_client.get_call_connection(call_connection_id)
                        
                        # Check call state
                        try:
                            call_properties = call_connection.get_call_properties()
                            call_state = getattr(call_properties, 'call_state', 'Unknown')
                            logging.info(f"MakeTestCallNoWebhook: Call state: {call_state}")
                        except Exception as state_error:
                            logging.warning(f"MakeTestCallNoWebhook: Could not get call state: {state_error}")
                        
                        # Create text source
                        text_source = TextSource(
                            text=message_to_play,
                            voice_name=voice_to_use
                        )
                        
                        # Attempt to play the message
                        logging.info(f"MakeTestCallNoWebhook: Initiating play_media...")
                        play_result = call_connection.play_media(
                            play_source=text_source,
                            play_to=[CommunicationUserIdentifier(TARGET_USER_ID)]
                        )
                        
                        operation_id = getattr(play_result, 'operation_id', 'Unknown')
                        logging.info(f"MakeTestCallNoWebhook: SUCCESS! TTS initiated. Operation ID: {operation_id}")
                        return  # Success, exit retry loop
                        
                    except Exception as attempt_error:
                        error_msg = str(attempt_error)
                        logging.warning(f"MakeTestCallNoWebhook: Attempt {attempt + 1} failed: {error_msg}")
                        
                        if "bad request to cognitive services" in error_msg.lower():
                            logging.error("MakeTestCallNoWebhook: Cognitive Services error - check region and endpoint")
                        elif "call not found" in error_msg.lower():
                            logging.error("MakeTestCallNoWebhook: Call may have been disconnected")
                        
                        if attempt < max_retries - 1:
                            logging.info(f"MakeTestCallNoWebhook: Waiting {retry_delay} seconds before retry...")
                            time.sleep(retry_delay)
                        else:
                            logging.error(f"MakeTestCallNoWebhook: All {max_retries} attempts failed")
                            
            except Exception as e:
                logging.error(f"MakeTestCallNoWebhook: Thread error: {str(e)}")
        
        # Start the delayed TTS in a background thread
        logging.info(f"MakeTestCallNoWebhook: Starting TTS thread with {delay_seconds}s delay")
        threading.Thread(target=play_delayed_message, daemon=True).start()
        
        # Add CORS headers
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        response_data = {
            "success": True,
            "message": "Call initiated WITHOUT webhook - best for client connectivity",
            "callId": call_connection_id,
            "delaySeconds": delay_seconds,
            "ttsMessage": (custom_message or WELCOME_MESSAGE)[:100] + "..." if len(custom_message or WELCOME_MESSAGE) > 100 else (custom_message or WELCOME_MESSAGE),
            "voice": custom_voice or TTS_VOICE,
            "note": "No webhook used - call should reach client immediately"
        }
        
        return func.HttpResponse(
            json.dumps(response_data),
            status_code=200,
            mimetype="application/json",
            headers=headers
        )
 
    except Exception as e:
        logging.error(f"MakeTestCallNoWebhook: Error: {str(e)}")
        
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        return func.HttpResponse(
            json.dumps({"error": f"Failed to create call: {str(e)}"}),
            status_code=500,
            mimetype="application/json",
            headers=headers
        )

# ================================
# BOT SERVICE ENDPOINTS
# ================================

@app.route(route="bot/messages", methods=["POST", "OPTIONS"])
def bot_messages(req: func.HttpRequest) -> func.HttpResponse:
    """
    Main bot endpoint to handle incoming messages from Azure Bot Service
    Processes user messages and initiates calls when requested
    """
    # Handle CORS preflight requests
    if req.method == "OPTIONS":
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Access-Control-Max-Age': '86400'
        }
        return func.HttpResponse("", status_code=200, headers=headers)
    
    logging.info('Bot: Received message from Azure Bot Service')
    
    try:
        # Get the activity from the request body
        activity_data = req.get_json()
        if not activity_data:
            logging.error("Bot: No activity data received")
            return func.HttpResponse(
                json.dumps({"error": "No activity data received"}),
                status_code=400,
                mimetype="application/json"
            )
        
        logging.info(f"Bot: Activity type: {activity_data.get('type')}, Text: {activity_data.get('text')}")
        
        # Only process message activities
        if activity_data.get('type') != 'message':
            logging.info(f"Bot: Ignoring non-message activity: {activity_data.get('type')}")
            return func.HttpResponse("", status_code=200)
        
        # Check if bot is properly configured
        if not BOT_APP_ID or not BOT_APP_PASSWORD:
            logging.error("Bot: BOT_APP_ID or BOT_APP_PASSWORD not configured")
            response_activity = create_bot_response(
                activity_data,
                "Sorry, I'm not properly configured. Please check my bot credentials."
            )
        else:
            # Process the message using our bot logic
            # Note: We're using a simplified approach here since we can't easily use async in Azure Functions v1
            try:
                # Simulate the async call for now
                bot_result = process_bot_message_sync(activity_data)
                response_text = bot_result.get('response_text', 'I understand your message.')
                
                # Log call information if applicable
                if bot_result.get('call_initiated'):
                    logging.info(f"Bot: Successfully initiated call. Call ID: {bot_result.get('call_id')}")
                elif bot_result.get('call_error'):
                    logging.error(f"Bot: Failed to initiate call: {bot_result.get('call_error')}")
                
                response_activity = create_bot_response(activity_data, response_text)
                
            except Exception as process_error:
                logging.error(f"Bot: Error processing message: {str(process_error)}")
                response_activity = create_bot_response(
                    activity_data,
                    "I encountered an error processing your request. Please try again."
                )
        
        # Return the response activity
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization'
        }
        
        return func.HttpResponse(
            json.dumps(response_activity),
            status_code=200,
            mimetype="application/json",
            headers=headers
        )
        
    except json.JSONDecodeError:
        logging.error("Bot: Invalid JSON in request body")
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON in request body"}),
            status_code=400,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Bot: Unexpected error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Unexpected error: {str(e)}"}),
            status_code=500,
            mimetype="application/json"
        )

def process_bot_message_sync(activity_data: dict) -> dict:
    """
    Synchronous wrapper for bot message processing
    Since Azure Functions v1 doesn't handle async easily, we simulate the async processing
    """
    try:
        user_message = activity_data.get('text', '').strip()
        user_id = activity_data.get('from', {}).get('id', 'unknown')
        
        logging.info(f"Bot: Processing sync message from {user_id}: {user_message}")
        
        # Check if user is requesting a call
        call_request = call_bot._analyze_call_request(user_message)
        
        if call_request['should_call']:
            # Initiate the call synchronously
            call_result = initiate_call_sync(call_request)
            
            if call_result['success']:
                response_text = f"I've initiated a call to the target user as requested. " \
                              f"Call ID: {call_result['call_id']}. " \
                              f"The call should connect shortly and you'll hear: '{call_result['message'][:50]}...'"
            else:
                response_text = f"I wasn't able to initiate the call. Error: {call_result['error']}"
                
            return {
                'response_text': response_text,
                'call_initiated': call_result['success'],
                'call_id': call_result.get('call_id'),
                'call_error': call_result.get('error')
            }
        else:
            # Regular bot conversation
            response_text = generate_response_sync(user_message)
            return {
                'response_text': response_text,
                'call_initiated': False
            }
            
    except Exception as e:
        logging.error(f"Bot: Error in sync processing: {str(e)}")
        return {
            'response_text': "I'm sorry, I encountered an error processing your request.",
            'call_initiated': False,
            'error': str(e)
        }

def initiate_call_sync(call_request: dict) -> dict:
    """
    Synchronous call initiation for bot requests
    Uses no-webhook approach for local development to avoid connectivity issues
    """
    try:
        if not ACS_CONNECTION_STRING:
            return {'success': False, 'error': 'ACS not configured'}
        
        if not TARGET_USER_ID:
            return {'success': False, 'error': 'TARGET_USER_ID not configured'}
        
        # Initialize ACS client
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
        
        # Prepare call parameters
        target_user = CommunicationUserIdentifier(TARGET_USER_ID)
        
        # Use custom message or default
        call_message = call_request.get('custom_message') or WELCOME_MESSAGE
        call_voice = call_request.get('custom_voice') or TTS_VOICE
        
        logging.info(f"Bot: Initiating call with message: '{call_message[:50]}...', voice: {call_voice}")
        
        # Create callback URL for the call
        callback_uri = f"https://{CALLBACK_URL_BASE}/api/BotCallWebhook"
        if 'localhost' in CALLBACK_URL_BASE or '127.0.0.1' in CALLBACK_URL_BASE:
            logging.warning("Bot: Localhost detected in CALLBACK_URL_BASE - webhook may not work")
        
        logging.info(f"Bot: Using callback URL: {callback_uri}")
        
        # Store call context for webhook
        global TEMP_CUSTOM_MESSAGE, TEMP_CUSTOM_VOICE
        TEMP_CUSTOM_MESSAGE = call_message
        TEMP_CUSTOM_VOICE = call_voice
        
        # Create the call
        call_result = client.create_call(
            target_participant=target_user,
            callback_url=callback_uri,
            cognitive_services_endpoint=COGNITIVE_SERVICES_ENDPOINT
        )
        
        call_id = getattr(call_result, 'call_connection_id', 'Unknown')
        
        logging.info(f"Bot: Successfully initiated call. Call ID: {call_id}")
        
        return {
            'success': True,
            'call_id': call_id,
            'message': call_message,
            'voice': call_voice
        }
        
    except Exception as e:
        logging.error(f"Bot: Error initiating call: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

def generate_response_sync(user_message: str) -> str:
    """
    Synchronous response generation
    """
    try:
        # Try to use OpenAI if configured
        if OPENAI_API_KEY and OPENAI_ENDPOINT:
            try:
                client = AzureOpenAI(
                    api_key=OPENAI_API_KEY,
                    api_version="2024-02-01",
                    azure_endpoint=OPENAI_ENDPOINT
                )
                
                system_prompt = """You are a helpful healthcare assistant bot that can initiate voice calls.

Key capabilities:
- You can make voice calls to patients using Azure Communication Services
- You can access patient and appointment data from Cosmos DB
- You help with healthcare-related tasks and scheduling

If a user wants you to make a call, they can say things like:
- "Call the patient"
- "Make a voice call" 
- "Phone the user"
- "Call and say [custom message]"

You can also help with general healthcare questions and appointment management."""
                
                response = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    max_tokens=150,
                    temperature=0.7
                )
                
                return response.choices[0].message.content.strip()
                
            except Exception as openai_error:
                logging.error(f"Bot: OpenAI error: {str(openai_error)}")
                return get_basic_response_sync(user_message)
        else:
            return get_basic_response_sync(user_message)
            
    except Exception as e:
        logging.error(f"Bot: Error generating response: {str(e)}")
        return get_basic_response_sync(user_message)

def get_basic_response_sync(user_message: str) -> str:
    """
    Basic response patterns when OpenAI is not available
    """
    message_lower = user_message.lower()
    
    if any(word in message_lower for word in ['hello', 'hi', 'hey', 'start']):
        return "Hello! I'm your healthcare assistant. I can help you make voice calls to patients, manage appointments, and answer healthcare questions. Just ask me to 'call the patient' when you need to initiate a voice call."
    
    elif any(word in message_lower for word in ['help', 'what can you do', 'capabilities']):
        return "I can help you with:\n- Making voice calls to patients\n- Managing patient appointments\n- Accessing patient data\n- Healthcare assistance\n\nTo make a call, just say 'call the patient' or 'make a voice call'."
    
    elif any(word in message_lower for word in ['thank', 'thanks', 'bye', 'goodbye']):
        return "You're welcome! Feel free to ask me to make calls or help with healthcare tasks anytime."
    
    else:
        return "I understand you'd like assistance. I can make voice calls to patients and help with healthcare tasks. Try saying 'call the patient' to initiate a voice call, or ask me about appointments and patient data."

def create_bot_response(incoming_activity: dict, response_text: str) -> dict:
    """
    Create a properly formatted bot response activity
    """
    return {
        "type": "message",
        "text": response_text,
        "replyToId": incoming_activity.get("id"),
        "conversation": incoming_activity.get("conversation"),
        "from": {
            "id": BOT_APP_ID,
            "name": "Healthcare Call Assistant"
        },
        "recipient": incoming_activity.get("from"),
        "serviceUrl": incoming_activity.get("serviceUrl"),
        "channelId": incoming_activity.get("channelId")
    }

@app.route(route="BotCallWebhook", methods=["POST"])
def bot_call_webhook(req: func.HttpRequest) -> func.HttpResponse:
    """
    Webhook endpoint for calls initiated by the bot
    Handles call events and plays TTS messages when call connects
    """
    global TEMP_CUSTOM_MESSAGE, TEMP_CUSTOM_VOICE
    logging.info('BotCallWebhook: Received call event from bot-initiated call')
    
    try:
        # Get the event data
        event_data = req.get_body().decode('utf-8')
        logging.info(f"BotCallWebhook: Raw event data: {event_data}")
        
        # Parse the JSON event
        events = json.loads(event_data)
        if not isinstance(events, list):
            events = [events]
        
        # Initialize the CallAutomationClient for handling events
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
        
        for event in events:
            event_type = event.get('type', 'Unknown')
            call_connection_id = event.get('data', {}).get('callConnectionId', 'Unknown')
            
            logging.info(f"BotCallWebhook: Processing event type: {event_type}, Call ID: {call_connection_id}")
            
            # Handle CallConnected event - this is when we play the message
            if event_type == 'Microsoft.Communication.CallConnected':
                logging.info(f"BotCallWebhook: Call connected! Playing bot-requested message...")
                
                # Use temporary custom values if set, otherwise use defaults
                message_to_play = TEMP_CUSTOM_MESSAGE or WELCOME_MESSAGE
                voice_to_use = TEMP_CUSTOM_VOICE or TTS_VOICE
                
                logging.info(f"BotCallWebhook: Using message: '{message_to_play[:50]}...', voice: {voice_to_use}")
                
                # Create text source for the message
                text_source = TextSource(
                    text=message_to_play,
                    voice_name=voice_to_use
                )
                
                try:
                    # Get the call connection
                    call_connection = client.get_call_connection(call_connection_id)
                    
                    # Play the text message
                    play_result = call_connection.play_media_to_all(
                        play_source=text_source
                    )
                    
                    logging.info(f"BotCallWebhook: Successfully initiated text playback. Operation ID: {getattr(play_result, 'operation_id', 'Unknown')}")
                    
                except Exception as play_error:
                    logging.error(f"BotCallWebhook: Error playing message: {str(play_error)}")
            
            # Handle other events
            elif event_type == 'Microsoft.Communication.CallDisconnected':
                logging.info(f"BotCallWebhook: Bot-initiated call disconnected")
                # Clear temporary message settings
                TEMP_CUSTOM_MESSAGE = None
                TEMP_CUSTOM_VOICE = None
            elif event_type == 'Microsoft.Communication.PlayCompleted':
                logging.info(f"BotCallWebhook: Bot message playback completed")
            elif event_type == 'Microsoft.Communication.PlayFailed':
                logging.warning(f"BotCallWebhook: Bot message playback failed")
            else:
                logging.info(f"BotCallWebhook: Received event type: {event_type}")
        
        # Return success response
        return func.HttpResponse(
            "Bot webhook processed successfully",
            status_code=200
        )
        
    except json.JSONDecodeError as json_error:
        logging.error(f"BotCallWebhook: Invalid JSON in request body: {str(json_error)}")
        return func.HttpResponse(
            "Invalid JSON in request body",
            status_code=400
        )
        
    except Exception as e:
        logging.error(f"BotCallWebhook: Error processing webhook: {str(e)}")
        return func.HttpResponse(
            f"Error processing webhook: {str(e)}",
            status_code=500
        )

@app.route(route="TestBotCall", methods=["GET", "POST", "OPTIONS"])
def test_bot_call(req: func.HttpRequest) -> func.HttpResponse:
    """
    Test endpoint to simulate bot message and call initiation
    Useful for testing bot integration without going through Azure Bot Service
    """
    # Handle CORS preflight requests
    if req.method == "OPTIONS":
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '86400'
        }
        return func.HttpResponse("", status_code=200, headers=headers)
    
    logging.info('TestBotCall: Testing bot call integration')
    
    try:
        # Get test message from query params or request body
        test_message = req.params.get('message', 'call the patient')
        custom_message = req.params.get('customMessage')
        
        if req.method == "POST":
            try:
                req_body = req.get_json()
                if req_body:
                    test_message = req_body.get('message', test_message)
                    custom_message = req_body.get('customMessage', custom_message)
            except ValueError:
                pass
        
        logging.info(f"TestBotCall: Testing with message: '{test_message}'")
        
        # Create a simulated bot activity
        test_activity = {
            "type": "message",
            "text": test_message,
            "from": {"id": "test-user", "name": "Test User"},
            "conversation": {"id": "test-conversation"},
            "id": "test-message-id",
            "serviceUrl": "https://test.botframework.com",
            "channelId": "test"
        }
        
        # If custom message is provided, append it
        if custom_message:
            test_activity["text"] += f" and say '{custom_message}'"
        
        # Process the message
        bot_result = process_bot_message_sync(test_activity)
        
        # Add CORS headers
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        response_data = {
            "success": True,
            "testMessage": test_message,
            "botResponse": bot_result.get('response_text'),
            "callInitiated": bot_result.get('call_initiated', False),
            "callId": bot_result.get('call_id'),
            "callError": bot_result.get('call_error'),
            "configuration": {
                "botAppId": BOT_APP_ID[:20] + "..." if BOT_APP_ID else "Not configured",
                "acsConfigured": bool(ACS_CONNECTION_STRING),
                "openaiConfigured": bool(OPENAI_API_KEY and OPENAI_ENDPOINT),
                "targetUserId": TARGET_USER_ID[:20] + "..." if TARGET_USER_ID else "Not configured"
            }
        }
        
        return func.HttpResponse(

            json.dumps(response_data, indent=2),
            status_code=200,
            mimetype="application/json",
            headers=headers
        )
        
    except Exception as e:
        logging.error(f"TestBotCall: Error: {str(e)}")
        
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            mimetype="application/json",
            headers=headers
        )

# ================================
# PATIENT MANAGEMENT ENDPOINTS
# ================================

@app.route(route="patients", methods=["GET", "POST", "OPTIONS"])
def manage_patients(req: func.HttpRequest) -> func.HttpResponse:
    """
    Patient management endpoint
    GET: List all patients
    POST: Create a new patient
    """
    # Handle CORS preflight requests
    if req.method == "OPTIONS":
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '86400'
        }
        return func.HttpResponse("", status_code=200, headers=headers)
    
    logging.info(f'Patient management: {req.method} request received')
    
    # Check if Cosmos DB is configured
    if not cosmos_manager.is_connected():
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        return func.HttpResponse(
            json.dumps({"error": "Cosmos DB not configured. Please set COSMOS_CONNECTION_STRING."}),
            status_code=500,
            mimetype="application/json",
            headers=headers
        )
    
    try:
        if req.method == "GET":
            # List patients
            limit = int(req.params.get('limit', 100))
            
            # Since we can't use async in Azure Functions v1 model easily, we'll use synchronous methods
            # In production, consider upgrading to Azure Functions v2 programming model for async support
            try:
                # Simulate async call with direct container access
                query = "SELECT * FROM c ORDER BY c.createdAt DESC"
                items = list(cosmos_manager.patients_container.query_items(
                    query=query,
                    max_item_count=limit,
                    enable_cross_partition_query=True                ))
                
                response_data = {
                    "success": True,
                    "patients": items,
                    "count": len(items),
                    "message": f"Retrieved {len(items)} patients"
                }
                
            except Exception as e:
                logging.error(f"Error listing patients: {str(e)}")
                response_data = {

                    "success": False,
                    "error": f"Failed to list patients: {str(e)}"
                }
                
        elif req.method == "POST":
            # Create patient
            try:
                patient_data = req.get_json()
                if not patient_data:
                    raise Exception("No patient data provided")
                
                # Ensure required fields
                if 'id' not in patient_data:
                    patient_data['id'] = patient_data.get('patientId', str(int(time.time())))
                if 'patientId' not in patient_data:
                    patient_data['patientId'] = patient_data['id']
                    
                # Add metadata
                patient_data['createdAt'] = int(time.time())
                patient_data['updatedAt'] = int(time.time())
                
                # Create patient
                response = cosmos_manager.patients_container.create_item(body=patient_data)
                
                response_data = {
                    "success": True,
                    "patient": response,
                    "message": f"Patient created successfully with ID: {patient_data['id']}"
                }
                
            except Exception as e:
                logging.error(f"Error creating patient: {str(e)}")
                response_data = {
                    "success": False,
                    "error": f"Failed to create patient: {str(e)}"
                }
        
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        status_code = 200 if response_data.get("success") else 400
        
        return func.HttpResponse(
            json.dumps(response_data),
            status_code=status_code,
            mimetype="application/json",
            headers=headers
        )
        
    except Exception as e:
        logging.error(f"Patient management error: {str(e)}")
        
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            mimetype="application/json",
            headers=headers
        )

@app.route(route="patients/{patient_id}", methods=["GET", "PUT", "DELETE", "OPTIONS"])
def manage_patient(req: func.HttpRequest) -> func.HttpResponse:
    """
    Individual patient management endpoint
    GET: Get patient by ID
    PUT: Update patient
    DELETE: Delete patient
    """
    # Handle CORS preflight requests
    if req.method == "OPTIONS":
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '86400'
        }
        return func.HttpResponse("", status_code=200, headers=headers)
    
    patient_id = req.route_params.get('patient_id')
    logging.info(f'Patient {req.method}: {patient_id}')
    
    # Check if Cosmos DB is configured
    if not cosmos_manager.is_connected():
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        return func.HttpResponse(
            json.dumps({"error": "Cosmos DB not configured. Please set COSMOS_CONNECTION_STRING."}),
            status_code=500,
            mimetype="application/json",
            headers=headers
        )
    
    try:
        if req.method == "GET":
            # Get patient by ID
            try:
                response = cosmos_manager.patients_container.read_item(item=patient_id, partition_key=patient_id)
                response_data = {
                    "success": True,
                    "patient": response,
                    "message": f"Patient retrieved successfully: {patient_id}"
                }
            except Exception as e:
                if "NotFound" in str(e):
                    response_data = {
                        "success": False,
                        "error": f"Patient with ID {patient_id} not found"
                    }
                else:
                    response_data = {
                        "success": False,
                        "error": f"Failed to retrieve patient: {str(e)}"
                    }
                    
        elif req.method == "PUT":
            # Update patient
            try:
                updates = req.get_json()
                if not updates:
                    raise Exception("No update data provided")
                
                # Get existing patient first
                existing_patient = cosmos_manager.patients_container.read_item(item=patient_id, partition_key=patient_id)
                
                # Update fields
                existing_patient.update(updates)
                existing_patient['updatedAt'] = int(time.time())
                
                response = cosmos_manager.patients_container.replace_item(item=patient_id, body=existing_patient)
                response_data = {
                    "success": True,
                    "patient": response,
                    "message": f"Patient updated successfully: {patient_id}"
                }
                
            except Exception as e:
                if "NotFound" in str(e):
                    response_data = {
                        "success": False,
                        "error": f"Patient with ID {patient_id} not found"
                    }
                else:
                    response_data = {
                        "success": False,
                        "error": f"Failed to update patient: {str(e)}"
                    }
                    
        elif req.method == "DELETE":
            # Delete patient
            try:
                cosmos_manager.patients_container.delete_item(item=patient_id, partition_key=patient_id)
                response_data = {
                    "success": True,
                    "message": f"Patient deleted successfully: {patient_id}"
                }
            except Exception as e:
                if "NotFound" in str(e):
                    response_data = {
                        "success": False,
                        "error": f"Patient with ID {patient_id} not found"
                    }
                else:
                    response_data = {
                        "success": False,
                        "error": f"Failed to delete patient: {str(e)}"
                    }
        
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        status_code = 200 if response_data.get("success") else 404
        
        return func.HttpResponse(
            json.dumps(response_data),
            status_code=status_code,
            mimetype="application/json",
            headers=headers
        )
        
    except Exception as e:
        logging.error(f"Patient management error: {str(e)}")
        
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            mimetype="application/json",
            headers=headers
        )

# ================================
# APPOINTMENT MANAGEMENT ENDPOINTS
# ================================

@app.route(route="appointments", methods=["GET", "POST", "OPTIONS"])
def manage_appointments(req: func.HttpRequest) -> func.HttpResponse:
    """
    Appointment management endpoint
    GET: List appointments (optionally filtered by patient)
    POST: Create a new appointment
    """
    # Handle CORS preflight requests
    if req.method == "OPTIONS":
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '86400'
        }
        return func.HttpResponse("", status_code=200, headers=headers)
    
    logging.info(f'Appointment management: {req.method} request received')
    
    # Check if Cosmos DB is configured
    if not cosmos_manager.is_connected():
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        return func.HttpResponse(
            json.dumps({"error": "Cosmos DB not configured. Please set COSMOS_CONNECTION_STRING."}),
            status_code=500,
            mimetype="application/json",
            headers=headers
        )
    
    try:
        if req.method == "GET":
            # List appointments
            patient_id = req.params.get('patientId')
            
            try:
                if patient_id:
                    # Get appointments for specific patient
                    query = "SELECT * FROM c WHERE c.patientId = @patientId ORDER BY c.appointmentDate ASC"
                    parameters = [{"name": "@patientId", "value": patient_id}]
                    
                    items = list(cosmos_manager.appointments_container.query_items(
                        query=query,
                        parameters=parameters,
                        partition_key=patient_id
                    ))
                    message = f"Retrieved {len(items)} appointments for patient {patient_id}"
                else:
                    # Get all appointments
                    query = "SELECT * FROM c ORDER BY c.appointmentDate ASC"
                    items = list(cosmos_manager.appointments_container.query_items(
                        query=query,
                        enable_cross_partition_query=True
                    ))
                    message = f"Retrieved {len(items)} appointments"
                
                response_data = {
                    "success": True,
                    "appointments": items,
                    "count": len(items),
                    "message": message
                }
                
            except Exception as e:
                logging.error(f"Error listing appointments: {str(e)}")
                response_data = {
                    "success": False,
                    "error": f"Failed to list appointments: {str(e)}"
                }
                
        elif req.method == "POST":
            # Create appointment
            try:
                appointment_data = req.get_json()
                if not appointment_data:
                    raise Exception("No appointment data provided")
                
                # Ensure required fields
                if 'patientId' not in appointment_data:
                    raise Exception("patientId is required for appointments")
                    
                if 'id' not in appointment_data:
                    appointment_data['id'] = str(int(time.time() * 1000))  # Unique ID
                    
                # Add metadata
                appointment_data['createdAt'] = int(time.time())
                appointment_data['updatedAt'] = int(time.time())
                
                # Create appointment
                response = cosmos_manager.appointments_container.create_item(body=appointment_data)
                
                response_data = {
                    "success": True,
                    "appointment": response,
                    "message": f"Appointment created successfully with ID: {appointment_data['id']}"
                }
                
            except Exception as e:
                logging.error(f"Error creating appointment: {str(e)}")
                response_data = {
                    "success": False,
                    "error": f"Failed to create appointment: {str(e)}"
                }
        
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        status_code = 200 if response_data.get("success") else 400
        
        return func.HttpResponse(
            json.dumps(response_data),
            status_code=status_code,
            mimetype="application/json",
            headers=headers
        )
        
    except Exception as e:
        logging.error(f"Appointment management error: {str(e)}")
        
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            mimetype="application/json",
            headers=headers
        )

@app.route(route="appointments/{appointment_id}", methods=["GET", "PUT", "DELETE", "OPTIONS"])
def manage_appointment(req: func.HttpRequest) -> func.HttpResponse:
    """
    Individual appointment management endpoint
    GET: Get appointment by ID
    PUT: Update appointment
    DELETE: Delete appointment
    """
    # Handle CORS preflight requests
    if req.method == "OPTIONS":
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '86400'
        }
        return func.HttpResponse("", status_code=200, headers=headers)
    
    appointment_id = req.route_params.get('appointment_id')
    patient_id = req.params.get('patientId')  # Required for partition key
    
    logging.info(f'Appointment {req.method}: {appointment_id}, Patient: {patient_id}')
    
    # Check if Cosmos DB is configured
    if not cosmos_manager.is_connected():
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        return func.HttpResponse(
            json.dumps({"error": "Cosmos DB not configured. Please set COSMOS_CONNECTION_STRING."}),
            status_code=500,
            mimetype="application/json",
            headers=headers
        )
    
    if not patient_id:
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        return func.HttpResponse(
            json.dumps({"error": "patientId query parameter is required"}),
            status_code=400,
            mimetype="application/json",
            headers=headers
        )
    
    try:
        if req.method == "GET":
            # Get appointment by ID
            try:
                response = cosmos_manager.appointments_container.read_item(item=appointment_id, partition_key=patient_id)
                response_data = {
                    "success": True,
                    "appointment": response,
                    "message": f"Appointment retrieved successfully: {appointment_id}"
                }
            except Exception as e:
                if "NotFound" in str(e):
                    response_data = {
                        "success": False,
                        "error": f"Appointment with ID {appointment_id} not found"
                    }
                else:
                    response_data = {
                        "success": False,
                        "error": f"Failed to retrieve appointment: {str(e)}"
                    }
                    
        elif req.method == "PUT":
            # Update appointment
            try:
                updates = req.get_json()
                if not updates:
                    raise Exception("No update data provided")
                
                # Get existing appointment first
                existing_appointment = cosmos_manager.appointments_container.read_item(item=appointment_id, partition_key=patient_id)
                
                # Update fields
                existing_appointment.update(updates)
                existing_appointment['updatedAt'] = int(time.time())
                
                response = cosmos_manager.appointments_container.replace_item(item=appointment_id, body=existing_appointment)
                response_data = {
                    "success": True,
                    "appointment": response,
                    "message": f"Appointment updated successfully: {appointment_id}"
                }
                
            except Exception as e:
                if "NotFound" in str(e):
                    response_data = {
                        "success": False,
                        "error": f"Appointment with ID {appointment_id} not found"
                    }
                else:
                    response_data = {
                        "success": False,
                        "error": f"Failed to update appointment: {str(e)}"
                    }
                    
        elif req.method == "DELETE":
            # Delete appointment
            try:
                cosmos_manager.appointments_container.delete_item(item=appointment_id, partition_key=patient_id)
                response_data = {
                    "success": True,
                    "message": f"Appointment deleted successfully: {appointment_id}"
                }
            except Exception as e:
                if "NotFound" in str(e):
                    response_data = {
                        "success": False,
                        "error": f"Appointment with ID {appointment_id} not found"
                    }
                else:
                    response_data = {
                        "success": False,
                        "error": f"Failed to delete appointment: {str(e)}"
                    }
        
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        status_code = 200 if response_data.get("success") else 404
        
        return func.HttpResponse(
            json.dumps(response_data),
            status_code=status_code,
            mimetype="application/json",
            headers=headers
        )
        
    except Exception as e:
        logging.error(f"Appointment management error: {str(e)}")
        
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            mimetype="application/json",
            headers=headers
        )

@app.route(route="MakePhoneCall", methods=["GET", "POST"])
def MakePhoneCall(req: func.HttpRequest) -> func.HttpResponse:
    """
    Create a call to a phone number (PSTN) with configurable target number
    Supports custom message, voice, and phone number via API parameters
    """
    logging.info('MakePhoneCall: Request to make PSTN call to phone number')
    
    # --- Input Validation ---
    if not all([ACS_CONNECTION_STRING, COGNITIVE_SERVICES_ENDPOINT]):
        logging.error("Missing required configuration. Check Application Settings for ACS_CONNECTION_STRING and COGNITIVE_SERVICES_ENDPOINT.")
        return func.HttpResponse(
             "Server configuration error: Missing required ACS settings.",
             status_code=500
        )
    
    if not SOURCE_CALLER_ID:
        logging.error("Missing SOURCE_CALLER_ID configuration. This is required for PSTN calls.")
        return func.HttpResponse(
             "Server configuration error: SOURCE_CALLER_ID is required for PSTN calls. Please set SOURCE_CALLER_ID or ACS_PHONE_NUMBER environment variable.",
             status_code=500
        )
 
    try:
        # Get parameters from query string or request body
        target_phone = req.params.get('phoneNumber') or req.params.get('phone')
        custom_message = req.params.get('message')
        custom_voice = req.params.get('voice')
        delay_seconds = req.params.get('delay', '3')  # Default 3 seconds for PSTN
        
        # Check if parameters were provided in request body (for POST requests)
        if req.method == "POST":
            try:
                req_body = req.get_json()
                if req_body:
                    target_phone = target_phone or req_body.get('phoneNumber') or req_body.get('phone')
                    custom_message = custom_message or req_body.get('message')
                    custom_voice = custom_voice or req_body.get('voice')
                    delay_seconds = req_body.get('delay', delay_seconds)
            except ValueError:
                pass
        
        # Use provided phone number or default from environment
        if not target_phone:
            target_phone = TARGET_PHONE_NUMBER
            
        if not target_phone:
            return func.HttpResponse(
                json.dumps({
                    "error": "Phone number is required. Provide via 'phoneNumber' parameter or set TARGET_PHONE_NUMBER environment variable.",
                    "example": "?phoneNumber=+917447474405"
                }),
                status_code=400,
                mimetype="application/json"
            )
        
        # Validate phone number format (basic validation)
        if not target_phone.startswith('+'):
            return func.HttpResponse(
                json.dumps({
                    "error": "Phone number must be in international format starting with '+' (e.g., +917447474405)",
                    "provided": target_phone
                }),
                status_code=400,
                mimetype="application/json"
            )
        
        # Parse delay
        try:
            delay_seconds = int(delay_seconds)
            if delay_seconds < 0 or delay_seconds > 30:
                delay_seconds = 3  # Default to 3 seconds if invalid
        except ValueError:
            delay_seconds = 3
        
        # --- Initialize Clients ---
        logging.info("MakePhoneCall: Initializing CallAutomationClient for PSTN calling")
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
       
        # Create PhoneNumberIdentifier for PSTN calling
        target_phone_user = PhoneNumberIdentifier(target_phone)
        source_caller_id = PhoneNumberIdentifier(SOURCE_CALLER_ID)
        
        logging.info(f"MakePhoneCall: Target phone number: {target_phone}")
        logging.info(f"MakePhoneCall: Source caller ID: {SOURCE_CALLER_ID}")
       
        # Store custom settings for webhook (in production, use proper storage)
        global TEMP_CUSTOM_MESSAGE, TEMP_CUSTOM_VOICE
        TEMP_CUSTOM_MESSAGE = custom_message or WELCOME_MESSAGE
        TEMP_CUSTOM_VOICE = custom_voice or TTS_VOICE
        
        # Use the webhook with auto TTS for PSTN calls
        callback_uri = f"https://{CALLBACK_URL_BASE}/api/PhoneCallWebhook"
        
        # For local testing, use localhost
        if 'localhost' in req.url or '127.0.0.1' in req.url:
            callback_uri = f"http://localhost:7071/api/PhoneCallWebhook"
            
        logging.info(f"MakePhoneCall: Using callback URI: {callback_uri}")
        
        # --- Create the PSTN Call ---
        logging.info(f"MakePhoneCall: Creating PSTN call to phone number: {target_phone}")
        
        try:
            # For PSTN calls, pass the source caller ID directly to create_call
            call_result = client.create_call(
                target_participant=target_phone_user,
                callback_url=callback_uri,
                cognitive_services_endpoint=COGNITIVE_SERVICES_ENDPOINT,
                source_caller_id_number=source_caller_id
            )
        except Exception as call_error:
            logging.error(f"MakePhoneCall: PSTN call creation failed: {call_error}")
            return func.HttpResponse(
                json.dumps({
                    "error": f"Failed to create PSTN call: {str(call_error)}",
                    "phoneNumber": target_phone,
                    "troubleshooting": "Check that your ACS resource has PSTN calling enabled and proper phone number provisioning"
                }),
                status_code=500,
                mimetype="application/json"
            )
        
        call_connection_id = call_result.call_connection_id if hasattr(call_result, 'call_connection_id') else 'Unknown'
        logging.info(f"MakePhoneCall: PSTN call created with ID: {call_connection_id}")
        
        # Add CORS headers
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        response_data = {
            "success": True,
            "message": "PSTN call initiated successfully",
            "callId": call_connection_id,
            "phoneNumber": target_phone,
            "ttsMessage": TEMP_CUSTOM_MESSAGE[:100] + "..." if len(TEMP_CUSTOM_MESSAGE) > 100 else TEMP_CUSTOM_MESSAGE,
            "voice": TEMP_CUSTOM_VOICE,
            "webhookUrl": callback_uri,
            "delay": delay_seconds,
            "callType": "PSTN"
        }
        
        logging.info(f"MakePhoneCall: Successfully initiated PSTN call to {target_phone}. Call ID: {call_connection_id}")
        
        return func.HttpResponse(
            json.dumps(response_data),
            status_code=200,
            mimetype="application/json",
            headers=headers
        )
        
    except Exception as e:
        logging.error(f"MakePhoneCall: Error: {str(e)}")
        
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        return func.HttpResponse(
            json.dumps({
                "error": f"Failed to create PSTN call: {str(e)}",
                "callType": "PSTN"
            }),
            status_code=500,
            mimetype="application/json",
            headers=headers
        )

@app.route(route="GetCallStatus", methods=["GET"])
def GetCallStatus(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get the status of a call by call ID
    """
    logging.info('GetCallStatus: Request to get call status')
    
    try:
        # Get call ID from query params
        call_id = req.params.get('callId')
        
        if not call_id:
            return func.HttpResponse(
                json.dumps({"error": "callId parameter is required"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Initialize the CallAutomationClient
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
        
        try:
            # Get the call connection to check status
            call_connection = client.get_call_connection(call_id)
            
            # The call exists, so it's either active or recently completed
            # Note: ACS doesn't provide detailed status info via get_call_connection
            response_data = {
                "callId": call_id,
                "status": "active_or_recent",
                "message": "Call connection exists and is active or was recently active"
            }
            
        except Exception as status_error:
            # If we can't get the call connection, it might be disconnected or invalid
            response_data = {
                "callId": call_id,
                "status": "disconnected_or_invalid",
                "message": f"Unable to retrieve call connection: {str(status_error)}"
            }
        
        # Add CORS headers
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        return func.HttpResponse(
            json.dumps(response_data),
            status_code=200,
            mimetype="application/json",
            headers=headers
        )
        
    except Exception as e:
        logging.error(f"GetCallStatus: Error: {str(e)}")
        
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        return func.HttpResponse(
            json.dumps({"error": f"Failed to get call status: {str(e)}"}),
            status_code=500,
            mimetype="application/json",
            headers=headers
        )

@app.route(route="PhoneCallWebhook", methods=["POST"])
def PhoneCallWebhook(req: func.HttpRequest) -> func.HttpResponse:
    """
    Webhook endpoint specifically for PSTN phone calls
    Handles call events and plays TTS messages when the phone call connects
    """
    global TEMP_CUSTOM_MESSAGE, TEMP_CUSTOM_VOICE
    logging.info('PhoneCallWebhook: Received PSTN call event')
    
    try:
        # Get the event data
        event_data = req.get_body().decode('utf-8')
        logging.info(f"PhoneCallWebhook: Raw event data: {event_data}")
        
        # Parse the JSON event
        events = json.loads(event_data)
        if not isinstance(events, list):
            events = [events]
        
        # Initialize the CallAutomationClient for handling events
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
        
        for event in events:
            event_type = event.get('type', 'Unknown')
            call_connection_id = event.get('data', {}).get('callConnectionId', 'Unknown')
            
            logging.info(f"PhoneCallWebhook: Processing PSTN event type: {event_type}, Call ID: {call_connection_id}")
            
            # Handle CallConnected event - this is when we play the message
            if event_type == 'Microsoft.Communication.CallConnected':
                logging.info(f"PhoneCallWebhook: PSTN call connected! Playing TTS message...")
                
                try:
                    # Get call connection
                    call_connection = client.get_call_connection(call_connection_id)
                    
                    # Use stored custom message and voice, or defaults
                    message_to_play = TEMP_CUSTOM_MESSAGE or WELCOME_MESSAGE
                    voice_to_use = TEMP_CUSTOM_VOICE or TTS_VOICE
                    
                    # Create text source for TTS
                    text_source = TextSource(
                        text=message_to_play,
                        voice_name=voice_to_use
                    )
                    
                    logging.info(f"PhoneCallWebhook: Playing message: '{message_to_play[:50]}...', Voice: {voice_to_use}")
                    
                    # Play the message to all participants (the phone call recipient)
                    play_result = call_connection.play_media(
                        play_source=text_source,
                        play_to="all"  # For PSTN calls, use "all" to play to all participants
                    )
                    
                    operation_id = getattr(play_result, 'operation_id', 'Unknown')
                    logging.info(f"PhoneCallWebhook: TTS playback initiated for PSTN call. Operation ID: {operation_id}")
                    
                    # Clear temp variables after use
                    TEMP_CUSTOM_MESSAGE = None
                    TEMP_CUSTOM_VOICE = None
                    
                except Exception as play_error:
                    logging.error(f"PhoneCallWebhook: Error playing TTS on PSTN call: {str(play_error)}")
                
            elif event_type == 'Microsoft.Communication.CallDisconnected':
                disconnect_reason = event.get('data', {}).get('callConnectionId', 'Unknown reason')
                logging.info(f"PhoneCallWebhook: PSTN call disconnected. Call ID: {call_connection_id}, Reason: {disconnect_reason}")
                
                # Clear temp variables on disconnect
                TEMP_CUSTOM_MESSAGE = None
                TEMP_CUSTOM_VOICE = None
                
            elif event_type == 'Microsoft.Communication.PlayCompleted':
                logging.info(f"PhoneCallWebhook: TTS playback completed for PSTN call {call_connection_id}")
                
            elif event_type == 'Microsoft.Communication.PlayFailed':
                play_error = event.get('data', {}).get('resultInformation', {}).get('message', 'Unknown error')
                logging.error(f"PhoneCallWebhook: TTS playback failed for PSTN call {call_connection_id}: {play_error}")
                
            elif event_type == 'Microsoft.Communication.CallEstablished':
                logging.info(f"PhoneCallWebhook: PSTN call established for call {call_connection_id}")
                
            elif event_type == 'Microsoft.Communication.ParticipantsUpdated':
                participants = event.get('data', {}).get('participants', [])
                logging.info(f"PhoneCallWebhook: Participants updated for PSTN call {call_connection_id}, count: {len(participants)}")
                
            else:
                logging.info(f"PhoneCallWebhook: Unhandled PSTN event type: {event_type}")
        
        # Return success response
        return func.HttpResponse(
            "PSTN webhook processed successfully",
            status_code=200
        )
        
    except json.JSONDecodeError as json_error:
        logging.error(f"PhoneCallWebhook: Invalid JSON in request body: {str(json_error)}")
        return func.HttpResponse(
            "Invalid JSON in request body",
            status_code=400
        )
        
    except Exception as e:
        logging.error(f"PhoneCallWebhook: Error processing PSTN webhook: {str(e)}")
        return func.HttpResponse(
            f"Error processing PSTN webhook: {str(e)}",
            status_code=500
        )
