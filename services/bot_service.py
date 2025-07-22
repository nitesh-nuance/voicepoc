"""
Bot Service Integration Module
Handles Azure Bot Service integration for initiating voice calls
Enhanced with medication adherence tracking and bot.js-style patient interactions
"""

import os
import re
import json
import time
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

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

# Import Phase A and Phase B enhancements
from bot_config import (
    MedicationAdherenceState, 
    EmergencyPriority, 
    bot_config, 
    shared_instructions,
    ContextualPrompts,
    ConversationTemplates  # Phase B addition
)
from .cosmos_manager import cosmos_manager, PatientRecord, MedicationInfo

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


# Phase A: Enhanced Conversation State with Medication Adherence
class ConversationAgent(Enum):
    """Healthcare conversation agents for specialized interactions"""
    TRIAGE = "triage"
    GENERAL_INQUIRY = "general_inquiry" 
    APPOINTMENT = "appointment"
    MEDICATION = "medication"
    EMERGENCY = "emergency"


@dataclass
class ConversationTurn:
    """Represents a single turn in the conversation with enhanced context"""
    speaker: str  # 'user' or 'assistant'
    message: str
    timestamp: float
    agent: Optional[ConversationAgent] = None
    confidence: float = 1.0
    patient_context: Optional[Dict[str, Any]] = None
    adherence_state: Optional[MedicationAdherenceState] = None
    emergency_level: EmergencyPriority = EmergencyPriority.NONE


@dataclass
class EnhancedConversationState:
    """Enhanced conversation state with medication adherence tracking"""
    call_connection_id: str
    active_agent: ConversationAgent = ConversationAgent.TRIAGE
    conversation_history: List[ConversationTurn] = field(default_factory=list)
    
    # Patient context from PatientRecord
    patient_record: Optional[PatientRecord] = None
    patient_id: Optional[str] = None
    
    # Medication adherence workflow
    adherence_state: MedicationAdherenceState = MedicationAdherenceState.INITIAL_CONTACT
    medication_pickup_status: Dict[str, bool] = field(default_factory=dict)
    dosage_discussion_status: Dict[str, bool] = field(default_factory=dict)
    
    # Emergency safety tracking
    emergency_detected: bool = False
    emergency_level: EmergencyPriority = EmergencyPriority.NONE
    emergency_timestamp: Optional[float] = None
    safety_escalation_triggered: bool = False
    
    # Conversation flow tracking
    completion_status: Dict[str, bool] = field(default_factory=dict)
    call_metadata: Dict[str, Any] = field(default_factory=dict)
    turn_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)
    
    def add_turn(self, speaker: str, message: str, agent: Optional[ConversationAgent] = None, 
                 confidence: float = 1.0, emergency_level: EmergencyPriority = EmergencyPriority.NONE):
        """Add a new conversation turn with enhanced context"""
        turn = ConversationTurn(
            speaker=speaker,
            message=message,
            timestamp=time.time(),
            agent=agent or self.active_agent,
            confidence=confidence,
            patient_context=self.get_patient_context_summary(),
            adherence_state=self.adherence_state,
            emergency_level=emergency_level
        )
        self.conversation_history.append(turn)
        self.turn_count += 1
        self.last_updated = time.time()
        
        # Update active agent if specified
        if agent and agent != self.active_agent:
            self.active_agent = agent
            self.call_metadata['agent_transitions'] = self.call_metadata.get('agent_transitions', 0) + 1
        
        # Update emergency status
        if emergency_level != EmergencyPriority.NONE:
            self.emergency_detected = True
            self.emergency_level = emergency_level
            self.emergency_timestamp = time.time()
    
    def get_patient_context_summary(self) -> Dict[str, Any]:
        """Get summary of patient context for conversation turn"""
        if not self.patient_record:
            return {}
        
        return {
            'patient_name': self.patient_record.get_full_name(),
            'primary_doctor': self.patient_record.primary_doctor,
            'medications': self.patient_record.get_medication_names(),
            'adherence_state': self.adherence_state.value,
            'emergency_contacts': {
                'name': self.patient_record.emergency_contact_name,
                'phone': self.patient_record.emergency_contact_phone
            }
        }
    
    def get_recent_context(self, num_turns: int = 3) -> List[Dict[str, Any]]:
        """Get recent conversation turns with enhanced context"""
        recent_turns = self.conversation_history[-num_turns:] if self.conversation_history else []
        return [
            {
                "speaker": turn.speaker,
                "message": turn.message,
                "agent": turn.agent.value if turn.agent else "unknown",
                "timestamp": turn.timestamp,
                "adherence_state": turn.adherence_state.value if turn.adherence_state else None,
                "emergency_level": turn.emergency_level.value,
                "patient_context": turn.patient_context
            }
            for turn in recent_turns
        ]
    
    def update_adherence_state(self, new_state: MedicationAdherenceState):
        """Update medication adherence state"""
        self.adherence_state = new_state
        if self.patient_record:
            self.patient_record.update_adherence_state(new_state)
        self.last_updated = time.time()
    
    def mark_medication_discussed(self, medication_name: str):
        """Mark medication as discussed"""
        self.dosage_discussion_status[medication_name] = True
        if self.patient_record:
            self.patient_record.mark_dosage_discussed(medication_name)
        self.last_updated = time.time()
    
    def trigger_emergency_protocol(self, emergency_level: EmergencyPriority = EmergencyPriority.HIGH):
        """Trigger emergency safety protocol"""
        self.emergency_detected = True
        self.emergency_level = emergency_level
        self.emergency_timestamp = time.time()
        self.safety_escalation_triggered = True
        
        # Log emergency in patient record
        if self.patient_record:
            emergency_note = f"EMERGENCY DETECTED: Level {emergency_level.value} at {datetime.now().isoformat()}"
            self.patient_record.add_conversation_note(emergency_note)
            self.patient_record.escalation_history.append(emergency_note)


# Global conversation state storage (in production, use Redis or Azure Storage)
ENHANCED_CONVERSATION_STATES: Dict[str, EnhancedConversationState] = {}


class ConversationWorkflowManager:
    """Phase B: Manages structured conversation workflows and templates"""
    
    def __init__(self, cosmos_manager_instance=None):
        self.cosmos_manager = cosmos_manager_instance or cosmos_manager
        self.logger = logging.getLogger(__name__)
    
    def get_workflow_for_state(self, patient_state: MedicationAdherenceState, patient_context: dict) -> dict:
        """Get appropriate workflow template for current patient state"""
        return ConversationTemplates.get_medication_adherence_workflow(patient_state, patient_context)
    
    def generate_contextual_prompt(self, conversation_state: EnhancedConversationState) -> str:
        """Generate contextual prompt based on current conversation state"""
        if not conversation_state.patient_record:
            return "Hello, how can I help you today?"
        
        patient_context = {
            "name": conversation_state.patient_record.get_full_name(),
            "patient_id": conversation_state.patient_id,
            "doctor_name": conversation_state.patient_record.primary_doctor,
            "medication_names": conversation_state.patient_record.get_medication_names(),
            "medications": conversation_state.patient_record.medications
        }
        
        # Get workflow template for current state
        workflow = self.get_workflow_for_state(conversation_state.adherence_state, patient_context)
        
        if workflow and "greeting" in workflow:
            return workflow["greeting"]
        
        # Fallback to basic contextual prompt
        return ContextualPrompts.get_initial_contact_prompt(
            patient_context["name"],
            patient_context["medication_names"]
        )
    
    def process_user_response(self, user_input: str, conversation_state: EnhancedConversationState) -> Dict[str, Any]:
        """Process user response and determine next workflow action"""
        if not conversation_state.patient_record:
            return {"action": "collect_patient_info", "message": "Could you please provide your patient ID?"}
        
        patient_context = {
            "name": conversation_state.patient_record.get_full_name(),
            "patient_id": conversation_state.patient_id,
            "doctor_name": conversation_state.patient_record.primary_doctor,
            "medication_names": conversation_state.patient_record.get_medication_names(),
            "medications": conversation_state.patient_record.medications
        }
        
        # Get current workflow
        workflow = self.get_workflow_for_state(conversation_state.adherence_state, patient_context)
        
        if not workflow:
            return {"action": "continue_conversation", "message": "I understand. Please continue."}
        
        # Check for emergency triggers
        emergency_triggers = workflow.get("escalation_triggers", [])
        if self._detect_emergency_keywords(user_input, emergency_triggers):
            return self._handle_emergency_escalation(user_input, conversation_state, patient_context)
        
        # Analyze user response against expected responses
        expected_responses = workflow.get("expected_responses", [])
        detected_response = self._classify_user_response(user_input, expected_responses)
        
        # Determine next action based on workflow
        next_actions = workflow.get("next_actions", {})
        next_action = next_actions.get(detected_response, "continue_conversation")
        
        # Handle state transitions
        if isinstance(next_action, MedicationAdherenceState):
            conversation_state.update_adherence_state(next_action)
            return {
                "action": "state_transition",
                "new_state": next_action,
                "message": self.generate_contextual_prompt(conversation_state)
            }
        
        # Handle specific actions
        return self._handle_workflow_action(next_action, conversation_state, patient_context)
    
    def _detect_emergency_keywords(self, user_input: str, triggers: List[str]) -> bool:
        """Detect emergency keywords in user input"""
        user_input_lower = user_input.lower()
        for trigger in triggers:
            if trigger.lower() in user_input_lower:
                return True
        
        # Additional emergency keywords
        emergency_keywords = [
            "chest pain", "can't breathe", "allergic reaction", "overdose",
            "severe pain", "bleeding", "unconscious", "911", "emergency"
        ]
        
        for keyword in emergency_keywords:
            if keyword in user_input_lower:
                return True
        
        return False
    
    def _classify_user_response(self, user_input: str, expected_responses: List[str]) -> str:
        """Classify user response against expected response patterns"""
        user_input_lower = user_input.lower().strip()
        
        # Direct matches
        for expected in expected_responses:
            if expected.lower() in user_input_lower:
                return expected
        
        # Synonym matching
        synonyms = {
            "yes": ["yeah", "yep", "sure", "correct", "right", "okay", "ok", "affirmative"],
            "no": ["nah", "nope", "incorrect", "wrong", "negative", "not yet"],
            "ready": ["prepared", "set", "good to go", "let's do it"],
            "questions": ["question", "ask", "confused", "unclear", "don't understand"],
            "understood": ["got it", "clear", "makes sense", "understand", "comprehend"]
        }
        
        for expected in expected_responses:
            if expected in synonyms:
                for synonym in synonyms[expected]:
                    if synonym in user_input_lower:
                        return expected
        
        # Default classification
        return "other"
    
    def _handle_emergency_escalation(self, user_input: str, conversation_state: EnhancedConversationState, patient_context: dict) -> Dict[str, Any]:
        """Handle emergency escalation workflow"""
        emergency_template = ConversationTemplates.get_emergency_protocol_template("medical emergency", patient_context)
        conversation_state.trigger_emergency_protocol(EmergencyPriority.HIGH)
        
        return {
            "action": "emergency_escalation",
            "priority": "HIGH",
            "message": emergency_template["immediate_response"],
            "required_actions": emergency_template["required_actions"],
            "escalation_contacts": emergency_template["escalation_contacts"]
        }
    
    def _handle_workflow_action(self, action: str, conversation_state: EnhancedConversationState, patient_context: dict) -> Dict[str, Any]:
        """Handle specific workflow actions"""
        if action == "schedule_pickup_reminder":
            return {
                "action": "schedule_reminder",
                "message": f"I'll schedule a reminder for you to pick up your medication. Would tomorrow work for you?",
                "reminder_type": "medication_pickup"
            }
        
        elif action == "schedule_dosage_review":
            return {
                "action": "schedule_review",
                "message": f"That's fine, {patient_context['name']}. When would be a better time to discuss your medication schedule?",
                "review_type": "dosage_instructions"
            }
        
        elif action == "address_questions":
            return {
                "action": "answer_questions",
                "message": "I'm here to help. What specific questions do you have about your medication?",
                "context": "medication_questions"
            }
        
        elif action == "clarify_dosage":
            medications = patient_context.get("medications", [])
            if medications:
                med_details = "\n".join([f"- {med.name}: {med.dosage} {med.frequency}" for med in medications])
                message = f"Let me clarify your medication schedule:\n{med_details}\n\nWhich part would you like me to explain further?"
            else:
                message = "Let me clarify your medication instructions. Which medication would you like me to explain?"
            
            return {
                "action": "clarify_instructions",
                "message": message,
                "context": "dosage_clarification"
            }
        
        elif action == "schedule_followup":
            return {
                "action": "schedule_followup",
                "message": f"I'll schedule a follow-up call in {bot_config.adherence_follow_up_days} days to check how you're doing with your medication. Is that okay?",
                "followup_days": bot_config.adherence_follow_up_days
            }
        
        else:
            return {
                "action": "continue_conversation",
                "message": "I understand. Is there anything else I can help you with regarding your medication?"
            }
    
    def get_side_effects_workflow(self, patient_context: dict) -> dict:
        """Get side effects management workflow"""
        return ConversationTemplates.get_side_effects_workflow_template(patient_context)
    
    def get_appointment_workflow(self, appointment_type: str, patient_context: dict) -> dict:
        """Get appointment scheduling workflow"""
        return ConversationTemplates.get_appointment_workflow_template(appointment_type, patient_context)


# Global workflow manager instance
conversation_workflow_manager = ConversationWorkflowManager()


def get_or_create_enhanced_conversation_state(call_connection_id: str, patient_id: Optional[str] = None) -> EnhancedConversationState:
    """Get existing enhanced conversation state or create new one with patient context"""
    if call_connection_id not in ENHANCED_CONVERSATION_STATES:
        state = EnhancedConversationState(call_connection_id=call_connection_id, patient_id=patient_id)
        
        # Load patient record if patient_id provided
        if patient_id and cosmos_manager.is_connected():
            try:
                # Note: This would be async in a real implementation
                # For now, we'll handle this in the calling functions
                state.patient_id = patient_id
                logging.info(f"Enhanced conversation state created for patient {patient_id}")
            except Exception as e:
                logging.warning(f"Could not load patient record {patient_id}: {str(e)}")
        
        ENHANCED_CONVERSATION_STATES[call_connection_id] = state
        logging.info(f"Created enhanced conversation state for call {call_connection_id}")
    
    return ENHANCED_CONVERSATION_STATES[call_connection_id]


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
                
                return response.choices[0].message.content.strip() or ""
                
            except Exception as openai_error:
                logging.error(f"OpenAI error: {str(openai_error)}")
                return get_basic_response_sync(user_message)
        else:
            return get_basic_response_sync(user_message)
            
    except Exception as e:
        logging.error(f"Error generating response: {str(e)}")
        return get_basic_response_sync(user_message)


def generate_agent_response_sync(user_input: str, call_connection_id: str, conversation_state: EnhancedConversationState) -> str:
    """
    Phase B: Generate intelligent agent response using structured prompts and workflow management
    
    Args:
        user_input: User's input text
        call_connection_id: Call connection identifier
        conversation_state: Enhanced conversation state with patient context
    
    Returns:
        Structured response based on conversation workflow
    """
    try:
        logging.info(f"Generating agent response for call {call_connection_id}: '{user_input[:50]}...'")
        
        # Add user turn to conversation history
        conversation_state.add_turn("user", user_input, ConversationAgent.MEDICATION)
        
        # Use workflow manager to process user response
        workflow_result = conversation_workflow_manager.process_user_response(user_input, conversation_state)
        
        # Get the response message
        agent_response = workflow_result.get("message", "I understand. How can I help you further?")
        
        # Handle different workflow actions
        action = workflow_result.get("action", "continue_conversation")
        
        if action == "emergency_escalation":
            # Emergency detected - prioritize immediate response
            emergency_response = workflow_result.get("message", "I'm concerned about what you're experiencing. Please call 911 immediately.")
            conversation_state.trigger_emergency_protocol(EmergencyPriority.HIGH)
            logging.warning(f"Emergency escalation triggered for call {call_connection_id}")
            agent_response = emergency_response
            
        elif action == "state_transition":
            # State changed - generate new contextual prompt
            new_state = workflow_result.get("new_state")
            if new_state:
                logging.info(f"State transition: {conversation_state.adherence_state} -> {new_state}")
                agent_response = workflow_result.get("message", conversation_workflow_manager.generate_contextual_prompt(conversation_state))
            
        elif action in ["schedule_reminder", "schedule_review", "schedule_followup"]:
            # Scheduling actions - provide helpful response
            scheduling_message = workflow_result.get("message", "I'll help you schedule that.")
            agent_response = scheduling_message
            
        elif action == "clarify_instructions":
            # Clarification needed - provide detailed explanation
            clarification = workflow_result.get("message", "Let me clarify that for you.")
            agent_response = clarification
            
        # Add agent response to conversation history
        conversation_state.add_turn("assistant", agent_response, conversation_state.active_agent)
        
        # Enhance response with OpenAI if available and not an emergency
        if action != "emergency_escalation" and OPENAI_API_KEY and OPENAI_ENDPOINT:
            try:
                # Get patient context for personalization
                patient_context = conversation_state.get_patient_context_summary()
                patient_name = patient_context.get('patient_name', '')
                
                # Create enhanced prompt with Phase B context
                system_prompt = f"""You are a professional healthcare voice assistant conducting a medication adherence follow-up call.

PATIENT CONTEXT:
- Patient: {patient_name}
- Doctor: {patient_context.get('primary_doctor', 'Dr. Smith')}
- Current State: {conversation_state.adherence_state.value}
- Medications: {', '.join(patient_context.get('medications', []))}

CONVERSATION GUIDELINES:
- Keep responses under 30 seconds when spoken
- Use the patient's name naturally
- Be professional, empathetic, and supportive
- Focus on medication adherence and safety
- Follow the structured workflow for this state

The system has generated this response based on workflow analysis: "{agent_response}"

Please refine this response to be more natural and conversational while maintaining the core message and medical professionalism."""

                client = AzureOpenAI(
                    api_key=OPENAI_API_KEY,
                    api_version="2024-02-01",
                    azure_endpoint=OPENAI_ENDPOINT
                )
                
                response = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_input}
                    ],
                    max_tokens=200,
                    temperature=0.7
                )
                
                enhanced_response = response.choices[0].message.content
                if enhanced_response and enhanced_response.strip():
                    agent_response = enhanced_response.strip()
                    logging.info(f"Enhanced response with OpenAI for call {call_connection_id}")
                
            except Exception as openai_error:
                logging.warning(f"OpenAI enhancement failed: {str(openai_error)}, using workflow response")
        
        logging.info(f"Generated agent response for {call_connection_id}: '{agent_response[:100]}...'")
        return agent_response
        
    except Exception as e:
        logging.error(f"Error in generate_agent_response_sync: {str(e)}")
        
        # Fallback to basic response
        try:
            return generate_response_sync(user_input)
        except Exception as fallback_error:
            logging.error(f"Fallback response failed: {str(fallback_error)}")
            return "I understand. Could you please repeat that or let me know if you need any help with your medication?"


def get_or_create_conversation_state(call_connection_id: str, patient_id: Optional[str] = None) -> EnhancedConversationState:
    """
    Get or create enhanced conversation state - wrapper function for phone_calling.py compatibility
    
    Args:
        call_connection_id: Call connection identifier
        patient_id: Optional patient identifier
    
    Returns:
        Enhanced conversation state
    """
    return get_or_create_enhanced_conversation_state(call_connection_id, patient_id)


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
