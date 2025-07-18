"""
VoIP Calling Module
Handles VoIP calls to Communication Service users using Azure Communication Services
"""

import os
import json
import logging
from typing import Optional, Dict, Any

from azure.communication.callautomation import CallAutomationClient, TextSource
from azure.communication.identity import CommunicationUserIdentifier

# Configuration
ACS_CONNECTION_STRING = os.environ.get("ACS_CONNECTION_STRING", "")
COGNITIVE_SERVICES_ENDPOINT = os.environ.get("COGNITIVE_SERVICES_ENDPOINT", "").rstrip('/') if os.environ.get("COGNITIVE_SERVICES_ENDPOINT") else ""
TARGET_USER_ID = os.environ.get("TARGET_USER_ID", "")
CALLBACK_URL_BASE = os.environ.get("CALLBACK_URL_BASE", "")
WELCOME_MESSAGE = os.environ.get("WELCOME_MESSAGE", 
    "Hello! This is your Azure Communication Services assistant. The call connection is working perfectly. "
    "You can now hear automated messages through Azure's text-to-speech service. "
    "Thank you for testing the voice integration.")
TTS_VOICE = os.environ.get("TTS_VOICE", "en-US-JennyNeural")

# Global variables for temporary webhook data storage
TEMP_CUSTOM_MESSAGE = None
TEMP_CUSTOM_VOICE = None


def validate_voip_configuration() -> tuple[bool, str]:
    """
    Validate that all required VoIP configuration is present
    Returns: (is_valid, error_message)
    """
    if not ACS_CONNECTION_STRING:
        return False, "ACS_CONNECTION_STRING is required for VoIP calls"
    
    if not COGNITIVE_SERVICES_ENDPOINT:
        return False, "COGNITIVE_SERVICES_ENDPOINT is required for TTS functionality"
    
    return True, ""


def validate_user_id(user_id: str) -> tuple[bool, str]:
    """
    Validate user ID format for VoIP calls
    Returns: (is_valid, error_message)
    """
    if not user_id:
        return False, "User ID is required"
    
    # Basic validation for ACS user ID format
    if not user_id.startswith('8:acs:'):
        return False, "User ID should be in ACS format (starting with '8:acs:')"
    
    return True, ""


def create_voip_call(
    target_user_id: str,
    custom_message: Optional[str] = None,
    custom_voice: Optional[str] = None,
    callback_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a VoIP call to a Communication Service user
    
    Args:
        target_user_id: Target user ID in ACS format
        custom_message: Custom TTS message to play
        custom_voice: Custom voice for TTS
        callback_url: Callback URL for webhook events
    
    Returns:
        Dict with call result information
    """
    global TEMP_CUSTOM_MESSAGE, TEMP_CUSTOM_VOICE
    
    logging.info(f"Creating VoIP call to: {target_user_id}")
    
    # Validate configuration
    is_valid, error_msg = validate_voip_configuration()
    if not is_valid:
        return {
            "success": False,
            "error": f"Configuration error: {error_msg}",
            "call_type": "VoIP"
        }
    
    # Validate user ID
    is_valid, error_msg = validate_user_id(target_user_id)
    if not is_valid:
        return {
            "success": False,
            "error": f"User ID validation error: {error_msg}",
            "call_type": "VoIP"
        }
    
    try:
        # Initialize ACS client
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
        
        # Create communication user identifier
        target_user = CommunicationUserIdentifier(target_user_id)
        
        # Store custom settings for webhook
        TEMP_CUSTOM_MESSAGE = custom_message or WELCOME_MESSAGE
        TEMP_CUSTOM_VOICE = custom_voice or TTS_VOICE
        
        # Determine callback URL
        if not callback_url:
            if CALLBACK_URL_BASE:
                callback_url = f"https://{CALLBACK_URL_BASE}/api/CallWebhook"
            else:
                callback_url = "http://localhost:7071/api/CallWebhook"
        
        logging.info(f"Using callback URL: {callback_url}")
        
        # Create the VoIP call
        call_result = client.create_call(
            target_participant=target_user,
            callback_url=callback_url,
            cognitive_services_endpoint=COGNITIVE_SERVICES_ENDPOINT
        )
        
        call_connection_id = call_result.call_connection_id if hasattr(call_result, 'call_connection_id') else 'Unknown'
        
        logging.info(f"VoIP call created successfully. Call ID: {call_connection_id}")
        
        return {
            "success": True,
            "call_id": call_connection_id,
            "user_id": target_user_id,
            "message": TEMP_CUSTOM_MESSAGE,
            "voice": TEMP_CUSTOM_VOICE,
            "webhook_url": callback_url,
            "call_type": "VoIP"
        }
        
    except Exception as e:
        logging.error(f"Failed to create VoIP call: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to create VoIP call: {str(e)}",
            "user_id": target_user_id,
            "call_type": "VoIP"
        }


def handle_voip_webhook_event(event: Dict[str, Any]) -> bool:
    """
    Handle a single VoIP webhook event
    
    Args:
        event: Event data from Azure Communication Services
    
    Returns:
        True if event was handled successfully, False otherwise
    """
    global TEMP_CUSTOM_MESSAGE, TEMP_CUSTOM_VOICE
    
    try:
        event_type = event.get('type', 'Unknown')
        call_connection_id = event.get('data', {}).get('callConnectionId', 'Unknown')
        
        logging.info(f"Processing VoIP event: {event_type}, Call ID: {call_connection_id}")
        
        # Initialize ACS client for event handling
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
        
        if event_type == 'Microsoft.Communication.CallConnected':
            logging.info(f"VoIP call connected! Playing TTS message...")
            
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
                play_result = call_connection.play_media_to_all(
                    play_source=text_source
                )
                
                operation_id = getattr(play_result, 'operation_id', 'Unknown')
                logging.info(f"TTS playback initiated. Operation ID: {operation_id}")
                
                # Clear temp variables after use
                TEMP_CUSTOM_MESSAGE = None
                TEMP_CUSTOM_VOICE = None
                
            except Exception as play_error:
                logging.error(f"Error playing TTS: {str(play_error)}")
                return False
                
        elif event_type == 'Microsoft.Communication.CallDisconnected':
            disconnect_reason = event.get('data', {}).get('callConnectionId', 'Unknown reason')
            logging.info(f"VoIP call disconnected. Call ID: {call_connection_id}, Reason: {disconnect_reason}")
            
            # Clear temp variables on disconnect
            TEMP_CUSTOM_MESSAGE = None
            TEMP_CUSTOM_VOICE = None
            
        elif event_type == 'Microsoft.Communication.PlayCompleted':
            logging.info(f"TTS playback completed for call {call_connection_id}")
            
        elif event_type == 'Microsoft.Communication.PlayFailed':
            play_error = event.get('data', {}).get('resultInformation', {}).get('message', 'Unknown error')
            logging.error(f"TTS playback failed for call {call_connection_id}: {play_error}")
            
        elif event_type == 'Microsoft.Communication.CallEstablished':
            logging.info(f"VoIP call established for call {call_connection_id}")
            
        elif event_type == 'Microsoft.Communication.ParticipantsUpdated':
            participants = event.get('data', {}).get('participants', [])
            logging.info(f"Participants updated for call {call_connection_id}, count: {len(participants)}")
            
        else:
            logging.info(f"Unhandled VoIP event type: {event_type}")
        
        return True
        
    except Exception as e:
        logging.error(f"Error handling VoIP webhook event: {str(e)}")
        return False


def create_test_voip_call_no_webhook(
    target_user_id: Optional[str] = None,
    custom_message: Optional[str] = None,
    custom_voice: Optional[str] = None,
    delay_seconds: int = 3
) -> Dict[str, Any]:
    """
    Create a VoIP call without webhook for testing purposes
    Uses threading to play TTS after delay
    
    Args:
        target_user_id: Target user ID (uses default if not provided)
        custom_message: Custom TTS message
        custom_voice: Custom voice for TTS
        delay_seconds: Delay before playing message
    
    Returns:
        Dict with call result information
    """
    import threading
    import time
    
    logging.info('Creating test VoIP call without webhook dependencies')
    
    # Use provided user ID or default
    user_id = target_user_id or TARGET_USER_ID
    
    # Validate configuration
    is_valid, error_msg = validate_voip_configuration()
    if not is_valid:
        return {
            "success": False,
            "error": f"Configuration error: {error_msg}",
            "call_type": "VoIP-Test"
        }
    
    if not user_id:
        return {
            "success": False,
            "error": "TARGET_USER_ID not configured and no user_id provided",
            "call_type": "VoIP-Test"
        }
    
    try:
        # Initialize ACS client
        client = CallAutomationClient.from_connection_string(ACS_CONNECTION_STRING)
        target_user = CommunicationUserIdentifier(user_id)
        
        # Use a dummy callback URL since we're not using webhooks
        callback_uri = "http://localhost:7071/api/DummyWebhook"
        
        # Create the call
        call_result = client.create_call(
            target_participant=target_user,
            callback_url=callback_uri,
            cognitive_services_endpoint=COGNITIVE_SERVICES_ENDPOINT
        )
        
        call_connection_id = call_result.call_connection_id if hasattr(call_result, 'call_connection_id') else 'Unknown'
        
        logging.info(f"Test VoIP call created. Call ID: {call_connection_id}")
        
        # Function to play TTS after delay
        def play_tts_delayed():
            try:
                time.sleep(delay_seconds)
                
                # Get call connection
                call_connection = client.get_call_connection(call_connection_id)
                
                # Use custom message or default
                message_to_play = custom_message or WELCOME_MESSAGE
                voice_to_use = custom_voice or TTS_VOICE
                
                # Create text source
                text_source = TextSource(
                    text=message_to_play,
                    voice_name=voice_to_use
                )
                
                logging.info(f"Playing delayed TTS message: '{message_to_play[:50]}...'")
                
                # Play the message
                play_result = call_connection.play_media_to_all(
                    play_source=text_source
                )
                
                logging.info(f"Delayed TTS playback initiated successfully")
                
            except Exception as e:
                logging.error(f"Error in delayed TTS playback: {str(e)}")
        
        # Start the delayed TTS in a separate thread
        threading.Thread(target=play_tts_delayed, daemon=True).start()
        
        return {
            "success": True,
            "call_id": call_connection_id,
            "user_id": user_id,
            "message": custom_message or WELCOME_MESSAGE,
            "voice": custom_voice or TTS_VOICE,
            "delay": delay_seconds,
            "call_type": "VoIP-Test",
            "note": "Using delayed TTS without webhook"
        }
        
    except Exception as e:
        logging.error(f"Failed to create test VoIP call: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to create test VoIP call: {str(e)}",
            "user_id": user_id,
            "call_type": "VoIP-Test"
        }


def clear_temp_variables():
    """Clear temporary variables used for webhook communication"""
    global TEMP_CUSTOM_MESSAGE, TEMP_CUSTOM_VOICE
    TEMP_CUSTOM_MESSAGE = None
    TEMP_CUSTOM_VOICE = None
