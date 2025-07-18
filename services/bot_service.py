"""
Bot Service Integration Module
Handles Azure Bot Service integration for initiating voice calls
"""

import os
import re
import json
import logging
from typing import Optional, Dict, Any

# Azure Bot Service imports
from botbuilder.core import TurnContext, ActivityHandler, MessageFactory
from botbuilder.schema import Activity, ChannelAccount, ActivityTypes
from botframework.connector import ConnectorClient
from botframework.connector.auth import MicrosoftAppCredentials

# OpenAI imports for bot intelligence
from openai import AzureOpenAI

# Import calling modules
from .phone_calling import create_pstn_call
from .voip_calling import create_voip_call

# Configuration
BOT_APP_ID = os.environ.get("BOT_APP_ID", "39188ba4-899a-4c87-a7a9-a35b52eb1891")
BOT_APP_PASSWORD = os.environ.get("BOT_APP_PASSWORD", "jz48Q~VxYZN_uLM6TgypoZbMUxSsHxCX1~oDta7y")
BOT_SERVICE_ENDPOINT = os.environ.get("BOT_SERVICE_ENDPOINT", "")

# OpenAI configuration for bot intelligence
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "2Xk8IVrD0Nh745tCPUWOhprKdAcMgyCKvUwXpHggf2WnsIHQoFfgJQQJ99BGACHYHv6XJ3w3AAABACOG3Zds")
OPENAI_ENDPOINT = os.environ.get("OPENAI_ENDPOINT", "https://healthcareagent-openai-ng01.openai.azure.com/")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# Voice and message defaults
TARGET_USER_ID = os.environ.get("TARGET_USER_ID", "")
WELCOME_MESSAGE = os.environ.get("WELCOME_MESSAGE", 
    "Hello! This is your Azure Communication Services assistant. The call connection is working perfectly. "
    "You can now hear automated messages through Azure's text-to-speech service. "
    "Thank you for testing the voice integration.")
TTS_VOICE = os.environ.get("TTS_VOICE", "en-US-JennyNeural")


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
    
    async def process_message(self, activity: dict) -> dict:
        """
        Process incoming bot message and handle call requests
        
        Args:
            activity: Bot activity data from Azure Bot Service
        
        Returns:
            Dict with response information
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
                    response_text = (f"I've initiated a {call_result['call_type']} call to {call_result['target']}. "
                                   f"Call ID: {call_result['call_id']}. "
                                   f"The call should connect shortly and you'll hear: '{call_result['message'][:50]}...'")
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
        Analyze message to determine if user wants to make a call
        Extracts phone numbers and call parameters
        
        Args:
            message: User message text
        
        Returns:
            Dict with call request analysis
        """
        message_lower = message.lower()
        
        # Check for call intent keywords
        call_keywords = ['call', 'phone', 'ring', 'dial', 'contact']
        should_call = any(keyword in message_lower for keyword in call_keywords)
        
        # Extract phone number if present
        phone_number = None
        phone_patterns = [
            r'\+\d{1,3}[\s-]?\d{3,14}',  # International format
            r'\+\d{1,3}[\s-]?\d{3,14}',  # International with separators
            r'\b\d{10,15}\b',  # 10-15 digits
        ]
        
        for pattern in phone_patterns:
            match = re.search(pattern, message)
            if match:
                phone_number = match.group().strip()
                # Ensure it starts with + for international format
                if not phone_number.startswith('+'):
                    # Add default country code if none provided
                    if len(phone_number) == 10:  # Assume US number if 10 digits
                        phone_number = '+1' + phone_number
                    elif len(phone_number) == 11 and phone_number.startswith('1'):  # US number with country code
                        phone_number = '+' + phone_number
                    else:
                        # Just add + and hope for the best
                        phone_number = '+' + phone_number
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
        
        Args:
            call_request: Call request details from message analysis
        
        Returns:
            Dict with call result information
        """
        try:
            # Determine target and call type
            target_phone = call_request.get('phone_number')
            target_user_id = TARGET_USER_ID
            
            # Decide whether to make PSTN or VoIP call
            use_pstn = bool(target_phone and target_phone.startswith('+'))
            
            if use_pstn:
                # PSTN call to phone number
                call_result = create_pstn_call(
                    target_phone=target_phone,
                    custom_message=call_request.get('custom_message'),
                    custom_voice=call_request.get('custom_voice')
                )
                
                if call_result['success']:
                    return {
                        'success': True,
                        'call_id': call_result['call_id'],
                        'message': call_result['message'],
                        'voice': call_result['voice'],
                        'call_type': 'PSTN',
                        'target': target_phone
                    }
                else:
                    return {
                        'success': False,
                        'error': call_result['error']
                    }
                    
            elif target_user_id:
                # VoIP call to Communication User
                call_result = create_voip_call(
                    target_user_id=target_user_id,
                    custom_message=call_request.get('custom_message'),
                    custom_voice=call_request.get('custom_voice')
                )
                
                if call_result['success']:
                    return {
                        'success': True,
                        'call_id': call_result['call_id'],
                        'message': call_result['message'],
                        'voice': call_result['voice'],
                        'call_type': 'VoIP',
                        'target': target_user_id[:20] + "..." if len(target_user_id) > 20 else target_user_id
                    }
                else:
                    return {
                        'success': False,
                        'error': call_result['error']
                    }
            else:
                return {'success': False, 'error': 'No valid target configured (no phone number or user ID)'}
                
        except Exception as e:
            logging.error(f"Error initiating call from bot: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _generate_response(self, user_message: str) -> str:
        """
        Generate intelligent response using OpenAI or fallback to basic responses
        
        Args:
            user_message: User's message text
        
        Returns:
            Response text for the user
        """
        try:
            # Try to use OpenAI if configured
            if self.openai_client:
                try:
                    response = self.openai_client.chat.completions.create(
                        model=OPENAI_MODEL,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are a helpful healthcare assistant that can make voice calls to patients. "
                                          "You help with appointments, patient care, and can initiate calls when requested. "
                                          "Keep responses concise and helpful. When users ask you to make calls, "
                                          "explain that you can call phone numbers or communication service users."
                            },
                            {
                                "role": "user",
                                "content": user_message
                            }
                        ],
                        max_tokens=150,
                        temperature=0.7
                    )
                    
                    return response.choices[0].message.content.strip()
                    
                except Exception as openai_error:
                    logging.error(f"OpenAI error: {str(openai_error)}")
                    return self._get_basic_response(user_message)
            else:
                return self._get_basic_response(user_message)
                
        except Exception as e:
            logging.error(f"Error generating response: {str(e)}")
            return self._get_basic_response(user_message)
    
    def _get_basic_response(self, user_message: str) -> str:
        """
        Basic response patterns when OpenAI is not available
        
        Args:
            user_message: User's message text
        
        Returns:
            Basic response text
        """
        message_lower = user_message.lower()
        
        if any(word in message_lower for word in ['hello', 'hi', 'hey', 'start']):
            return ("Hello! I'm your healthcare assistant. I can help you make voice calls to patients, "
                   "manage appointments, and answer healthcare questions. Just ask me to 'call the patient' "
                   "or provide a phone number when you need to initiate a voice call.")
        
        elif any(word in message_lower for word in ['help', 'what can you do', 'capabilities']):
            return ("I can help you with:\n- Making voice calls to patients\n- Managing patient appointments\n"
                   "- Accessing patient data\n- Healthcare assistance\n\n"
                   "To make a call, just say 'call the patient' or 'call +1234567890' with a phone number.")
        
        elif any(word in message_lower for word in ['thank', 'thanks', 'bye', 'goodbye']):
            return "You're welcome! Feel free to ask me to make calls or help with healthcare tasks anytime."
        
        else:
            return ("I understand you'd like assistance. I can make voice calls to patients and help with "
                   "healthcare tasks. Try saying 'call the patient' to initiate a voice call, or ask me "
                   "about appointments and patient data.")


def process_bot_message_sync(activity_data: dict) -> dict:
    """
    Synchronous wrapper for bot message processing
    Since Azure Functions v1 doesn't handle async easily, we simulate the async processing
    
    Args:
        activity_data: Bot activity data
    
    Returns:
        Dict with processing results
    """
    try:
        user_message = activity_data.get('text', '').strip()
        user_id = activity_data.get('from', {}).get('id', 'unknown')
        
        logging.info(f"Processing sync message from {user_id}: {user_message}")
        
        # Create bot instance
        bot = CallInitiatorBot()
        
        # Check if user is requesting a call
        call_request = bot._analyze_call_request(user_message)
        
        if call_request['should_call']:
            # Initiate the call synchronously
            call_result = initiate_call_sync(call_request)
            
            if call_result['success']:
                response_text = (f"I've initiated a {call_result['call_type']} call to {call_result['target']}. "
                               f"Call ID: {call_result['call_id']}. "
                               f"The call should connect shortly and you'll hear: '{call_result['message'][:50]}...'")
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
        logging.error(f"Error in sync processing: {str(e)}")
        return {
            'response_text': "I'm sorry, I encountered an error processing your request.",
            'call_initiated': False,
            'error': str(e)
        }


def initiate_call_sync(call_request: dict) -> dict:
    """
    Synchronous call initiation for bot requests
    
    Args:
        call_request: Call request details
    
    Returns:
        Dict with call result information
    """
    try:
        # Determine target and call type
        target_phone = call_request.get('phone_number')
        
        # Decide whether to make PSTN or VoIP call
        use_pstn = bool(target_phone and target_phone.startswith('+'))
        
        if use_pstn:
            # PSTN call to phone number
            call_result = create_pstn_call(
                target_phone=target_phone,
                custom_message=call_request.get('custom_message'),
                custom_voice=call_request.get('custom_voice')
            )
            
            if call_result['success']:
                return {
                    'success': True,
                    'call_id': call_result['call_id'],
                    'message': call_result['message'],
                    'voice': call_result['voice'],
                    'call_type': 'PSTN',
                    'target': target_phone
                }
            else:
                return {'success': False, 'error': call_result['error']}
                
        elif TARGET_USER_ID:
            # VoIP call to Communication User
            call_result = create_voip_call(
                target_user_id=TARGET_USER_ID,
                custom_message=call_request.get('custom_message'),
                custom_voice=call_request.get('custom_voice')
            )
            
            if call_result['success']:
                return {
                    'success': True,
                    'call_id': call_result['call_id'],
                    'message': call_result['message'],
                    'voice': call_result['voice'],
                    'call_type': 'VoIP',
                    'target': TARGET_USER_ID[:20] + "..." if len(TARGET_USER_ID) > 20 else TARGET_USER_ID
                }
            else:
                return {'success': False, 'error': call_result['error']}
        else:
            return {'success': False, 'error': 'No valid target configured'}
            
    except Exception as e:
        logging.error(f"Error initiating call: {str(e)}")
        return {'success': False, 'error': str(e)}


def generate_response_sync(user_message: str) -> str:
    """
    Synchronous response generation
    
    Args:
        user_message: User's message text
    
    Returns:
        Response text
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
                
                response = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a helpful healthcare assistant that can make voice calls to patients. "
                                      "Keep responses concise and helpful."
                        },
                        {
                            "role": "user",
                            "content": user_message
                        }
                    ],
                    max_tokens=150,
                    temperature=0.7
                )
                
                return response.choices[0].message.content.strip()
                
            except Exception as openai_error:
                logging.error(f"OpenAI error: {str(openai_error)}")
                return get_basic_response_sync(user_message)
        else:
            return get_basic_response_sync(user_message)
            
    except Exception as e:
        logging.error(f"Error generating response: {str(e)}")
        return get_basic_response_sync(user_message)


def get_basic_response_sync(user_message: str) -> str:
    """
    Basic response patterns when OpenAI is not available
    
    Args:
        user_message: User's message text
    
    Returns:
        Basic response text
    """
    message_lower = user_message.lower()
    
    if any(word in message_lower for word in ['hello', 'hi', 'hey', 'start']):
        return ("Hello! I'm your healthcare assistant. I can help you make voice calls to patients, "
               "manage appointments, and answer healthcare questions. Just ask me to 'call the patient' "
               "when you need to initiate a voice call.")
    
    elif any(word in message_lower for word in ['help', 'what can you do', 'capabilities']):
        return ("I can help you with:\n- Making voice calls to patients\n- Managing patient appointments\n"
               "- Accessing patient data\n- Healthcare assistance\n\n"
               "To make a call, just say 'call the patient' or 'make a voice call'.")
    
    elif any(word in message_lower for word in ['thank', 'thanks', 'bye', 'goodbye']):
        return "You're welcome! Feel free to ask me to make calls or help with healthcare tasks anytime."
    
    else:
        return ("I understand you'd like assistance. I can make voice calls to patients and help with "
               "healthcare tasks. Try saying 'call the patient' to initiate a voice call, or ask me "
               "about appointments and patient data.")


def create_bot_response(incoming_activity: dict, response_text: str) -> dict:
    """
    Create a properly formatted bot response activity
    
    Args:
        incoming_activity: The incoming activity from the user
        response_text: The response text to send back
    
    Returns:
        Formatted bot response activity
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


# Create global bot instance for use in function app
call_bot = CallInitiatorBot()
