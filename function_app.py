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

# Temporary variables for webhook-based custom TTS (in production, use proper storage)
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
                    enable_cross_partition_query=True
                ))
                
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

# ================================
