import azure.functions as func
import logging
import os
import json

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

# Your connection string from ACS, stored securely
ACS_CONNECTION_STRING = os.environ.get("ACS_CONNECTION_STRING", "endpoint=https://healthcareagent-comms.unitedstates.communication.azure.com/;accesskey=FfQcj4nwjlzvM5sMwxzw0le8473TMsywMGLgomBcDtCvoDfONAbUJQQJ99BGACULyCpYBcwtAAAAAZCS3t8U")

# Cognitive Services endpoint for TTS functionality (required for media operations)
# For Global ACS resources, use a global or US endpoint
COGNITIVE_SERVICES_ENDPOINT = os.environ.get("COGNITIVE_SERVICES_ENDPOINT", "https://healthcareagent-cognitiveserv-ng.cognitiveservices.azure.com/").rstrip('/')
 
# The User Identity you generated (the one starting with 8:acs:...)
TARGET_USER_ID = os.environ.get("TARGET_USER_ID", "8:acs:a40c5c9d-178f-4629-b90d-4c48e852facf_00000028-7088-6a5f-6a0b-343a0d004313")
 
# The callback URL for your function, so ACS can send back events
CALLBACK_URL_BASE = os.environ.get("CALLBACK_URL_BASE", "healthcareagent-functions-ng1.azurewebsites.net")

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
        connection_string = os.environ.get("ACS_CONNECTION_STRING", "endpoint=https://healthcareagent-comms.unitedstates.communication.azure.com/;accesskey=FfQcj4nwjlzvM5sMwxzw0le8473TMsywMGLgomBcDtCvoDfONAbUJQQJ99BGACULyCpYBcwtAAAAAZCS3t8U")
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
            user_id = os.environ.get("TARGET_USER_ID", "8:acs:a40c5c9d-178f-4629-b90d-4c48e852facf_00000028-7088-6a5f-6a0b-343a0d004313")
        
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

@app.route(route="TestMessage", methods=["GET"])
def TestMessage(req: func.HttpRequest) -> func.HttpResponse:
    """
    Test endpoint to check the configured welcome message and voice settings
    Also shows available endpoints for different call scenarios
    """
    logging.info('TestMessage endpoint called')
    
    try:
        response_data = {
            "welcomeMessage": WELCOME_MESSAGE,
            "ttsVoice": TTS_VOICE,
            "targetUserId": TARGET_USER_ID[:20] + "..." if len(TARGET_USER_ID) > 20 else TARGET_USER_ID,
            "cognitiveServicesEndpoint": COGNITIVE_SERVICES_ENDPOINT,
            "availableEndpoints": {
                "MakeTestCall": {
                    "description": "Creates a direct call to web client (no automatic TTS)",
                    "usage": "/api/MakeTestCall",
                    "note": "Call reaches web client immediately. Use /PlayMessage after answering."
                },
                "MakeTestCallNoWebhook": {
                    "description": "Creates call and plays TTS after delay (NO WEBHOOK - MOST RELIABLE)",
                    "usage": "/api/MakeTestCallNoWebhook?delay=8&message=Custom message&voice=en-US-AriaNeural",
                    "note": "Best option for client connectivity. No webhook dependencies.",
                    "parameters": {
                        "delay": "Seconds to wait before playing TTS (default: 8)",
                        "message": "Custom message to play (optional)",
                        "voice": "Custom voice to use (optional)"
                    }
                },
                "MakeTestCallWithAutoTTS": {
                    "description": "Creates call and plays TTS after delay using threading (WITH WEBHOOK)",
                    "usage": "/api/MakeTestCallWithAutoTTS?delay=5&message=Custom message&voice=en-US-AriaNeural",
                    "note": "Uses webhook which may prevent client connection in some cases.",
                    "parameters": {
                        "delay": "Seconds to wait before playing TTS (default: 5)",
                        "message": "Custom message to play (optional)",
                        "voice": "Custom voice to use (optional)"
                    }
                },
                "MakeTestCallWithWebhookTTS": {
                    "description": "Creates call and plays TTS via webhook when call connects",
                    "usage": "/api/MakeTestCallWithWebhookTTS",
                    "note": "Webhook approach - may block client connection if webhook fails.",
                    "parameters": {
                        "message": "Custom message to play (optional)",
                        "voice": "Custom voice to use (optional)"
                    }
                },
                "PlayMessage": {
                    "description": "Play TTS on an existing active call",
                    "usage": "/api/PlayMessage?callId=YOUR_CALL_ID&message=Custom message&voice=en-US-AriaNeural",
                    "parameters": {
                        "callId": "Required - Call ID from MakeTestCall response",
                        "message": "Custom message to play (optional)",
                        "voice": "Custom voice to use (optional)"
                    }
                },
                "GetToken": {
                    "description": "Get ACS authentication token for web client",
                    "usage": "/api/GetToken"
                },
                "TestMessage": {
                    "description": "View current configuration and available endpoints",
                    "usage": "/api/TestMessage"
                }
            },
            "recommendedFlow": {
                "step1": "Use MakeTestCallNoWebhook for best client connectivity",
                "step2": "Alternative: Use MakeTestCall + answer call + PlayMessage for manual control",
                "step3": "Avoid webhook-based endpoints if client connection is unreliable"
            }
        }
        
        # Add CORS headers
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        return func.HttpResponse(
            json.dumps(response_data, indent=2),
            status_code=200,
            mimetype="application/json",
            headers=headers
        )
        
    except Exception as e:
        logging.error(f"Error in TestMessage: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
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

def CallWebhook(req: func.HttpRequest) -> func.HttpResponse:
    """
    Basic webhook endpoint to handle call events
    This is used by MakeTestCall for basic call flow without automatic TTS
    """
    logging.info('CallWebhook: Received call event')
    
    try:
        # Get the event data
        event_data = req.get_body().decode('utf-8')
        logging.info(f"CallWebhook: Raw event data: {event_data}")
        
        # Parse the JSON event
        events = json.loads(event_data)
        if not isinstance(events, list):
            events = [events]
        
        for event in events:
            event_type = event.get('type', 'Unknown')
            call_connection_id = event.get('data', {}).get('callConnectionId', 'Unknown')
            
            logging.info(f"CallWebhook: Processing event type: {event_type}, Call ID: {call_connection_id}")
            
            # Log different event types
            if event_type == 'Microsoft.Communication.CallConnected':
                logging.info(f"CallWebhook: Call connected! Call ID: {call_connection_id}")
            elif event_type == 'Microsoft.Communication.CallDisconnected':
                logging.info(f"CallWebhook: Call disconnected")
            elif event_type == 'Microsoft.Communication.PlayCompleted':
                logging.info(f"CallWebhook: Play operation completed")
            elif event_type == 'Microsoft.Communication.PlayFailed':
                logging.warning(f"CallWebhook: Play operation failed")
            else:
                logging.info(f"CallWebhook: Received event type: {event_type}")
        
        return func.HttpResponse(
            "Webhook processed successfully",
            status_code=200
        )
        
    except json.JSONDecodeError as json_error:
        logging.error(f"CallWebhook: Invalid JSON in request body: {str(json_error)}")
        return func.HttpResponse(
            "Invalid JSON in request body",
            status_code=400
        )
        
    except Exception as e:
        logging.error(f"CallWebhook: Error processing webhook: {str(e)}")
        return func.HttpResponse(
            f"Error processing webhook: {str(e)}",
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

@app.route(route="DebugConfig", methods=["GET"])
def DebugConfig(req: func.HttpRequest) -> func.HttpResponse:
    """
    Debug endpoint to check all configuration values
    """
    logging.info('DebugConfig: Configuration check requested')
    
    try:
        config_info = {
            "acsConnectionString": {
                "configured": bool(ACS_CONNECTION_STRING),
                "endpoint": ACS_CONNECTION_STRING.split(';')[0] if ACS_CONNECTION_STRING else "Not configured",
                "length": len(ACS_CONNECTION_STRING) if ACS_CONNECTION_STRING else 0
            },
            "cognitiveServicesEndpoint": {
                "configured": bool(COGNITIVE_SERVICES_ENDPOINT),
                "value": COGNITIVE_SERVICES_ENDPOINT,
                "isEastUS2": "eastus2" in COGNITIVE_SERVICES_ENDPOINT.lower() if COGNITIVE_SERVICES_ENDPOINT else False
            },
            "targetUserId": {
                "configured": bool(TARGET_USER_ID),
                "value": TARGET_USER_ID[:20] + "..." if len(TARGET_USER_ID) > 20 else TARGET_USER_ID
            },
            "callbackUrlBase": {
                "configured": bool(CALLBACK_URL_BASE),
                "value": CALLBACK_URL_BASE
            },
            "ttsSettings": {
                "welcomeMessage": WELCOME_MESSAGE[:50] + "..." if len(WELCOME_MESSAGE) > 50 else WELCOME_MESSAGE,
                "voice": TTS_VOICE
            },
            "environmentVariables": {
                "AZURE_FUNCTIONS_ENVIRONMENT": os.environ.get('AZURE_FUNCTIONS_ENVIRONMENT', 'Not set'),
                "FUNCTIONS_WORKER_RUNTIME": os.environ.get('FUNCTIONS_WORKER_RUNTIME', 'Not set')
            }
        }
        
        # Add CORS headers
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        return func.HttpResponse(
            json.dumps(config_info, indent=2),
            status_code=200,
            mimetype="application/json",
            headers=headers
        )
        
    except Exception as e:
        logging.error(f"DebugConfig: Error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )

@app.route(route="TestCognitiveServices", methods=["GET"])
def TestCognitiveServices(req: func.HttpRequest) -> func.HttpResponse:
    """
    Test endpoint to verify Cognitive Services configuration
    """
    logging.info('TestCognitiveServices: Testing Cognitive Services configuration')
    
    try:
        # Test different endpoint formats
        test_endpoints = [
            COGNITIVE_SERVICES_ENDPOINT,
            COGNITIVE_SERVICES_ENDPOINT.rstrip('/'),
            f"{COGNITIVE_SERVICES_ENDPOINT.rstrip('/')}/",
            "https://eastus2.api.cognitive.microsoft.com",
            "https://eastus2.api.cognitive.microsoft.com/"
        ]
        
        # Get ACS resource location for comparison
        acs_endpoint = ACS_CONNECTION_STRING.split(';')[0].replace('endpoint=', '') if ACS_CONNECTION_STRING else ""
        
        test_results = {
            "currentCognitiveServicesEndpoint": COGNITIVE_SERVICES_ENDPOINT,
            "acsEndpoint": acs_endpoint,
            "acsRegion": "unitedstates" if "unitedstates" in acs_endpoint else "unknown",
            "cognitiveServicesRegion": "eastus2" if "eastus2" in COGNITIVE_SERVICES_ENDPOINT else "unknown",
            "regionMismatch": ("unitedstates" in acs_endpoint and "eastus2" in COGNITIVE_SERVICES_ENDPOINT),
            "endpointFormats": test_endpoints,
            "voice": TTS_VOICE,
            "recommendations": []
        }
        
        # Add recommendations based on analysis
        if test_results["regionMismatch"]:
            test_results["recommendations"].append("CRITICAL: Region mismatch detected. ACS is in 'unitedstates' but Cognitive Services is in 'eastus2'. This may cause the bad request error.")
        
        if COGNITIVE_SERVICES_ENDPOINT.endswith('/'):
            test_results["recommendations"].append("Remove trailing slash from Cognitive Services endpoint")
            
        if "eastus2" not in COGNITIVE_SERVICES_ENDPOINT:
            test_results["recommendations"].append("Verify Cognitive Services is in East US 2 region")
            
        # Check if voice is valid
        valid_voices = ["en-US-JennyNeural", "en-US-AriaNeural", "en-US-DavisNeural", "en-US-AmberNeural"]
        if TTS_VOICE not in valid_voices:
            test_results["recommendations"].append(f"Voice '{TTS_VOICE}' may not be valid. Try: {', '.join(valid_voices)}")
        
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        }
        
        return func.HttpResponse(
            json.dumps(test_results, indent=2),
            status_code=200,
            mimetype="application/json",
            headers=headers
        )
        
    except Exception as e:
        logging.error(f"TestCognitiveServices: Error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
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

@app.route(route="TestWebhook", methods=["GET", "POST"])
def TestWebhook(req: func.HttpRequest) -> func.HttpResponse:
    """
    Test endpoint to verify webhook connectivity and behavior
    """
    if req.method == "GET":
        response_data = {
            "webhookTestInfo": {
                "basicWebhook": f"https://{CALLBACK_URL_BASE}/api/CallWebhook",
                "autoTTSWebhook": f"https://{CALLBACK_URL_BASE}/api/CallWebhookWithAutoTTS",
                "localWebhook": "http://localhost:7071/api/CallWebhook"
            },
            "webhookIssues": {
                "description": "Webhooks can prevent client connections if they fail",
                "commonProblems": [
                    "Webhook URL not publicly accessible",
                    "Webhook returning errors or timing out"
                ],
                "solutions": [
                    "Use MakeTestCallNoWebhook for best reliability"
                ]
            }
        }
    else:
        logging.info('TestWebhook: Simulating webhook POST request')
        try:
            event_data = req.get_body().decode('utf-8')
            response_data = {
                "success": True,
                "message": "Webhook test successful",
                "receivedData": event_data[:200] + "..." if len(event_data) > 200 else event_data
            }
        except Exception as e:
            response_data = {
                "success": False,
                "error": str(e)
            }
    
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type'
    }
    
    return func.HttpResponse(
        json.dumps(response_data, indent=2),
        status_code=200,
        mimetype="application/json",
        headers=headers
    )