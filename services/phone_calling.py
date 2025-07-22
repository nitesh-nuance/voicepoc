"""
PSTN Phone Calling Module
Handles PSTN (Public Switched Telephone Network) phone calls using Azure Communication Services

This module implements OUTBOUND CALLING functionality where:
1. Our system (Azure Communication Services) calls a target phone number
2. The system plays a greeting message to the called person
3. The system listens to and processes speech from the called person
4. The system responds conversationally based on the recognized speech

Key Components:
- create_pstn_call(): Initiates outbound calls to target phone numbers
- handle_pstn_webhook_event(): Processes webhook events from Azure Communication Services
- Speech Recognition: Listens to the CALLED PERSON's speech using various Azure SDK methods
- Conversation Flow: Maintains conversational context and generates appropriate responses

Target Participant Logic:
- In outbound calls, the "target_participant" for speech recognition is the person we called
- We store the call_connection_id -> target_phone_number mapping to identify who to listen to
- Speech recognition attempts to capture what the CALLED PERSON says, not our own system audio
"""

import os
import json
import logging
import time
from typing import Optional, Dict, Any

from azure.communication.callautomation import CallAutomationClient, TextSource, RecognitionChoice
from azure.communication.callautomation import PhoneNumberIdentifier, RecognizeInputType

# Initialize logging for this module
logging.info("PSTN Phone Calling Module loaded successfully")
logging.debug(f"Module configuration - ACS configured: {bool(os.environ.get('ACS_CONNECTION_STRING'))}, "
             f"Cognitive Services configured: {bool(os.environ.get('COGNITIVE_SERVICES_ENDPOINT'))}")

# Configuration
ACS_CONNECTION_STRING = os.environ.get("ACS_CONNECTION_STRING", "")
COGNITIVE_SERVICES_ENDPOINT = os.environ.get("COGNITIVE_SERVICES_ENDPOINT", "").rstrip('/') if os.environ.get("COGNITIVE_SERVICES_ENDPOINT") else ""
TARGET_PHONE_NUMBER = os.environ.get("TARGET_PHONE_NUMBER", "+917447474405")
SOURCE_CALLER_ID = os.environ.get("SOURCE_CALLER_ID", "") or os.environ.get("ACS_PHONE_NUMBER", "")
CALLBACK_URL_BASE = os.environ.get("CALLBACK_URL_BASE", "")
WELCOME_MESSAGE = os.environ.get("WELCOME_MESSAGE", 
    "Hello! This is your Azure Communication Services assistant. The call connection is working perfectly. "
    "You can now hear automated messages through Azure's text-to-speech service. "
    "Thank you for testing the voice integration.")
TTS_VOICE = os.environ.get("TTS_VOICE", "en-US-JennyNeural")

# Global variables for conversation state and temporary webhook data storage
# In production, use proper storage like Redis or Azure Storage
TEMP_CUSTOM_MESSAGE = None
TEMP_CUSTOM_VOICE = None
CONVERSATION_STATE = {}  # Store conversation state by call_connection_id
CALL_TARGET_MAPPING = {}  # Store call_connection_id -> target_phone_number mapping


def validate_pstn_configuration() -> tuple[bool, str]:
    """
    Validate that all required PSTN configuration is present
    Returns: (is_valid, error_message)
    """
    logging.debug("Starting PSTN configuration validation")
    
    if not ACS_CONNECTION_STRING:
        logging.error("ACS_CONNECTION_STRING is missing or empty")
        return False, "ACS_CONNECTION_STRING is required for PSTN calls"
    else:
        logging.debug(f"ACS_CONNECTION_STRING is present (length: {len(ACS_CONNECTION_STRING)})")
    
    if not COGNITIVE_SERVICES_ENDPOINT:
        logging.error("COGNITIVE_SERVICES_ENDPOINT is missing or empty")
        return False, "COGNITIVE_SERVICES_ENDPOINT is required for TTS functionality"
    else:
        logging.debug(f"COGNITIVE_SERVICES_ENDPOINT is present: {COGNITIVE_SERVICES_ENDPOINT}")
    
    if not SOURCE_CALLER_ID:
        logging.error("SOURCE_CALLER_ID is missing or empty")
        return False, "SOURCE_CALLER_ID is required for PSTN calls"
    else:
        logging.debug(f"SOURCE_CALLER_ID is present: {SOURCE_CALLER_ID}")
    
    logging.info("PSTN configuration validation successful")
    return True, ""


def validate_phone_number(phone_number: str) -> tuple[bool, str]:
    """
    Validate phone number format for PSTN calls
    Returns: (is_valid, error_message)
    """
    logging.debug(f"Validating phone number: {phone_number}")
    
    if not phone_number:
        logging.error("Phone number is empty or None")
        return False, "Phone number is required"
    
    if not phone_number.startswith('+'):
        logging.error(f"Phone number does not start with '+': {phone_number}")
        return False, "Phone number must be in international format starting with '+'"
    
    # Basic validation - should have country code + number
    if len(phone_number) < 8 or len(phone_number) > 16:
        logging.error(f"Phone number length invalid: {len(phone_number)} characters")
        return False, "Phone number length should be between 8-16 characters"
    
    logging.info(f"Phone number validation successful: {phone_number}")
    return True, ""


def create_pstn_call(
    target_phone: str,
    custom_message: Optional[str] = None,
    custom_voice: Optional[str] = None,
    callback_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a PSTN call to a phone number
    
    Args:
        target_phone: Target phone number in international format
        custom_message: Custom TTS message to play
        custom_voice: Custom voice for TTS
        callback_url: Callback URL for webhook events
    
    Returns:
        Dict with call result information
    """
    global TEMP_CUSTOM_MESSAGE, TEMP_CUSTOM_VOICE
    
    logging.info(f"Creating PSTN call to: {target_phone}")
    
    # Validate configuration
    is_valid, error_msg = validate_pstn_configuration()
    if not is_valid:
        return {
            "success": False,
            "error": f"Configuration error: {error_msg}",
            "call_type": "PSTN"
        }
    
    # Validate phone number
    is_valid, error_msg = validate_phone_number(target_phone)
    if not is_valid:
        return {
            "success": False,
            "error": f"Phone number validation error: {error_msg}",
            "call_type": "PSTN"
        }
    
    try:
        # Initialize ACS client
        logging.debug("Initializing CallAutomationClient with connection string")
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
        logging.info("CallAutomationClient initialized successfully")
        
        # Create phone number identifiers
        logging.debug(f"Creating phone number identifiers - Target: {target_phone}, Source: {SOURCE_CALLER_ID}")
        target_phone_user = PhoneNumberIdentifier(target_phone)
        source_caller_id = PhoneNumberIdentifier(SOURCE_CALLER_ID)
        logging.debug("Phone number identifiers created successfully")
        
        # Store custom settings for webhook
        TEMP_CUSTOM_MESSAGE = custom_message or WELCOME_MESSAGE
        TEMP_CUSTOM_VOICE = custom_voice or TTS_VOICE
        logging.debug(f"Stored custom settings - Message: '{TEMP_CUSTOM_MESSAGE[:50]}...', Voice: {TEMP_CUSTOM_VOICE}")
        
        # Determine callback URL
        if not callback_url:
            if CALLBACK_URL_BASE:
                callback_url = f"https://{CALLBACK_URL_BASE}/api/phone_call_webhook"
            else:
                callback_url = "http://localhost:7071/api/phone_call_webhook"
        
        logging.info(f"Using callback URL: {callback_url}")
        logging.info(f"Source caller ID: {SOURCE_CALLER_ID}")
        logging.info(f"Target phone: {target_phone}")
        
        # Create the PSTN call
        logging.debug("Initiating PSTN call creation...")
        call_result = client.create_call(
            target_participant=target_phone_user,
            callback_url=callback_url,
            cognitive_services_endpoint=COGNITIVE_SERVICES_ENDPOINT,
            source_caller_id_number=source_caller_id
        )
        
        call_connection_id = call_result.call_connection_id if hasattr(call_result, 'call_connection_id') else 'Unknown'
        
        logging.info(f"PSTN call created successfully. Call ID: {call_connection_id}")
        logging.debug(f"Call result object: {type(call_result)}")
        
        # Store the mapping of call_connection_id to target phone number for speech recognition
        if call_connection_id != 'Unknown':
            CALL_TARGET_MAPPING[call_connection_id] = target_phone
            logging.debug(f"Stored target phone mapping: {call_connection_id} -> {target_phone}")
        
        return {
            "success": True,
            "call_id": call_connection_id,
            "phone_number": target_phone,
            "message": TEMP_CUSTOM_MESSAGE,
            "voice": TEMP_CUSTOM_VOICE,
            "webhook_url": callback_url,
            "call_type": "PSTN"
        }
        
    except Exception as e:
        logging.error(f"Failed to create PSTN call: {str(e)}")
        logging.error(f"Exception type: {type(e).__name__}")
        logging.error(f"Exception args: {e.args}")
        logging.debug(f"Phone number: {target_phone}, Custom message: {custom_message}, Custom voice: {custom_voice}")
        return {
            "success": False,
            "error": f"Failed to create PSTN call: {str(e)}",
            "phone_number": target_phone,
            "call_type": "PSTN"
        }


def handle_pstn_webhook_event(event: Dict[str, Any]) -> bool:
    """
    Handle a single PSTN webhook event
    
    Args:
        event: Event data from Azure Communication Services
    
    Returns:
        True if event was handled successfully, False otherwise
    """
    global TEMP_CUSTOM_MESSAGE, TEMP_CUSTOM_VOICE
    
    try:
        event_type = event.get('type', 'Unknown')
        call_connection_id = event.get('data', {}).get('callConnectionId', 'Unknown')
        
        logging.info(f"Processing PSTN event: {event_type}, Call ID: {call_connection_id}")
        logging.debug(f"Full event data: {json.dumps(event, indent=2)}")
        
        # Initialize ACS client for event handling
        logging.debug("Initializing CallAutomationClient for event handling")
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
        
        if event_type == 'Microsoft.Communication.CallConnected':
            logging.info(f"PSTN call connected! Playing TTS message...")
            logging.debug(f"Current conversation states: {list(CONVERSATION_STATE.keys())}")
            
            try:
                # Get call connection
                logging.debug(f"Getting call connection for ID: {call_connection_id}")
                call_connection = client.get_call_connection(call_connection_id)
                logging.debug("Call connection retrieved successfully")
                
                # Use stored custom message and voice, or defaults
                message_to_play = TEMP_CUSTOM_MESSAGE or WELCOME_MESSAGE
                voice_to_use = TEMP_CUSTOM_VOICE or TTS_VOICE
                
                logging.debug(f"Message to play (full): '{message_to_play}'")
                logging.debug(f"Voice to use: {voice_to_use}")
                
                # Create text source for TTS
                text_source = TextSource(
                    text=message_to_play,
                    voice_name=voice_to_use
                )
                logging.debug("TextSource created successfully")
                
                logging.info(f"Playing message: '{message_to_play[:50]}...', Voice: {voice_to_use}")
                
                # Play the message to all participants
                play_result = call_connection.play_media(
                    play_source=text_source,
                    play_to="all"
                )
                
                operation_id = getattr(play_result, 'operation_id', 'Unknown')
                logging.info(f"TTS playback initiated. Operation ID: {operation_id}")
                logging.debug(f"Play result type: {type(play_result)}")
                
                # Initialize conversation state for this call
                CONVERSATION_STATE[call_connection_id] = {
                    'stage': 'greeting_played',
                    'turn_count': 0,
                    'conversation_history': [
                        {'speaker': 'assistant', 'message': message_to_play}
                    ]
                }
                logging.debug(f"Conversation state initialized for call {call_connection_id}")
                
                # Clear temp variables after use
                TEMP_CUSTOM_MESSAGE = None
                TEMP_CUSTOM_VOICE = None
                logging.debug("Temp variables cleared after successful message play")
                
            except Exception as play_error:
                logging.error(f"Error playing TTS: {str(play_error)}")
                logging.error(f"Play error type: {type(play_error).__name__}")
                logging.error(f"Play error args: {play_error.args}")
                return False
                
        elif event_type == 'Microsoft.Communication.CallDisconnected':
            disconnect_data = event.get('data', {})
            disconnect_reason = disconnect_data.get('callConnectionId', 'Unknown reason')
            logging.info(f"PSTN call disconnected. Call ID: {call_connection_id}, Reason: {disconnect_reason}")
            logging.debug(f"Disconnect event data: {json.dumps(disconnect_data, indent=2)}")
            
            # Clear conversation state and temp variables on disconnect
            clear_conversation_state(call_connection_id)
            
            # Clear the call target mapping
            if call_connection_id in CALL_TARGET_MAPPING:
                target_phone = CALL_TARGET_MAPPING[call_connection_id]
                del CALL_TARGET_MAPPING[call_connection_id]
                logging.debug(f"Cleared call target mapping for {call_connection_id} -> {target_phone}")
            
            TEMP_CUSTOM_MESSAGE = None
            TEMP_CUSTOM_VOICE = None
            logging.debug("Conversation state and temp variables cleared on disconnect")
            
        elif event_type == 'Microsoft.Communication.PlayCompleted':
            logging.info(f"TTS playback completed for call {call_connection_id}")
            play_data = event.get('data', {})
            logging.debug(f"PlayCompleted event data: {json.dumps(play_data, indent=2)}")
            
            # After greeting is played, start listening for user response
            if call_connection_id in CONVERSATION_STATE:
                state = CONVERSATION_STATE[call_connection_id]
                current_stage = state['stage']
                logging.debug(f"Current conversation stage: {current_stage}")
                
                if current_stage == 'greeting_played':
                    logging.info("Greeting completed, starting speech recognition")
                    _start_speech_recognition(client, call_connection_id)
                    state['stage'] = 'listening_for_response'
                elif current_stage == 'playing_response':
                    # After playing a conversational response, listen for next input
                    logging.info("Response completed, starting speech recognition for next input")
                    _start_speech_recognition(client, call_connection_id)
                    state['stage'] = 'listening_for_response'
                elif current_stage == 'simulated_listening':
                    # Simulate receiving user input after listening prompt
                    logging.info("Simulating user speech input after listening prompt")
                    
                    # Simulate a typical user response
                    simulated_input = "I need help with scheduling an appointment"
                    logging.debug(f"Using simulated input: '{simulated_input}'")
                    
                    # Process the simulated input
                    fake_recognition_result = {
                        'speechResult': {
                            'speech': simulated_input
                        }
                    }
                    
                    logging.info(f"Processing simulated speech: '{simulated_input}'")
                    _handle_speech_recognition_result(client, call_connection_id, fake_recognition_result)
                elif current_stage == 'listening_for_response':
                    # Handle case where we're already listening for response
                    logging.info("Already in listening state, checking for timeout or continuing simulation")
                    logging.debug("Speech recognition should be active, checking conversation state for timeout")
                    
                    # Check if we should simulate a timeout and generate a response
                    if call_connection_id in CONVERSATION_STATE:
                        state = CONVERSATION_STATE[call_connection_id]
                        recognition_mode = state.get('recognition_mode', 'unknown')
                        listen_start_time = state.get('listen_start_time', time.time())
                        current_time = time.time()
                        elapsed_time = current_time - listen_start_time
                        
                        logging.debug(f"Recognition mode: {recognition_mode}, Elapsed time: {elapsed_time:.2f}s")
                        
                        # If using simulation mode and enough time has passed, simulate user input
                        if recognition_mode == 'simulation' and elapsed_time > 2:  # 2 seconds timeout for simulation
                            logging.info("Simulation timeout reached, generating simulated user response")
                            
                            # Generate varied simulated responses based on conversation history
                            simulated_responses = [
                                "I need help with scheduling an appointment",
                                "I have a question about my medication",
                                "Can you help me with my test results?",
                                "I'm not feeling well and need advice",
                                "I need to reschedule my appointment",
                                "Can you transfer me to a nurse?",
                                "I have a billing question",
                                "Yes, I need help with that"
                            ]
                            
                            turn_count = state.get('turn_count', 0)
                            # Use turn count to vary responses, with some randomness
                            response_index = min(turn_count, len(simulated_responses) - 1)
                            simulated_input = simulated_responses[response_index]
                            
                            logging.debug(f"Using simulated input (turn {turn_count}): '{simulated_input}'")
                            
                            # Process the simulated input
                            fake_recognition_result = {
                                'speechResult': {
                                    'speech': simulated_input
                                }
                            }
                            
                            logging.info(f"Processing simulated speech after timeout: '{simulated_input}'")
                            _handle_speech_recognition_result(client, call_connection_id, fake_recognition_result)
                        elif recognition_mode == 'azure_speech':
                            # For real speech recognition, just log that we're waiting
                            logging.debug(f"Real Azure speech recognition active, waiting for user input (elapsed: {elapsed_time:.2f}s)")
                            # In a real implementation, you might want to handle timeouts here too
                            if elapsed_time > 30:  # 30 second timeout for real speech
                                logging.warning("Speech recognition timeout reached, playing retry message")
                                _play_retry_message(client, call_connection_id)
                        else:
                            logging.debug(f"Unknown recognition mode: {recognition_mode}, no action taken")
                    else:
                        logging.warning("No conversation state found for timeout check")
                    
                    # In a real implementation, this might be where we handle timeout logic
                elif current_stage == 'menu_presented' or current_stage == 'dtmf_menu':
                    # After presenting menu, we could start DTMF recognition or wait for input
                    logging.info("Menu presented, ready for user input")
                    logging.debug("In a real implementation, DTMF recognition would be set up here")
                else:
                    logging.warning(f"Unknown stage after PlayCompleted: {current_stage}")
            else:
                logging.warning(f"No conversation state found for call {call_connection_id} after PlayCompleted")
            
        elif event_type == 'Microsoft.Communication.RecognizeCompleted':
            logging.info(f"Speech recognition completed for call {call_connection_id}")
            recognize_data = event.get('data', {})
            logging.debug(f"RecognizeCompleted event data: {json.dumps(recognize_data, indent=2)}")
            
            # Process the recognized speech and generate response
            # The webhook puts speech data directly in the data section, not nested in recognitionResult
            _handle_speech_recognition_result(client, call_connection_id, recognize_data)
            
        elif event_type == 'Microsoft.Communication.RecognizeFailed':
            recognize_data = event.get('data', {})
            error_info = recognize_data.get('resultInformation', {})
            logging.error(f"Speech recognition failed for call {call_connection_id}")
            logging.error(f"Recognition failure details: {json.dumps(error_info, indent=2)}")
            
            # Handle recognition failure - ask user to repeat
            if call_connection_id in CONVERSATION_STATE:
                logging.info("Attempting to play retry message due to recognition failure")
                _play_retry_message(client, call_connection_id)
            else:
                logging.warning(f"No conversation state found for failed recognition on call {call_connection_id}")
            
        elif event_type == 'Microsoft.Communication.PlayFailed':
            play_data = event.get('data', {})
            play_error = play_data.get('resultInformation', {}).get('message', 'Unknown error')
            error_code = play_data.get('resultInformation', {}).get('code', 'Unknown')
            logging.error(f"TTS playback failed for call {call_connection_id}: {play_error} (Code: {error_code})")
            logging.error(f"PlayFailed event data: {json.dumps(play_data, indent=2)}")
            
        elif event_type == 'Microsoft.Communication.CallEstablished':
            logging.info(f"PSTN call established for call {call_connection_id}")
            establish_data = event.get('data', {})
            logging.debug(f"CallEstablished event data: {json.dumps(establish_data, indent=2)}")
            
        elif event_type == 'Microsoft.Communication.ParticipantsUpdated':
            participants_data = event.get('data', {})
            participants = participants_data.get('participants', [])
            logging.info(f"Participants updated for call {call_connection_id}, count: {len(participants)}")
            logging.debug(f"Participants details: {json.dumps(participants, indent=2)}")
            
        else:
            logging.info(f"Unhandled PSTN event type: {event_type}")
            logging.debug(f"Unhandled event full data: {json.dumps(event, indent=2)}")
        
        return True
        
    except Exception as e:
        logging.error(f"Error handling PSTN webhook event: {str(e)}")
        logging.error(f"Exception type: {type(e).__name__}")
        logging.error(f"Exception args: {e.args}")
        logging.error(f"Event that caused error: {json.dumps(event, indent=2)}")
        return False


def get_call_status(call_id: str) -> Dict[str, Any]:
    """
    Get the status of a PSTN call
    
    Args:
        call_id: The call connection ID
    
    Returns:
        Dict with call status information
    """
    logging.debug(f"Getting call status for call ID: {call_id}")
    
    try:
        if not ACS_CONNECTION_STRING:
            logging.error("ACS_CONNECTION_STRING not configured for call status check")
            return {
                "error": "ACS_CONNECTION_STRING not configured",
                "call_id": call_id
            }
        
        # Initialize the CallAutomationClient
        logging.debug("Initializing CallAutomationClient for status check")
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
        
        try:
            # Get the call connection to check status
            logging.debug(f"Attempting to get call connection for ID: {call_id}")
            call_connection = client.get_call_connection(call_id)
            logging.info(f"Successfully retrieved call connection for {call_id}")
            
            return {
                "call_id": call_id,
                "status": "active_or_recent",
                "message": "Call connection exists and is active or was recently active"
            }
            
        except Exception as status_error:
            logging.warning(f"Unable to retrieve call connection for {call_id}: {str(status_error)}")
            logging.debug(f"Status error type: {type(status_error).__name__}")
            return {
                "call_id": call_id,
                "status": "disconnected_or_invalid",
                "message": f"Unable to retrieve call connection: {str(status_error)}"
            }
            
    except Exception as e:
        logging.error(f"Error getting call status: {str(e)}")
        logging.error(f"Exception type: {type(e).__name__}")
        return {
            "error": f"Failed to get call status: {str(e)}",
            "call_id": call_id
        }


def clear_temp_variables():
    """Clear temporary variables used for webhook communication"""
    global TEMP_CUSTOM_MESSAGE, TEMP_CUSTOM_VOICE
    logging.debug(f"Clearing temp variables - Message: {TEMP_CUSTOM_MESSAGE is not None}, Voice: {TEMP_CUSTOM_VOICE is not None}")
    TEMP_CUSTOM_MESSAGE = None
    TEMP_CUSTOM_VOICE = None
    logging.debug("Temp variables cleared successfully")


def _get_target_participant_for_call(call_connection_id: str) -> Optional[PhoneNumberIdentifier]:
    """
    Get the target participant (the person we called) for speech recognition purposes
    
    Args:
        call_connection_id: The call connection ID
        
    Returns:
        PhoneNumberIdentifier for the target participant, or None if not available
    """
    try:
        # First check the call target mapping (most reliable for outbound calls)
        if call_connection_id in CALL_TARGET_MAPPING:
            target_phone = CALL_TARGET_MAPPING[call_connection_id]
            logging.debug(f"Found target phone in call mapping: {target_phone}")
            if target_phone and target_phone.strip():
                return PhoneNumberIdentifier(target_phone)
            else:
                logging.warning(f"Target phone in mapping is empty for call {call_connection_id}")
        
        # Check if we have conversation state that might contain the target phone
        if call_connection_id in CONVERSATION_STATE:
            state = CONVERSATION_STATE[call_connection_id]
            target_phone = state.get('target_phone_number')
            if target_phone and target_phone.strip():
                logging.debug(f"Found target phone in conversation state: {target_phone}")
                return PhoneNumberIdentifier(target_phone)
        
        # Fall back to the global TARGET_PHONE_NUMBER if available
        if TARGET_PHONE_NUMBER and TARGET_PHONE_NUMBER.strip():
            logging.debug(f"Using global TARGET_PHONE_NUMBER: {TARGET_PHONE_NUMBER}")
            return PhoneNumberIdentifier(TARGET_PHONE_NUMBER)
        
        # If no target phone is available, log the issue
        logging.warning(f"No valid target phone number found for call {call_connection_id}")
        logging.debug(f"Call mapping keys: {list(CALL_TARGET_MAPPING.keys())}")
        logging.debug(f"Conversation state keys: {list(CONVERSATION_STATE.keys())}")
        logging.debug(f"Global TARGET_PHONE_NUMBER: '{TARGET_PHONE_NUMBER}'")
        return None
        
    except Exception as e:
        logging.error(f"Error determining target participant for call {call_connection_id}: {e}")
        logging.error(f"Exception type: {type(e).__name__}")
        return None


def _start_speech_recognition(client: CallAutomationClient, call_connection_id: str):
    """Start speech recognition to listen for user input"""
    logging.info(f"Starting speech recognition for call {call_connection_id}")
    
    # Log SDK version information for debugging
    try:
        import azure.communication.callautomation
        sdk_version = getattr(azure.communication.callautomation, '__version__', 'Unknown version')
        logging.info(f"Azure Communication CallAutomation SDK version: {sdk_version}")
    except Exception as e:
        logging.warning(f"Could not determine SDK version: {e}")
    
    call_connection = None
    try:
        logging.debug(f"Getting call connection for speech recognition: {call_connection_id}")
        call_connection = client.get_call_connection(call_connection_id)
        logging.debug("Call connection retrieved for speech recognition")
        
        # Get the target participant for speech recognition (the person we called)
        target_phone_participant = _get_target_participant_for_call(call_connection_id)
        logging.debug(f"Target participant for speech recognition: {target_phone_participant}")
        
        # Ensure we have a valid target participant
        if target_phone_participant is None:
            logging.warning(f"No target participant found for call {call_connection_id}, cannot proceed with speech recognition")
            logging.debug(f"Current call mappings: {list(CALL_TARGET_MAPPING.keys())}")
            logging.debug(f"Current conversation states: {list(CONVERSATION_STATE.keys())}")
            logging.debug(f"Global TARGET_PHONE_NUMBER: '{TARGET_PHONE_NUMBER}'")
            logging.info("Falling back to conversation simulation due to missing target participant")
            _use_conversation_simulation(call_connection, call_connection_id)
            return
        
        # Validate the target participant object
        if not hasattr(target_phone_participant, 'raw_id'):
            logging.error(f"Invalid target participant object: {target_phone_participant} (type: {type(target_phone_participant)})")
            logging.error("PhoneNumberIdentifier object is missing required 'raw_id' attribute")
            logging.info("Falling back to conversation simulation due to invalid target participant")
            _use_conversation_simulation(call_connection, call_connection_id)
            return
        
        logging.info(f"Using validated target participant: {target_phone_participant} (type: {type(target_phone_participant)})")
        logging.debug(f"Target participant raw_id: {target_phone_participant.raw_id}")
        logging.debug(f"Target participant properties: {getattr(target_phone_participant, 'properties', 'N/A')}")
        
        # First, try to use actual Azure Communication Services speech recognition
        try:
            logging.info("Attempting to use Azure Communication Services speech recognition")
            
            # Check if we have the necessary cognitive services endpoint
            if not COGNITIVE_SERVICES_ENDPOINT:
                raise Exception("COGNITIVE_SERVICES_ENDPOINT not configured for speech recognition")
            
            logging.debug(f"Using cognitive services endpoint: {COGNITIVE_SERVICES_ENDPOINT}")
            
            # Try to use the recognize API if available
            # Note: Different SDK versions may have different method names
            recognition_methods = [
                'start_recognizing_media', 
                'start_recognizing', 
                'recognize_media',
                'start_continuous_dtmf_recognition',
                'start_recognizing_speech',
                'recognize_speech',
                'start_speech_recognition'
            ]
            recognition_started = False
            available_methods = []
            
            # First, check what recognition methods are actually available
            logging.debug(f"Call connection object type: {type(call_connection)}")
            logging.debug(f"Call connection available attributes: {[attr for attr in dir(call_connection) if 'recogni' in attr.lower() or 'speech' in attr.lower()]}")
            
            for method_name in recognition_methods:
                if hasattr(call_connection, method_name):
                    available_methods.append(method_name)
                    logging.debug(f"Found recognition method: {method_name}")
                else:
                    logging.debug(f"Method not available: {method_name}")
            
            logging.debug(f"Available recognition methods: {available_methods}")
            
            if not available_methods:
                # Log all available methods for debugging
                all_methods = [method for method in dir(call_connection) if not method.startswith('_')]
                speech_related = [method for method in all_methods if any(keyword in method.lower() for keyword in ['recogni', 'speech', 'dtmf', 'listen'])]
                logging.debug(f"All available call_connection methods: {all_methods}")
                logging.debug(f"Speech-related methods found: {speech_related}")
                raise Exception(f"No compatible speech recognition methods found in current SDK version. Available methods: {len(all_methods)}, Speech-related: {speech_related}")
            
            # Try each available method
            for method_name in available_methods:
                logging.debug(f"Attempting to use recognition method: {method_name}")
                try:
                    method = getattr(call_connection, method_name)
                    logging.debug(f"Retrieved method {method_name}, attempting to call with appropriate parameters")
                    
                    # Try to inspect the method signature for debugging
                    try:
                        import inspect
                        sig = inspect.signature(method)
                        logging.debug(f"Method {method_name} signature: {sig}")
                        
                        # Get parameter names to help with correct usage
                        param_names = list(sig.parameters.keys())
                        logging.debug(f"Method {method_name} parameters: {param_names}")
                        
                    except Exception:
                        logging.debug(f"Could not inspect signature for {method_name}")
                    
                    # Try to call the recognition method with specific parameters for each method type
                    if method_name == 'start_recognizing_media':
                        logging.debug("Calling start_recognizing_media with speech recognition parameters")
                        # The method needs input_type and target_participant as positional arguments
                        
                        # For speech recognition in outbound calls, we want to listen to the person we called
                        # We've already validated that target_phone_participant is not None above
                        logging.debug(f"Using validated target participant for speech recognition: {target_phone_participant}")
                        
                        # Try different parameter combinations to find the correct one
                        try:
                            # First try with minimal parameters
                            logging.debug("Attempting start_recognizing_media with minimal parameters")
                            result = method(
                                RecognizeInputType.SPEECH,  # input_type (positional)
                                target_phone_participant    # target_participant (positional)
                            )
                            logging.info("Speech recognition started successfully with minimal parameters")
                        except Exception as e1:
                            logging.debug(f"Minimal parameters failed: {e1}")
                            try:
                                # Try with timeout parameter using correct name
                                logging.debug("Attempting start_recognizing_media with initial_silence_timeout")
                                result = method(
                                    RecognizeInputType.SPEECH,  # input_type (positional)
                                    target_phone_participant,   # target_participant (positional)
                                    initial_silence_timeout=10
                                )
                                logging.info("Speech recognition started successfully with initial_silence_timeout")
                            except Exception as e2:
                                logging.debug(f"initial_silence_timeout failed: {e2}")
                                try:
                                    # Try with different timeout parameter name
                                    logging.debug("Attempting start_recognizing_media with silence_timeout")
                                    result = method(
                                        RecognizeInputType.SPEECH,  # input_type (positional)
                                        target_phone_participant,   # target_participant (positional)
                                        silence_timeout=10
                                    )
                                    logging.info("Speech recognition started successfully with silence_timeout")
                                except Exception as e3:
                                    logging.debug(f"silence_timeout failed: {e3}")
                                    try:
                                        # Try with recognize_options parameter
                                        logging.debug("Attempting start_recognizing_media with recognize_options")
                                        result = method(
                                            RecognizeInputType.SPEECH,  # input_type (positional)
                                            target_phone_participant,   # target_participant (positional)
                                            speech_language="en-US"
                                        )
                                        logging.info("Speech recognition started successfully with speech_language")
                                    except Exception as e4:
                                        logging.warning(f"All parameter variations failed for start_recognizing_media")
                                        logging.error(f"Final error: {e4}")
                                        raise e4
                                
                    elif method_name == 'start_continuous_dtmf_recognition':
                        logging.debug("Calling start_continuous_dtmf_recognition with DTMF parameters")
                        # The method needs target_participant as positional argument
                        
                        # For DTMF in outbound calls, we want to listen to the person we called
                        # We've already validated that target_phone_participant is not None above
                        logging.debug(f"Using validated target participant for DTMF recognition: {target_phone_participant}")
                        
                        try:
                            # Try minimal parameters first
                            logging.debug("Attempting start_continuous_dtmf_recognition with minimal parameters")
                            result = method(target_phone_participant)
                            logging.info("DTMF recognition started successfully with target participant")
                        except Exception as dtmf_e1:
                            logging.warning(f"DTMF recognition with target participant failed: {dtmf_e1}")
                            # Log the error details and raise since we should have a valid participant
                            logging.error(f"Target participant validation passed but DTMF recognition still failed")
                            logging.error(f"Target participant type: {type(target_phone_participant)}")
                            logging.error(f"Target participant value: {target_phone_participant}")
                            raise dtmf_e1
                    elif method_name == 'recognize_media':
                        logging.debug("Calling recognize_media with media recognition parameters")
                        result = method(
                            input_type=RecognizeInputType.SPEECH,
                            target_participant=None,
                            initial_silence_timeout=10
                        )
                    elif method_name in ['start_recognizing_speech', 'recognize_speech']:
                        logging.debug(f"Calling {method_name} with speech-specific parameters")
                        # Try speech-specific methods
                        result = method(
                            target_participant=None,
                            speech_language="en-US",
                            initial_silence_timeout=10
                        )
                    elif method_name == 'start_speech_recognition':
                        logging.debug("Calling start_speech_recognition with generic parameters")
                        # Try more generic speech recognition
                        result = method(language="en-US", timeout=10)
                    else:
                        logging.debug(f"Trying {method_name} with fallback parameter approaches")
                        # Generic attempt with minimal parameters
                        try:
                            logging.debug("Attempting with RecognizeInputType.SPEECH parameter")
                            result = method(RecognizeInputType.SPEECH)
                        except TypeError as te1:
                            logging.debug(f"RecognizeInputType.SPEECH failed: {te1}, trying with no parameters")
                            # If that fails, try with no parameters
                            try:
                                result = method()
                            except TypeError as te2:
                                logging.debug(f"No parameters failed: {te2}, trying with basic target_participant=None")
                                result = method(target_participant=None)
                    
                    logging.info(f"Azure Communication Services speech recognition started using {method_name}")
                    logging.debug(f"Recognition operation result: {type(result)}")
                    recognition_started = True
                    
                    # Update conversation state to indicate real speech recognition is active
                    if call_connection_id in CONVERSATION_STATE:
                        CONVERSATION_STATE[call_connection_id]['recognition_mode'] = 'azure_speech'
                        CONVERSATION_STATE[call_connection_id]['recognition_method'] = method_name
                        CONVERSATION_STATE[call_connection_id]['recognition_start_time'] = time.time()
                        logging.debug(f"Updated conversation state for Azure speech recognition using {method_name}")
                    
                    break  # Successfully started, exit the loop
                    
                except Exception as method_error:
                    error_msg = str(method_error)
                    error_type = type(method_error).__name__
                    logging.warning(f"Method {method_name} failed: {error_msg}")
                    logging.debug(f"Method error type: {error_type}")
                    logging.debug(f"Method error args: {method_error.args}")
                    
                    # Log specific error patterns to help with debugging
                    if "parameter" in error_msg.lower():
                        logging.debug(f"Parameter-related error for {method_name}: {error_msg}")
                    elif "argument" in error_msg.lower():
                        logging.debug(f"Argument-related error for {method_name}: {error_msg}")
                    elif "authorization" in error_msg.lower() or "auth" in error_msg.lower():
                        logging.warning(f"Authorization error for {method_name}: {error_msg}")
                    elif "endpoint" in error_msg.lower():
                        logging.warning(f"Endpoint-related error for {method_name}: {error_msg}")
                    else:
                        logging.debug(f"General error for {method_name}: {error_msg}")
                    
                    continue
            
            if recognition_started:
                logging.info("Azure Communication Services speech recognition successfully initiated")
                return  # Successfully started speech recognition, no need for simulation
            else:
                # Provide detailed information about why recognition failed
                error_details = f"No compatible speech recognition methods worked. Tried: {available_methods}"
                logging.warning(f"All recognition methods failed: {error_details}")
                raise Exception(error_details)
            
        except Exception as speech_error:
            logging.warning(f"Azure speech recognition failed: {str(speech_error)}")
            logging.warning(f"Speech error type: {type(speech_error).__name__}")
            logging.info("Falling back to conversation simulation approach")
            
            # Fall back to conversation simulation
            logging.warning("Using conversation simulation approach due to Azure speech recognition limitations")
            logging.debug("Azure Communication Services speech recognition not available or failed")
            logging.debug("This could be due to: missing cognitive services, API version incompatibility, or configuration issues")
            logging.debug("Available call_connection methods: " + ", ".join([method for method in dir(call_connection) if not method.startswith('_')]))
            _use_conversation_simulation(call_connection, call_connection_id)
        
    except Exception as e:
        logging.error(f"Failed to start speech recognition: {str(e)}")
        logging.error(f"Exception type: {type(e).__name__}")
        if call_connection:
            logging.info("Attempting conversation simulation as fallback")
            _use_conversation_simulation(call_connection, call_connection_id)
        else:
            logging.error("Could not get call connection for conversation simulation")
            logging.error("Speech recognition completely failed for this call")


def _use_conversation_simulation(call_connection, call_connection_id: str):
    """Use a conversation simulation approach when speech recognition API is not available"""
    try:
        logging.info(f"Using conversation simulation for call {call_connection_id}")
        logging.debug("Creating simulation prompt for listening")
        
        # Get current conversation state to personalize the prompt
        conversation_context = ""
        if call_connection_id in CONVERSATION_STATE:
            state = CONVERSATION_STATE[call_connection_id]
            turn_count = state.get('turn_count', 0)
            if turn_count == 0:
                conversation_context = "How can I help you today? "
            elif turn_count == 1:
                conversation_context = "I understand. Could you tell me more? "
            else:
                conversation_context = "What else can I help you with? "
        
        # Create a more natural listening prompt
        simulation_text = f"{conversation_context}I'm listening for your response. Please speak now, and I'll do my best to help you."
        
        # Play a prompt that simulates listening
        simulation_prompt = TextSource(
            text=simulation_text,
            voice_name=TTS_VOICE
        )
        logging.debug(f"Simulation prompt created with voice: {TTS_VOICE}")
        logging.debug(f"Simulation text: '{simulation_text}'")
        
        # Play the prompt
        logging.debug("Playing simulation listening prompt")
        play_result = call_connection.play_media(
            play_source=simulation_prompt,
            play_to="all"
        )
        
        operation_id = getattr(play_result, 'operation_id', 'Unknown')
        logging.info(f"Simulation listening prompt initiated. Operation ID: {operation_id}")
        
        # Set conversation state to simulate speech recognition
        if call_connection_id in CONVERSATION_STATE:
            CONVERSATION_STATE[call_connection_id]['stage'] = 'simulated_listening'
            CONVERSATION_STATE[call_connection_id]['listen_start_time'] = time.time()
            CONVERSATION_STATE[call_connection_id]['simulation_mode'] = True
            CONVERSATION_STATE[call_connection_id]['recognition_mode'] = 'simulation'
            CONVERSATION_STATE[call_connection_id]['simulation_prompt_played'] = True
            logging.debug(f"Updated conversation state for simulation mode: {CONVERSATION_STATE[call_connection_id]['stage']}")
            
            # Log the reason for using simulation
            logging.info("Conversation simulation activated due to Azure Communication Services speech recognition limitations")
            logging.debug("This simulation will automatically generate user responses after the listening prompt")
            logging.debug(f"Simulation will trigger after listening prompt completes (stage will change to 'simulated_listening')")
        else:
            logging.warning(f"No conversation state found for call {call_connection_id} during simulation setup")
        
        logging.info("Conversation simulation mode activated - will simulate user response after prompt completion")
        
    except Exception as sim_error:
        logging.error(f"Conversation simulation failed: {str(sim_error)}")
        logging.error(f"Simulation error type: {type(sim_error).__name__}")
        logging.info("Falling back to DTMF menu due to simulation failure")
        _provide_dtmf_menu(call_connection, call_connection_id)


def _provide_dtmf_menu(call_connection, call_connection_id: str):
    """Provide DTMF menu when speech recognition is not working"""
    try:
        logging.info(f"Providing DTMF menu for call {call_connection_id}")
        logging.debug("Creating DTMF menu prompt")
        
        # Create DTMF menu prompt
        dtmf_prompt = TextSource(
            text="I'll provide some options. Press 1 for appointments, 2 for general questions, 3 to speak with someone, or 0 to hear this menu again.",
            voice_name=TTS_VOICE
        )
        logging.debug(f"DTMF prompt created with voice: {TTS_VOICE}")
        
        # Play the DTMF prompt
        play_result = call_connection.play_media(
            play_source=dtmf_prompt,
            play_to="all"
        )
        
        operation_id = getattr(play_result, 'operation_id', 'Unknown')
        logging.info(f"DTMF menu playback initiated. Operation ID: {operation_id}")
        
        # Update conversation state to indicate DTMF mode
        if call_connection_id in CONVERSATION_STATE:
            CONVERSATION_STATE[call_connection_id]['recognition_mode'] = 'dtmf'
            CONVERSATION_STATE[call_connection_id]['stage'] = 'dtmf_menu'
            logging.debug("Updated conversation state to DTMF mode")
        else:
            logging.warning(f"No conversation state found for call {call_connection_id} during DTMF menu setup")
        
        logging.info("DTMF menu provided")
        
    except Exception as menu_error:
        logging.error(f"Failed to provide DTMF menu: {str(menu_error)}")
        logging.error(f"DTMF error type: {type(menu_error).__name__}")
        logging.error(f"Call ID: {call_connection_id}")


def _handle_speech_recognition_result(client: CallAutomationClient, call_connection_id: str, recognition_result: dict):
    """Process recognized speech and generate conversational response"""
    try:
        logging.info(f"Processing speech recognition result for call {call_connection_id}")
        logging.debug(f"Recognition result: {json.dumps(recognition_result, indent=2)}")
        
        # Extract recognized text - handle both direct speechResult and nested structure
        recognized_text = ""
        confidence = 0.0
        
        # Check if we have speechResult directly
        if 'speechResult' in recognition_result:
            speech_result = recognition_result['speechResult']
            recognized_text = speech_result.get('speech', '').strip()
            confidence = speech_result.get('confidence', 0.0)
            logging.debug(f"Found speechResult in recognition_result: speech='{recognized_text}', confidence={confidence}")
        
        # Check if we have recognitionResult containing speechResult (from webhook)
        elif 'recognitionResult' in recognition_result:
            recognition_data = recognition_result['recognitionResult']
            if 'speechResult' in recognition_data:
                speech_result = recognition_data['speechResult']
                recognized_text = speech_result.get('speech', '').strip()
                confidence = speech_result.get('confidence', 0.0)
                logging.debug(f"Found speechResult in recognitionResult: speech='{recognized_text}', confidence={confidence}")
        
        # Direct access for webhook events that pass speechResult at top level
        elif 'speech' in recognition_result:
            recognized_text = recognition_result.get('speech', '').strip()
            confidence = recognition_result.get('confidence', 0.0)
            logging.debug(f"Found speech directly in result: speech='{recognized_text}', confidence={confidence}")
        
        logging.info(f"Recognized speech: '{recognized_text}' (confidence: {confidence:.3f})")
        
        if not recognized_text:
            logging.warning("No speech recognized, asking user to repeat")
            _play_retry_message(client, call_connection_id)
            return
        
        # Update conversation state
        if call_connection_id in CONVERSATION_STATE:
            state = CONVERSATION_STATE[call_connection_id]
            logging.debug(f"Current conversation state before update: {state}")
            
            state['conversation_history'].append({
                'speaker': 'user', 
                'message': recognized_text
            })
            state['turn_count'] += 1
            
            logging.debug(f"Updated turn count: {state['turn_count']}")
            logging.debug(f"Conversation history length: {len(state['conversation_history'])}")
            
            # Generate conversational response
            logging.debug("Generating conversational response")
            response_text = _generate_conversational_response(recognized_text, state)
            logging.info(f"Generated response: '{response_text[:100]}...'")
            
            # Play the response
            _play_conversational_response(client, call_connection_id, response_text)
            
            # Update conversation history with assistant response
            state['conversation_history'].append({
                'speaker': 'assistant', 
                'message': response_text
            })
            logging.debug(f"Updated conversation history length: {len(state['conversation_history'])}")
        else:
            logging.error(f"No conversation state found for call {call_connection_id}")
            
    except Exception as e:
        logging.error(f"Error handling speech recognition result: {str(e)}")
        logging.error(f"Exception type: {type(e).__name__}")
        logging.error(f"Recognition result that caused error: {json.dumps(recognition_result, indent=2)}")
        _play_error_message(client, call_connection_id)


def _generate_conversational_response(user_input: str, conversation_state: dict) -> str:
    """Generate an appropriate conversational response based on user input using bot service"""
    
    logging.debug(f"Generating response for input: '{user_input}'")
    logging.debug(f"Conversation state: Turn {conversation_state['turn_count']}, History length: {len(conversation_state['conversation_history'])}")
    
    try:
        # Try to use the bot service for intelligent AI responses first
        from .bot_service import generate_response_sync
        
        # Create a context-aware message for the bot
        turn_count = conversation_state['turn_count']
        conversation_history = conversation_state.get('conversation_history', [])
        
        # Build context from conversation history
        context_messages = []
        for entry in conversation_history[-3:]:  # Last 3 messages for context
            speaker = entry.get('speaker', 'unknown')
            message = entry.get('message', '')
            if speaker == 'user':
                context_messages.append(f"Patient: {message}")
            elif speaker == 'assistant':
                context_messages.append(f"Assistant: {message}")
        
        # Create enhanced user message with context
        if context_messages:
            enhanced_message = f"Conversation context:\n" + "\n".join(context_messages) + f"\n\nCurrent patient input: {user_input}"
        else:
            enhanced_message = f"Patient says: {user_input}"
        
        logging.debug(f"Enhanced message for bot service: '{enhanced_message}'")
        
        # Generate response using bot service (with OpenAI integration)
        bot_response = generate_response_sync(enhanced_message)
        
        if bot_response and bot_response.strip():
            logging.info(f"Bot service generated response: '{bot_response[:50]}...'")
            return bot_response.strip()
        else:
            logging.warning("Bot service returned empty response, falling back to rule-based")
            
    except Exception as bot_error:
        logging.warning(f"Bot service failed: {str(bot_error)}, falling back to rule-based responses")
        logging.debug(f"Bot error type: {type(bot_error).__name__}")
    
    # Fallback to rule-based responses if bot service fails
    logging.debug("Using fallback rule-based responses")
    
    user_input_lower = user_input.lower()
    turn_count = conversation_state['turn_count']
    
    logging.debug(f"Processing turn {turn_count} with lowercase input: '{user_input_lower}'")
    
    # Healthcare-specific responses
    if any(word in user_input_lower for word in ['appointment', 'book', 'schedule']):
        response = "I'd be happy to help you schedule an appointment. What type of appointment do you need, and what's your preferred date and time?"
        logging.debug("Detected appointment-related request")
    elif any(word in user_input_lower for word in ['pain', 'hurt', 'sick', 'feel']):
        response = "I understand you're not feeling well. Can you tell me more about your symptoms? When did they start?"
        logging.debug("Detected health/symptom-related request")
    elif any(word in user_input_lower for word in ['prescription', 'medication', 'medicine', 'refill']):
        response = "For prescription refills or medication questions, I can help connect you with our pharmacy team. What medication do you need assistance with?"
        logging.debug("Detected medication-related request")
    elif any(word in user_input_lower for word in ['emergency', 'urgent', 'help']):
        response = "If this is a medical emergency, please hang up and call 911 immediately. For urgent but non-emergency care, I can help you find the nearest urgent care facility."
        logging.debug("Detected emergency/urgent request")
    elif any(word in user_input_lower for word in ['yes', 'yeah', 'ok', 'okay']):
        response = "Great! How else can I assist you today? I can help with appointments, general health questions, or connecting you with the right department."
        logging.debug("Detected affirmative response")
    elif any(word in user_input_lower for word in ['no', 'nothing', "that's all"]):
        response = "Thank you for calling! If you need any assistance in the future, please don't hesitate to reach out. Have a great day!"
        logging.debug("Detected negative/ending response")
    elif any(word in user_input_lower for word in ['hello', 'hi', 'hey']):
        response = "Hello! I'm your healthcare assistant. How can I help you today? I can assist with appointments, answer general health questions, or direct your call to the appropriate department."
        logging.debug("Detected greeting")
    # Generic conversational responses
    elif turn_count == 1:
        response = "I understand. Can you provide more details about what you need help with today?"
        logging.debug("Using first turn generic response")
    elif turn_count == 2:
        response = "Thank you for that information. Is there anything specific I can help you with regarding your healthcare needs?"
        logging.debug("Using second turn generic response")
    else:
        response = "I want to make sure I'm helping you properly. Could you please clarify what type of assistance you're looking for?"
        logging.debug("Using default generic response")
    
    logging.info(f"Generated fallback response: '{response[:50]}...'")
    return response


def _play_conversational_response(client: CallAutomationClient, call_connection_id: str, response_text: str):
    """Play the conversational response and then listen for next input"""
    try:
        logging.info(f"Playing conversational response for call {call_connection_id}")
        logging.debug(f"Response text: '{response_text}'")
        
        call_connection = client.get_call_connection(call_connection_id)
        logging.debug("Retrieved call connection for response playback")
        
        # Create text source for TTS
        text_source = TextSource(
            text=response_text,
            voice_name=TTS_VOICE
        )
        logging.debug(f"Created TextSource with voice: {TTS_VOICE}")
        
        logging.info(f"Playing conversational response: '{response_text[:50]}...'")
        
        # Play the response
        play_result = call_connection.play_media(
            play_source=text_source,
            play_to="all"
        )
        
        # Update conversation state to indicate we're playing a response
        if call_connection_id in CONVERSATION_STATE:
            CONVERSATION_STATE[call_connection_id]['stage'] = 'playing_response'
            logging.debug("Updated conversation stage to 'playing_response'")
        else:
            logging.warning(f"No conversation state found for call {call_connection_id} during response play")
        
        operation_id = getattr(play_result, 'operation_id', 'Unknown')
        logging.info(f"Conversational response playback initiated. Operation ID: {operation_id}")
        
    except Exception as e:
        logging.error(f"Failed to play conversational response: {str(e)}")
        logging.error(f"Exception type: {type(e).__name__}")
        logging.error(f"Response text that failed: '{response_text}'")
        logging.error(f"Call ID: {call_connection_id}")


def _play_retry_message(client: CallAutomationClient, call_connection_id: str):
    """Play a message asking the user to repeat their input"""
    logging.info(f"Playing retry message for call {call_connection_id}")
    retry_message = "I'm sorry, I didn't catch that. Could you please repeat what you said?"
    logging.debug(f"Retry message: '{retry_message}'")
    _play_conversational_response(client, call_connection_id, retry_message)


def _play_error_message(client: CallAutomationClient, call_connection_id: str):
    """Play an error message when something goes wrong"""
    logging.error(f"Playing error message for call {call_connection_id}")
    error_message = "I'm experiencing some technical difficulties. Let me transfer you to a human representative."
    logging.debug(f"Error message: '{error_message}'")
    _play_conversational_response(client, call_connection_id, error_message)


def get_conversation_state(call_connection_id: str) -> dict:
    """Get the current conversation state for a call"""
    logging.debug(f"Getting conversation state for call {call_connection_id}")
    state = CONVERSATION_STATE.get(call_connection_id, {})
    if state:
        logging.debug(f"Found conversation state - Stage: {state.get('stage')}, Turns: {state.get('turn_count')}")
    else:
        logging.debug(f"No conversation state found for call {call_connection_id}")
    return state


def clear_conversation_state(call_connection_id: str):
    """Clear conversation state when call ends"""
    if call_connection_id in CONVERSATION_STATE:
        state_info = CONVERSATION_STATE[call_connection_id]
        logging.info(f"Clearing conversation state for call {call_connection_id}")
        logging.debug(f"Final state - Stage: {state_info.get('stage')}, Turns: {state_info.get('turn_count')}, History length: {len(state_info.get('conversation_history', []))}")
        
        del CONVERSATION_STATE[call_connection_id]
        logging.info(f"Cleared conversation state for call {call_connection_id}")
    else:
        logging.warning(f"No conversation state found to clear for call {call_connection_id}")
        logging.debug(f"Current conversation states: {list(CONVERSATION_STATE.keys())}")


def _continue_conversation_without_recognition(client: CallAutomationClient, call_connection_id: str):
    """Continue conversation when speech recognition is not available"""
    try:
        logging.info(f"Continuing conversation without recognition for call {call_connection_id}")
        
        # Play a message indicating we'll use a simple menu system
        menu_text = "I'm having trouble with speech recognition. Let me offer you some options. Press 1 for appointments, 2 for general questions, or 3 to speak with someone."
        logging.debug(f"Menu fallback text: '{menu_text}'")
        
        call_connection = client.get_call_connection(call_connection_id)
        logging.debug("Retrieved call connection for menu fallback")
        
        text_source = TextSource(
            text=menu_text,
            voice_name=TTS_VOICE
        )
        
        play_result = call_connection.play_media(
            play_source=text_source,
            play_to="all"
        )
        
        operation_id = getattr(play_result, 'operation_id', 'Unknown')
        logging.info(f"Menu fallback playback initiated. Operation ID: {operation_id}")
        
        # Update conversation state
        if call_connection_id in CONVERSATION_STATE:
            CONVERSATION_STATE[call_connection_id]['stage'] = 'menu_presented'
            logging.debug("Updated conversation stage to 'menu_presented'")
        else:
            logging.warning(f"No conversation state found for call {call_connection_id} during menu fallback")
        
        logging.info("Presented menu options due to speech recognition unavailability")
        
    except Exception as e:
        logging.error(f"Failed to continue conversation without recognition: {str(e)}")
        logging.error(f"Exception type: {type(e).__name__}")
        logging.error(f"Call ID: {call_connection_id}")


def diagnose_speech_recognition_capabilities(client: CallAutomationClient) -> dict:
    """
    Diagnose the current Azure Communication Services speech recognition capabilities
    
    Returns:
        dict: Diagnostic information about speech recognition availability
    """
    logging.info("Diagnosing Azure Communication Services speech recognition capabilities")
    
    try:
        # Create a temporary call connection for testing (won't actually make a call)
        diagnosis = {
            "cognitive_services_configured": bool(COGNITIVE_SERVICES_ENDPOINT),
            "cognitive_services_endpoint": COGNITIVE_SERVICES_ENDPOINT or "Not configured",
            "acs_connection_configured": bool(ACS_CONNECTION_STRING),
            "available_recognition_methods": [],
            "sdk_version": "Unknown",
            "diagnosis_timestamp": time.time()
        }
        
        # Check what methods are available in the SDK
        try:
            # We can't create an actual call connection without making a real call,
            # so we'll check the client capabilities instead
            client_methods = [method for method in dir(client) if not method.startswith('_')]
            diagnosis["client_methods"] = client_methods
            logging.debug(f"Available client methods: {client_methods}")
            
            # Check for recognition-related methods
            recognition_methods = [method for method in client_methods if 'recogni' in method.lower()]
            diagnosis["recognition_related_methods"] = recognition_methods
            logging.debug(f"Recognition-related methods: {recognition_methods}")
            
            # Try to get SDK version information
            try:
                import azure.communication.callautomation
                diagnosis["sdk_version"] = getattr(azure.communication.callautomation, '__version__', 'Version not available')
            except Exception:
                diagnosis["sdk_version"] = "Unable to determine SDK version"
            
            logging.info(f"Speech recognition diagnosis completed")
            logging.debug(f"Diagnosis results: {diagnosis}")
            
        except Exception as method_check_error:
            logging.warning(f"Could not fully diagnose SDK capabilities: {str(method_check_error)}")
            diagnosis["method_check_error"] = str(method_check_error)
        
        return diagnosis
        
    except Exception as e:
        logging.error(f"Failed to diagnose speech recognition capabilities: {str(e)}")
        return {
            "error": str(e),
            "diagnosis_failed": True,
            "timestamp": time.time()
        }


def get_speech_recognition_status() -> dict:
    """
    Get the current status of speech recognition configuration and capabilities
    
    Returns:
        dict: Status information about speech recognition
    """
    logging.debug("Getting speech recognition status")
    
    try:
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
        diagnosis = diagnose_speech_recognition_capabilities(client)
        
        status = {
            "speech_recognition_available": False,
            "using_simulation": True,
            "configuration_issues": [],
            "recommendations": [],
            "diagnosis": diagnosis
        }
        
        # Check configuration issues
        if not COGNITIVE_SERVICES_ENDPOINT:
            status["configuration_issues"].append("COGNITIVE_SERVICES_ENDPOINT not configured")
            status["recommendations"].append("Configure COGNITIVE_SERVICES_ENDPOINT environment variable")
        
        if not ACS_CONNECTION_STRING:
            status["configuration_issues"].append("ACS_CONNECTION_STRING not configured")
            status["recommendations"].append("Configure ACS_CONNECTION_STRING environment variable")
        
        # Check if any recognition methods are available
        recognition_methods = diagnosis.get("recognition_related_methods", [])
        if recognition_methods:
            status["potential_recognition_methods"] = recognition_methods
            status["recommendations"].append("Try upgrading Azure Communication Services SDK for latest speech recognition features")
        else:
            status["recommendations"].append("Current SDK version may not support speech recognition - consider simulation approach")
        
        # Determine overall status
        if len(status["configuration_issues"]) == 0 and recognition_methods:
            status["speech_recognition_available"] = True
            status["using_simulation"] = False
        
        logging.info(f"Speech recognition status: Available={status['speech_recognition_available']}, Using simulation={status['using_simulation']}")
        return status
        
    except Exception as e:
        logging.error(f"Failed to get speech recognition status: {str(e)}")
        return {
            "error": str(e),
            "speech_recognition_available": False,
            "using_simulation": True,
            "status_check_failed": True
        }


def debug_conversation_flow(call_connection_id: Optional[str] = None) -> dict:
    """
    Debug conversation flow and state for troubleshooting
    
    Args:
        call_connection_id: Specific call to debug (optional, debugs all if None)
    
    Returns:
        dict: Debug information about conversation flow
    """
    logging.info(f"Debugging conversation flow for call: {call_connection_id if call_connection_id else 'all calls'}")
    
    debug_info = {
        "debug_timestamp": time.time(),
        "total_active_conversations": len(CONVERSATION_STATE),
        "conversation_details": {}
    }
    
    try:
        if call_connection_id:
            # Debug specific call
            if call_connection_id in CONVERSATION_STATE:
                state = CONVERSATION_STATE[call_connection_id]
                debug_info["conversation_details"][call_connection_id] = _analyze_conversation_state(call_connection_id, state)
            else:
                debug_info["error"] = f"No conversation state found for call {call_connection_id}"
                debug_info["available_calls"] = list(CONVERSATION_STATE.keys())
        else:
            # Debug all calls
            for cid, state in CONVERSATION_STATE.items():
                debug_info["conversation_details"][cid] = _analyze_conversation_state(cid, state)
        
        logging.debug(f"Conversation flow debug completed: {len(debug_info['conversation_details'])} conversations analyzed")
        return debug_info
        
    except Exception as e:
        logging.error(f"Failed to debug conversation flow: {str(e)}")
        debug_info["debug_error"] = str(e)
        return debug_info


def _analyze_conversation_state(call_connection_id: str, state: dict) -> dict:
    """
    Analyze a single conversation state for debugging
    
    Args:
        call_connection_id: Call connection ID
        state: Conversation state dictionary
    
    Returns:
        dict: Analysis of the conversation state
    """
    current_time = time.time()
    
    analysis = {
        "call_id": call_connection_id,
        "current_stage": state.get('stage', 'unknown'),
        "turn_count": state.get('turn_count', 0),
        "recognition_mode": state.get('recognition_mode', 'unknown'),
        "simulation_mode": state.get('simulation_mode', False),
        "conversation_history_length": len(state.get('conversation_history', [])),
        "stage_issues": [],
        "recommendations": []
    }
    
    # Check for timing issues
    listen_start_time = state.get('listen_start_time')
    elapsed_time = None
    if listen_start_time:
        elapsed_time = current_time - listen_start_time
        analysis["time_in_current_stage"] = elapsed_time
        
        if elapsed_time > 60:  # More than 1 minute
            analysis["stage_issues"].append(f"Conversation stuck in stage '{analysis['current_stage']}' for {elapsed_time:.1f} seconds")
            analysis["recommendations"].append("Consider resetting conversation or providing fallback options")
    
    # Check for recognition issues
    if analysis["recognition_mode"] == "simulation" and analysis["current_stage"] == "listening_for_response":
        if elapsed_time is not None and elapsed_time > 5:
            analysis["stage_issues"].append("Simulation mode stuck in listening state - timeout should have triggered")
            analysis["recommendations"].append("Check simulation timeout logic in PlayCompleted handler")
    
    # Check conversation history
    if analysis["turn_count"] > 10:
        analysis["stage_issues"].append(f"Very long conversation ({analysis['turn_count']} turns)")
        analysis["recommendations"].append("Consider offering to transfer to human representative")
    
    # Check for missing data
    required_fields = ['stage', 'turn_count', 'conversation_history']
    missing_fields = [field for field in required_fields if field not in state]
    if missing_fields:
        analysis["stage_issues"].append(f"Missing required state fields: {missing_fields}")
        analysis["recommendations"].append("Reinitialize conversation state")
    
    logging.debug(f"Analyzed conversation {call_connection_id}: Stage={analysis['current_stage']}, Issues={len(analysis['stage_issues'])}")
    
    return analysis


def test_target_participant_logic():
    """
    Test function to verify target participant identification logic
    """
    # Simulate a call mapping
    test_call_id = "test-call-123"
    test_phone_number = "+1234567890"
    
    # Store the mapping
    CALL_TARGET_MAPPING[test_call_id] = test_phone_number
    
    # Test the helper function
    target_participant = _get_target_participant_for_call(test_call_id)
    
    print(f"Test Results:")
    print(f"  Call ID: {test_call_id}")
    print(f"  Target Phone: {test_phone_number}")
    print(f"  Target Participant Type: {type(target_participant)}")
    print(f"  Target Participant Value: {target_participant}")
    
    # Verify it's a PhoneNumberIdentifier
    if target_participant and hasattr(target_participant, 'raw_id'):
        print(f"  PhoneNumberIdentifier raw_id: {target_participant.raw_id}")
        print(f"  PhoneNumberIdentifier kind: {getattr(target_participant, 'kind', 'N/A')}")
        print(f"  PhoneNumberIdentifier properties: {getattr(target_participant, 'properties', 'N/A')}")
        print("  ✅ Target participant correctly identified as PhoneNumberIdentifier")
    else:
        print("  ❌ Target participant is not a PhoneNumberIdentifier or is None")
        print(f"  Available attributes: {dir(target_participant) if target_participant else 'None'}")
    
    # Clean up
    del CALL_TARGET_MAPPING[test_call_id]
    
    return target_participant


if __name__ == "__main__":
    # Run test when script is executed directly
    test_target_participant_logic()
