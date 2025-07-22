"""
Bot Configuration Module
Bot.js-style settings for medication adherence and personalized healthcare interactions
"""

import os
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

# Bot.js-style configuration settings
@dataclass
class BotConfiguration:
    """Configuration settings matching bot.js behavior"""
    
    # Healthcare facility information
    facility_name: str = "General Hospital"
    facility_phone: str = "+1-555-HOSPITAL"
    
    # Default doctor information (can be overridden per patient)
    default_doctor_name: str = "Dr. Smith"
    default_doctor_specialty: str = "Primary Care"
    
    # Medication adherence workflow settings
    medication_pickup_reminder_days: int = 3
    dosage_discussion_required: bool = True
    adherence_follow_up_days: int = 7
    
    # Emergency safety protocols
    emergency_escalation_enabled: bool = True
    emergency_phone: str = "911"
    urgent_care_phone: str = "+1-555-URGENT"
    
    # Conversation flow settings
    max_conversation_turns: int = 15
    escalation_threshold_turns: int = 8
    context_memory_turns: int = 5
    
    # Voice and tone settings
    professional_tone: bool = True
    empathetic_responses: bool = True
    medication_safety_emphasis: bool = True


class MedicationAdherenceState(Enum):
    """Medication adherence workflow states matching bot.js behavior"""
    INITIAL_CONTACT = "initial_contact"
    MEDICATION_PICKED_UP = "medicationPickedUp"
    DOSAGE_DISCUSSED = "dosageDiscussed"
    ADHERENCE_COMPLETED = "adherenceCompleted"
    SCHEDULING_STARTED = "schedulingStarted"
    FOLLOW_UP_SCHEDULED = "followUpScheduled"
    WORKFLOW_COMPLETE = "workflowComplete"


class EmergencyPriority(Enum):
    """Emergency priority levels for safety protocols"""
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SharedInstructions:
    """Shared instruction templates matching bot.js structured prompts"""
    
    # Core conversation guidelines
    base_instructions: str = """
    You are a professional healthcare voice assistant conducting post-discharge medication adherence follow-up calls.
    
    CORE PRINCIPLES:
    - Patient safety is the absolute priority
    - Maintain professional, empathetic, and supportive tone
    - Use personalized context (patient name, doctor name, medications)
    - Follow structured medication adherence workflow
    - Escalate emergencies immediately
    - Keep responses conversational and under 30 seconds when spoken
    """
    
    # Emergency safety protocol
    emergency_protocol: str = """
    EMERGENCY SAFETY PROTOCOL:
    If patient mentions ANY of these symptoms, immediately recommend calling 911:
    - Chest pain or pressure
    - Difficulty breathing or shortness of breath
    - Severe allergic reaction (swelling, rash, difficulty swallowing)
    - Signs of stroke (confusion, slurred speech, weakness)
    - Loss of consciousness or severe dizziness
    - Severe bleeding
    - Severe medication reaction
    
    Emergency response format:
    "I'm concerned about the symptoms you're describing. Please hang up and call 911 immediately, or have someone call for you. This requires immediate medical attention."
    """
    
    # Medication adherence workflow
    adherence_workflow: str = """
    MEDICATION ADHERENCE WORKFLOW:
    1. INITIAL_CONTACT: Warm greeting with patient name and purpose
    2. MEDICATION_PICKED_UP: Verify prescription pickup from pharmacy
    3. DOSAGE_DISCUSSED: Review dosage, timing, and instructions
    4. ADHERENCE_COMPLETED: Address questions, concerns, side effects
    5. SCHEDULING_STARTED: Offer follow-up appointment if needed
    6. FOLLOW_UP_SCHEDULED: Confirm next steps and contact information
    7. WORKFLOW_COMPLETE: Professional closing with safety reminders
    """
    
    # Personalization templates
    greeting_template: str = "Hello {patient_name}, this is your healthcare assistant calling from {facility_name} regarding your recent discharge and new medications prescribed by {doctor_name}."
    
    medication_inquiry_template: str = "I wanted to check in about the {medication_name} that {doctor_name} prescribed for you. Have you been able to pick this up from the pharmacy yet?"
    
    closing_template: str = "Thank you {patient_name}. Remember, if you have any urgent concerns about your medications, please don't hesitate to call {facility_phone} or your doctor {doctor_name} directly."


class ContextualPrompts:
    """Context-aware prompt templates for different conversation scenarios"""
    
    @staticmethod
    def get_triage_prompt(patient_name: str, doctor_name: str, medications: Optional[List[str]] = None) -> str:
        """Generate triage-specific prompt with patient context"""
        meds_context = f" You are following up on medications: {', '.join(medications)}." if medications else ""
        
        return f"""
        You are conducting a post-discharge triage call for {patient_name}, who was recently treated by {doctor_name}.{meds_context}
        
        TRIAGE PRIORITIES:
        1. Assess immediate health concerns or symptoms
        2. Identify medication-related issues or reactions
        3. Determine urgency level and appropriate care pathway
        4. Route to medication adherence workflow if stable
        5. Escalate emergencies immediately per safety protocol
        
        Use warm, professional tone. Address patient by name. Reference their doctor appropriately.
        """
    
    @staticmethod
    def get_medication_prompt(patient_name: str, doctor_name: str, current_state: MedicationAdherenceState, medications: Optional[List[str]] = None) -> str:
        """Generate medication-specific prompt based on adherence state"""
        meds_context = f"Medications: {', '.join(medications)}. " if medications else ""
        
        state_guidance = {
            MedicationAdherenceState.INITIAL_CONTACT: "Begin with warm greeting and explain purpose of call.",
            MedicationAdherenceState.MEDICATION_PICKED_UP: "Verify pharmacy pickup and any pickup challenges.",
            MedicationAdherenceState.DOSAGE_DISCUSSED: "Review dosage timing, instructions, and patient understanding.",
            MedicationAdherenceState.ADHERENCE_COMPLETED: "Address concerns, side effects, and adherence barriers.",
            MedicationAdherenceState.SCHEDULING_STARTED: "Offer follow-up appointments and ongoing support.",
        }
        
        current_guidance = state_guidance.get(current_state, "Continue medication adherence discussion.")
        
        return f"""
        You are conducting medication adherence follow-up for {patient_name}, prescribed by {doctor_name}.
        {meds_context}
        
        CURRENT WORKFLOW STATE: {current_state.value}
        CURRENT FOCUS: {current_guidance}
        
        MEDICATION ADHERENCE GOALS:
        - Ensure patient has picked up medications
        - Verify understanding of dosage and timing
        - Address any concerns or side effects
        - Support adherence and answer questions
        - Schedule follow-up care if needed
        
        Maintain professional, supportive tone. Use patient name naturally in conversation.
        """
    
    @staticmethod
    def get_appointment_prompt(patient_name: str, doctor_name: str, appointment_type: str = "follow-up") -> str:
        """Generate appointment-specific prompt with patient context"""
        return f"""
        You are scheduling a {appointment_type} appointment for {patient_name} with {doctor_name}.
        
        APPOINTMENT SCHEDULING PRIORITIES:
        1. Determine appropriate appointment type and urgency
        2. Check patient availability and preferences
        3. Coordinate with provider schedule
        4. Confirm appointment details and preparation instructions
        5. Provide clear next steps and contact information
        
        Reference the patient's recent discharge and ongoing medication needs.
        Maintain warm, helpful tone throughout scheduling process.
        """
    
    # Phase B: Enhanced Contextual Prompts
    @staticmethod
    def get_initial_contact_prompt(patient_name: str, medication_names: list) -> str:
        """Get prompt for initial patient contact"""
        med_list = ", ".join(medication_names) if len(medication_names) > 1 else medication_names[0]
        return f"""
Hello {patient_name}, this is your healthcare assistant calling about your medication {med_list}.
I'm here to help ensure you're taking your medication safely and effectively.
Can you confirm you've picked up your prescription from the pharmacy?
"""
    
    @staticmethod
    def get_medication_pickup_prompt(patient_name: str) -> str:
        """Get prompt for medication pickup confirmation"""
        return f"""
Thank you {patient_name}. Now that you have your medication, I'd like to review the dosage instructions with you.
This will help ensure you're taking it correctly and safely.
Are you ready to go over the dosage information?
"""
    
    @staticmethod
    def get_dosage_review_prompt(patient_name: str, medications: list) -> str:
        """Get prompt for dosage review"""
        return f"""
Great {patient_name}! Let me review your medication schedule:
{chr(10).join([f"- {med.name}: {med.dosage} {med.frequency}" for med in medications])}

Do you have any questions about when or how to take these medications?
"""
    
    @staticmethod
    def get_followup_prompt(patient_name: str, last_contact_days: int) -> str:
        """Get prompt for follow-up calls"""
        return f"""
Hello {patient_name}, this is your healthcare assistant following up on your medication adherence.
It's been {last_contact_days} days since our last conversation.
How are you feeling with your current medication routine?
"""

    @staticmethod
    def get_emergency_escalation_prompt(patient_name: str, concern_type: str) -> str:
        """Get prompt for emergency situations requiring escalation"""
        return f"""
{patient_name}, I understand you're experiencing {concern_type}. 
This is important and I want to make sure you get the right help immediately.
I'm going to connect you with a healthcare professional right away.
Please stay on the line while I transfer your call.
"""
    
    @staticmethod
    def get_medication_reminder_prompt(patient_name: str, medication_name: str, time_info: str) -> str:
        """Get prompt for medication reminders"""
        return f"""
Hello {patient_name}, this is a friendly reminder about your {medication_name}.
It's time for your {time_info} dose.
Have you taken your medication today as prescribed?
"""
    
    @staticmethod
    def get_side_effects_inquiry_prompt(patient_name: str) -> str:
        """Get prompt for side effects discussion"""
        return f"""
{patient_name}, I'd like to check how you're feeling with your current medications.
Are you experiencing any side effects or unusual symptoms since starting your treatment?
This information helps us ensure your medication is working well for you.
"""
    
    @staticmethod
    def get_appointment_scheduling_prompt(patient_name: str, doctor_name: str) -> str:
        """Get prompt for appointment scheduling"""
        return f"""
{patient_name}, {doctor_name} would like to schedule a follow-up appointment with you
to review your medication progress and overall health.
Would you like me to help you schedule an appointment for next week?
"""
    
    @staticmethod
    def get_medication_completion_prompt(patient_name: str, medication_name: str, doctor_name: str) -> str:
        """Get prompt when medication course is completed"""
        return f"""
Congratulations {patient_name}! You've completed your {medication_name} treatment course.
{doctor_name} will review your progress and determine if any follow-up treatment is needed.
How are you feeling overall after completing this medication?
"""


class ConversationTemplates:
    """Phase B: Structured conversation templates for different scenarios"""
    
    @staticmethod
    def get_medication_adherence_workflow(patient_state: MedicationAdherenceState, patient_context: dict) -> dict:
        """Get structured workflow for medication adherence conversations"""
        workflows = {
            MedicationAdherenceState.INITIAL_CONTACT: {
                "greeting": ContextualPrompts.get_initial_contact_prompt(
                    patient_context.get("name", ""),
                    patient_context.get("medication_names", [])
                ),
                "expected_responses": ["yes", "no", "not yet", "picked up"],
                "next_actions": {
                    "yes": MedicationAdherenceState.MEDICATION_PICKED_UP,
                    "no": "schedule_pickup_reminder",
                    "not_yet": "schedule_pickup_reminder"
                },
                "escalation_triggers": ["emergency", "urgent", "pain", "reaction"],
                "conversation_flow": {
                    "max_turns": 3,
                    "retry_prompts": [
                        "I want to make sure I understand correctly - have you been able to pick up your prescription?",
                        "Let me ask differently - did you go to the pharmacy to get your medication?"
                    ]
                }
            },
            
            MedicationAdherenceState.MEDICATION_PICKED_UP: {
                "greeting": ContextualPrompts.get_medication_pickup_prompt(
                    patient_context.get("name", "")
                ),
                "expected_responses": ["yes", "ready", "no", "later"],
                "next_actions": {
                    "yes": MedicationAdherenceState.DOSAGE_DISCUSSED,
                    "ready": MedicationAdherenceState.DOSAGE_DISCUSSED,
                    "no": "schedule_dosage_review",
                    "later": "schedule_dosage_review"
                },
                "escalation_triggers": ["confused", "concerned", "side effects"],
                "conversation_flow": {
                    "max_turns": 2,
                    "retry_prompts": [
                        "Would now be a good time to quickly review how to take your medication?"
                    ]
                }
            },
            
            MedicationAdherenceState.DOSAGE_DISCUSSED: {
                "greeting": ContextualPrompts.get_dosage_review_prompt(
                    patient_context.get("name", ""),
                    patient_context.get("medications", [])
                ),
                "expected_responses": ["understood", "questions", "clear", "confused"],
                "next_actions": {
                    "understood": MedicationAdherenceState.ADHERENCE_COMPLETED,
                    "clear": MedicationAdherenceState.ADHERENCE_COMPLETED,
                    "questions": "address_questions",
                    "confused": "clarify_dosage"
                },
                "escalation_triggers": ["allergic", "reaction", "emergency"],
                "conversation_flow": {
                    "max_turns": 5,
                    "retry_prompts": [
                        "Do you have any specific questions about when or how to take these medications?",
                        "Is there anything about the medication schedule that seems unclear?"
                    ]
                }
            },
            
            MedicationAdherenceState.ADHERENCE_COMPLETED: {
                "greeting": f"Thank you {patient_context.get('name', '')}. You're all set with your medication plan. I'll check in with you in a few days to see how you're doing.",
                "expected_responses": ["thank you", "okay", "questions"],
                "next_actions": {
                    "thank_you": "schedule_followup",
                    "okay": "schedule_followup",
                    "questions": "address_questions"
                },
                "escalation_triggers": ["emergency", "urgent"],
                "conversation_flow": {
                    "max_turns": 2,
                    "closing_prompts": [
                        "Remember, if you have any concerns about your medication, please call us immediately.",
                        "Take care, and we'll talk again soon."
                    ]
                }
            }
        }
        
        return workflows.get(patient_state, {})
    
    @staticmethod
    def get_emergency_protocol_template(emergency_type: str, patient_context: dict) -> dict:
        """Get structured template for emergency situations"""
        return {
            "immediate_response": ContextualPrompts.get_emergency_escalation_prompt(
                patient_context.get("name", ""),
                emergency_type
            ),
            "escalation_priority": EmergencyPriority.HIGH,
            "required_actions": [
                "transfer_to_healthcare_professional",
                "log_emergency_contact",
                "notify_primary_doctor",
                "document_incident"
            ],
            "documentation_template": {
                "timestamp": "auto_generated",
                "patient_id": patient_context.get("patient_id"),
                "emergency_type": emergency_type,
                "agent_response": "immediate_escalation",
                "outcome": "pending_human_intervention"
            },
            "follow_up_required": True,
            "escalation_contacts": [
                {"type": "emergency", "number": "911"},
                {"type": "urgent_care", "number": bot_config.urgent_care_phone},
                {"type": "primary_doctor", "number": patient_context.get("doctor_phone", bot_config.facility_phone)}
            ]
        }
    
    @staticmethod
    def get_side_effects_workflow_template(patient_context: dict) -> dict:
        """Get structured template for side effects management"""
        return {
            "initial_inquiry": ContextualPrompts.get_side_effects_inquiry_prompt(
                patient_context.get("name", "")
            ),
            "severity_assessment": {
                "mild": {
                    "response": "Thank you for sharing that. These sound like manageable side effects.",
                    "next_action": "provide_management_tips",
                    "escalation": False
                },
                "moderate": {
                    "response": "I'm glad you told me about these symptoms. Let me connect you with a nurse.",
                    "next_action": "schedule_nurse_consultation",
                    "escalation": True
                },
                "severe": {
                    "response": "These symptoms concern me. You need immediate medical attention.",
                    "next_action": "emergency_escalation",
                    "escalation": True
                }
            },
            "documentation_required": True,
            "follow_up_timeline": "24_hours"
        }
    
    @staticmethod
    def get_appointment_workflow_template(appointment_type: str, patient_context: dict) -> dict:
        """Get structured template for appointment scheduling"""
        return {
            "scheduling_prompt": ContextualPrompts.get_appointment_scheduling_prompt(
                patient_context.get("name", ""),
                patient_context.get("doctor_name", "your doctor")
            ),
            "appointment_types": {
                "routine_followup": {
                    "urgency": "low",
                    "timeframe": "1-2 weeks",
                    "duration": "15-30 minutes"
                },
                "medication_review": {
                    "urgency": "moderate",
                    "timeframe": "3-5 days",
                    "duration": "20-45 minutes"
                },
                "urgent_consultation": {
                    "urgency": "high",
                    "timeframe": "same_day",
                    "duration": "30-60 minutes"
                }
            },
            "confirmation_required": True,
            "reminder_preferences": ["phone", "email", "text"]
        }


# Global configuration instance
bot_config = BotConfiguration()

# Environment variable overrides
def load_config_from_env():
    """Load configuration values from environment variables if available"""
    global bot_config
    
    # Facility information
    if os.environ.get("FACILITY_NAME"):
        bot_config.facility_name = os.environ.get("FACILITY_NAME", bot_config.facility_name)
    if os.environ.get("FACILITY_PHONE"):
        bot_config.facility_phone = os.environ.get("FACILITY_PHONE", bot_config.facility_phone)
    
    # Doctor information
    if os.environ.get("DEFAULT_DOCTOR_NAME"):
        bot_config.default_doctor_name = os.environ.get("DEFAULT_DOCTOR_NAME", bot_config.default_doctor_name)
    if os.environ.get("DEFAULT_DOCTOR_SPECIALTY"):
        bot_config.default_doctor_specialty = os.environ.get("DEFAULT_DOCTOR_SPECIALTY", bot_config.default_doctor_specialty)
    
    # Emergency contacts
    if os.environ.get("EMERGENCY_PHONE"):
        bot_config.emergency_phone = os.environ.get("EMERGENCY_PHONE", bot_config.emergency_phone)
    if os.environ.get("URGENT_CARE_PHONE"):
        bot_config.urgent_care_phone = os.environ.get("URGENT_CARE_PHONE", bot_config.urgent_care_phone)
    
    # Workflow settings
    if os.environ.get("MEDICATION_PICKUP_REMINDER_DAYS"):
        try:
            bot_config.medication_pickup_reminder_days = int(os.environ.get("MEDICATION_PICKUP_REMINDER_DAYS", str(bot_config.medication_pickup_reminder_days)))
        except (ValueError, TypeError):
            pass  # Keep default value
    if os.environ.get("ADHERENCE_FOLLOW_UP_DAYS"):
        try:
            bot_config.adherence_follow_up_days = int(os.environ.get("ADHERENCE_FOLLOW_UP_DAYS", str(bot_config.adherence_follow_up_days)))
        except (ValueError, TypeError):
            pass  # Keep default value

# Load configuration from environment on import
load_config_from_env()

# Shared instruction templates
shared_instructions = SharedInstructions()
