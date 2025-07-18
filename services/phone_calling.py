"""
PSTN Phone Calling Module
Handles PSTN (Public Switched Telephone Network) phone calls using Azure Communication Services
"""

import os
import json
import logging
from typing import Optional, Dict, Any

from azure.communication.callautomation import CallAutomationClient, TextSource, RecognitionChoice
from azure.communication.callautomation import PhoneNumberIdentifier, RecognizeInputType

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


def validate_pstn_configuration() -> tuple[bool, str]:
    """
    Validate that all required PSTN configuration is present
    Returns: (is_valid, error_message)
    """
    if not ACS_CONNECTION_STRING:
        return False, "ACS_CONNECTION_STRING is required for PSTN calls"
    
    if not COGNITIVE_SERVICES_ENDPOINT:
        return False, "COGNITIVE_SERVICES_ENDPOINT is required for TTS functionality"
    
    if not SOURCE_CALLER_ID:
        return False, "SOURCE_CALLER_ID is required for PSTN calls"
    
    return True, ""


def validate_phone_number(phone_number: str) -> tuple[bool, str]:
    """
    Validate phone number format for PSTN calls
    Returns: (is_valid, error_message)
    """
    if not phone_number:
        return False, "Phone number is required"
    
    if not phone_number.startswith('+'):
        return False, "Phone number must be in international format starting with '+'"
    
    # Basic validation - should have country code + number
    if len(phone_number) < 8 or len(phone_number) > 16:
        return False, "Phone number length should be between 8-16 characters"
    
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
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
        
        # Create phone number identifiers
        target_phone_user = PhoneNumberIdentifier(target_phone)
        source_caller_id = PhoneNumberIdentifier(SOURCE_CALLER_ID)
        
        # Store custom settings for webhook
        TEMP_CUSTOM_MESSAGE = custom_message or WELCOME_MESSAGE
        TEMP_CUSTOM_VOICE = custom_voice or TTS_VOICE
        
        # Determine callback URL
        if not callback_url:
            if CALLBACK_URL_BASE:
                callback_url = f"https://{CALLBACK_URL_BASE}/api/phone_call_webhook"
            else:
                callback_url = "http://localhost:7071/api/phone_call_webhook"
        
        logging.info(f"Using callback URL: {callback_url}")
        logging.info(f"Source caller ID: {SOURCE_CALLER_ID}")
        
        # Create the PSTN call
        call_result = client.create_call(
            target_participant=target_phone_user,
            callback_url=callback_url,
            cognitive_services_endpoint=COGNITIVE_SERVICES_ENDPOINT,
            source_caller_id_number=source_caller_id
        )
        
        call_connection_id = call_result.call_connection_id if hasattr(call_result, 'call_connection_id') else 'Unknown'
        
        logging.info(f"PSTN call created successfully. Call ID: {call_connection_id}")
        
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
        
        # Initialize ACS client for event handling
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
        
        if event_type == 'Microsoft.Communication.CallConnected':
            logging.info(f"PSTN call connected! Playing TTS message...")
            
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
                
                logging.info(f"Playing message: '{message_to_play[:50]}...', Voice: {voice_to_use}")
                
                # Play the message to all participants
                play_result = call_connection.play_media(
                    play_source=text_source,
                    play_to="all"
                )
                
                operation_id = getattr(play_result, 'operation_id', 'Unknown')
                logging.info(f"TTS playback initiated. Operation ID: {operation_id}")
                
                # Initialize conversation state for this call
                CONVERSATION_STATE[call_connection_id] = {
                    'stage': 'greeting_played',
                    'turn_count': 0,
                    'conversation_history': [
                        {'speaker': 'assistant', 'message': message_to_play}
                    ]
                }
                
                # Clear temp variables after use
                TEMP_CUSTOM_MESSAGE = None
                TEMP_CUSTOM_VOICE = None
                
            except Exception as play_error:
                logging.error(f"Error playing TTS: {str(play_error)}")
                return False
                
        elif event_type == 'Microsoft.Communication.CallDisconnected':
            disconnect_reason = event.get('data', {}).get('callConnectionId', 'Unknown reason')
            logging.info(f"PSTN call disconnected. Call ID: {call_connection_id}, Reason: {disconnect_reason}")
            
            # Clear conversation state and temp variables on disconnect
            clear_conversation_state(call_connection_id)
            TEMP_CUSTOM_MESSAGE = None
            TEMP_CUSTOM_VOICE = None
            
        elif event_type == 'Microsoft.Communication.PlayCompleted':
            logging.info(f"TTS playback completed for call {call_connection_id}")
            
            # After greeting is played, start listening for user response
            if call_connection_id in CONVERSATION_STATE:
                state = CONVERSATION_STATE[call_connection_id]
                if state['stage'] == 'greeting_played':
                    _start_speech_recognition(client, call_connection_id)
                    state['stage'] = 'listening_for_response'
                elif state['stage'] == 'playing_response':
                    # After playing a conversational response, listen for next input
                    _start_speech_recognition(client, call_connection_id)
                    state['stage'] = 'listening_for_response'
                elif state['stage'] == 'menu_presented':
                    # After presenting menu, we could start DTMF recognition
                    logging.info("Menu presented, waiting for user input")
            
        elif event_type == 'Microsoft.Communication.RecognizeCompleted':
            logging.info(f"Speech recognition completed for call {call_connection_id}")
            
            # Process the recognized speech and generate response
            recognition_result = event.get('data', {}).get('recognitionResult', {})
            _handle_speech_recognition_result(client, call_connection_id, recognition_result)
            
        elif event_type == 'Microsoft.Communication.RecognizeFailed':
            logging.error(f"Speech recognition failed for call {call_connection_id}")
            
            # Handle recognition failure - ask user to repeat
            if call_connection_id in CONVERSATION_STATE:
                _play_retry_message(client, call_connection_id)
            
        elif event_type == 'Microsoft.Communication.PlayFailed':
            play_error = event.get('data', {}).get('resultInformation', {}).get('message', 'Unknown error')
            logging.error(f"TTS playback failed for call {call_connection_id}: {play_error}")
            
        elif event_type == 'Microsoft.Communication.CallEstablished':
            logging.info(f"PSTN call established for call {call_connection_id}")
            
        elif event_type == 'Microsoft.Communication.ParticipantsUpdated':
            participants = event.get('data', {}).get('participants', [])
            logging.info(f"Participants updated for call {call_connection_id}, count: {len(participants)}")
            
        else:
            logging.info(f"Unhandled PSTN event type: {event_type}")
        
        return True
        
    except Exception as e:
        logging.error(f"Error handling PSTN webhook event: {str(e)}")
        return False


def get_call_status(call_id: str) -> Dict[str, Any]:
    """
    Get the status of a PSTN call
    
    Args:
        call_id: The call connection ID
    
    Returns:
        Dict with call status information
    """
    try:
        if not ACS_CONNECTION_STRING:
            return {
                "error": "ACS_CONNECTION_STRING not configured",
                "call_id": call_id
            }
        
        # Initialize the CallAutomationClient
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
        
        try:
            # Get the call connection to check status
            call_connection = client.get_call_connection(call_id)
            
            return {
                "call_id": call_id,
                "status": "active_or_recent",
                "message": "Call connection exists and is active or was recently active"
            }
            
        except Exception as status_error:
            return {
                "call_id": call_id,
                "status": "disconnected_or_invalid",
                "message": f"Unable to retrieve call connection: {str(status_error)}"
            }
            
    except Exception as e:
        logging.error(f"Error getting call status: {str(e)}")
        return {
            "error": f"Failed to get call status: {str(e)}",
            "call_id": call_id
        }


def clear_temp_variables():
    """Clear temporary variables used for webhook communication"""
    global TEMP_CUSTOM_MESSAGE, TEMP_CUSTOM_VOICE
    TEMP_CUSTOM_MESSAGE = None
    TEMP_CUSTOM_VOICE = None


def _start_speech_recognition(client: CallAutomationClient, call_connection_id: str):
    """Start speech recognition to listen for user input"""
    try:
        call_connection = client.get_call_connection(call_connection_id)
        
        logging.info(f"Starting speech recognition for call {call_connection_id}")
        
        # Start recognition using the correct API method
        # Note: The exact API may vary based on Azure Communication Services version
        # This is a placeholder for the speech recognition functionality
        # In production, you would use the actual Azure Speech Services integration
        
        # For now, we'll use a simple approach with DTMF recognition as fallback
        # and log that speech recognition would be initiated here
        logging.info("Speech recognition would be initiated here - using DTMF as fallback")
        
        # Example of starting DTMF recognition (which is supported)
        # This allows users to press keys instead of speaking
        try:
            # For now, we'll simulate speech recognition by playing a prompt
            # and then listening for a few seconds before continuing
            prompt_text = "Please speak now, or press any key to continue."
            
            text_source = TextSource(
                text=prompt_text,
                voice_name=TTS_VOICE
            )
            
            # Play prompt and then continue conversation
            play_result = call_connection.play_media(
                play_source=text_source,
                play_to="all"
            )
            
            logging.info("Played speech recognition prompt")
            
        except Exception as prompt_error:
            logging.warning(f"Failed to play speech recognition prompt: {str(prompt_error)}")
            _continue_conversation_without_recognition(client, call_connection_id)
        
    except Exception as e:
        logging.error(f"Failed to start speech recognition: {str(e)}")
        # Continue the conversation without speech recognition
        _continue_conversation_without_recognition(client, call_connection_id)


def _handle_speech_recognition_result(client: CallAutomationClient, call_connection_id: str, recognition_result: dict):
    """Process recognized speech and generate conversational response"""
    try:
        # Extract recognized text
        speech_result = recognition_result.get('speechResult', {})
        recognized_text = speech_result.get('speech', '').strip()
        
        logging.info(f"Recognized speech: '{recognized_text}'")
        
        if not recognized_text:
            logging.warning("No speech recognized, asking user to repeat")
            _play_retry_message(client, call_connection_id)
            return
        
        # Update conversation state
        if call_connection_id in CONVERSATION_STATE:
            state = CONVERSATION_STATE[call_connection_id]
            state['conversation_history'].append({
                'speaker': 'user', 
                'message': recognized_text
            })
            state['turn_count'] += 1
            
            # Generate conversational response
            response_text = _generate_conversational_response(recognized_text, state)
            
            # Play the response
            _play_conversational_response(client, call_connection_id, response_text)
            
            # Update conversation history with assistant response
            state['conversation_history'].append({
                'speaker': 'assistant', 
                'message': response_text
            })
            
    except Exception as e:
        logging.error(f"Error handling speech recognition result: {str(e)}")
        _play_error_message(client, call_connection_id)


def _generate_conversational_response(user_input: str, conversation_state: dict) -> str:
    """Generate an appropriate conversational response based on user input"""
    
    # Simple rule-based responses for healthcare context
    # In production, integrate with OpenAI or Azure OpenAI for intelligent responses
    
    user_input_lower = user_input.lower()
    turn_count = conversation_state['turn_count']
    
    # Healthcare-specific responses
    if any(word in user_input_lower for word in ['appointment', 'book', 'schedule']):
        return "I'd be happy to help you schedule an appointment. What type of appointment do you need, and what's your preferred date and time?"
    
    elif any(word in user_input_lower for word in ['pain', 'hurt', 'sick', 'feel']):
        return "I understand you're not feeling well. Can you tell me more about your symptoms? When did they start?"
    
    elif any(word in user_input_lower for word in ['prescription', 'medication', 'medicine', 'refill']):
        return "For prescription refills or medication questions, I can help connect you with our pharmacy team. What medication do you need assistance with?"
    
    elif any(word in user_input_lower for word in ['emergency', 'urgent', 'help']):
        return "If this is a medical emergency, please hang up and call 911 immediately. For urgent but non-emergency care, I can help you find the nearest urgent care facility."
    
    elif any(word in user_input_lower for word in ['yes', 'yeah', 'ok', 'okay']):
        return "Great! How else can I assist you today? I can help with appointments, general health questions, or connecting you with the right department."
    
    elif any(word in user_input_lower for word in ['no', 'nothing', "that's all"]):
        return "Thank you for calling! If you need any assistance in the future, please don't hesitate to reach out. Have a great day!"
    
    elif any(word in user_input_lower for word in ['hello', 'hi', 'hey']):
        return "Hello! I'm your healthcare assistant. How can I help you today? I can assist with appointments, answer general health questions, or direct your call to the appropriate department."
    
    # Generic conversational responses
    elif turn_count == 1:
        return "I understand. Can you provide more details about what you need help with today?"
    elif turn_count == 2:
        return "Thank you for that information. Is there anything specific I can help you with regarding your healthcare needs?"
    else:
        return "I want to make sure I'm helping you properly. Could you please clarify what type of assistance you're looking for?"


def _play_conversational_response(client: CallAutomationClient, call_connection_id: str, response_text: str):
    """Play the conversational response and then listen for next input"""
    try:
        call_connection = client.get_call_connection(call_connection_id)
        
        # Create text source for TTS
        text_source = TextSource(
            text=response_text,
            voice_name=TTS_VOICE
        )
        
        logging.info(f"Playing conversational response: '{response_text[:50]}...'")
        
        # Play the response
        play_result = call_connection.play_media(
            play_source=text_source,
            play_to="all"
        )
        
        # Update conversation state to indicate we're playing a response
        if call_connection_id in CONVERSATION_STATE:
            CONVERSATION_STATE[call_connection_id]['stage'] = 'playing_response'
        
        operation_id = getattr(play_result, 'operation_id', 'Unknown')
        logging.info(f"Conversational response playback initiated. Operation ID: {operation_id}")
        
    except Exception as e:
        logging.error(f"Failed to play conversational response: {str(e)}")


def _play_retry_message(client: CallAutomationClient, call_connection_id: str):
    """Play a message asking the user to repeat their input"""
    retry_message = "I'm sorry, I didn't catch that. Could you please repeat what you said?"
    _play_conversational_response(client, call_connection_id, retry_message)


def _play_error_message(client: CallAutomationClient, call_connection_id: str):
    """Play an error message when something goes wrong"""
    error_message = "I'm experiencing some technical difficulties. Let me transfer you to a human representative."
    _play_conversational_response(client, call_connection_id, error_message)


def get_conversation_state(call_connection_id: str) -> dict:
    """Get the current conversation state for a call"""
    return CONVERSATION_STATE.get(call_connection_id, {})


def clear_conversation_state(call_connection_id: str):
    """Clear conversation state when call ends"""
    if call_connection_id in CONVERSATION_STATE:
        del CONVERSATION_STATE[call_connection_id]
        logging.info(f"Cleared conversation state for call {call_connection_id}")


def _continue_conversation_without_recognition(client: CallAutomationClient, call_connection_id: str):
    """Continue conversation when speech recognition is not available"""
    try:
        # Play a message indicating we'll use a simple menu system
        menu_text = "I'm having trouble with speech recognition. Let me offer you some options. Press 1 for appointments, 2 for general questions, or 3 to speak with someone."
        
        call_connection = client.get_call_connection(call_connection_id)
        text_source = TextSource(
            text=menu_text,
            voice_name=TTS_VOICE
        )
        
        call_connection.play_media(
            play_source=text_source,
            play_to="all"
        )
        
        # Update conversation state
        if call_connection_id in CONVERSATION_STATE:
            CONVERSATION_STATE[call_connection_id]['stage'] = 'menu_presented'
        
        logging.info("Presented menu options due to speech recognition unavailability")
        
    except Exception as e:
        logging.error(f"Failed to continue conversation without recognition: {str(e)}")
