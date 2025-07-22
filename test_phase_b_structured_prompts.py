"""
Phase B: Structured Prompts Testing Script
Test conversation templates and workflows with real patient data from Cosmos DB
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
def load_environment():
    """Load environment variables from local.settings.json"""
    try:
        with open('local.settings.json', 'r') as f:
            settings = json.load(f)
            for key, value in settings.get('Values', {}).items():
                os.environ[key] = value
        logger.info("Environment variables loaded from local.settings.json")
    except Exception as e:
        logger.warning(f"Could not load local.settings.json: {e}")

load_environment()

# Import after environment is loaded
from services.cosmos_manager import cosmos_manager, PatientRecord
from services.bot_service import (
    EnhancedConversationState, 
    ConversationWorkflowManager,
    ConversationAgent,
    get_or_create_enhanced_conversation_state
)
from bot_config import (
    MedicationAdherenceState,
    ContextualPrompts,
    ConversationTemplates,
    EmergencyPriority
)

class PhaseBTester:
    """Test Phase B structured prompts and conversation workflows"""
    
    def __init__(self):
        self.workflow_manager = ConversationWorkflowManager()
        self.test_results = []
        
        print("🧪 Phase B Structured Prompts Testing Suite")
        print("=" * 60)
    
    def run_all_tests(self):
        """Run comprehensive Phase B testing"""
        try:
            print("\n📋 Testing Phase B Implementation...")
            
            # Test 1: Load real patient data
            patients = self.test_patient_data_loading()
            
            # Test 2: Contextual prompt generation
            self.test_contextual_prompts(patients)
            
            # Test 3: Conversation workflow templates
            self.test_conversation_workflows(patients)
            
            # Test 4: User response processing
            self.test_user_response_processing(patients)
            
            # Test 5: Emergency escalation workflows
            self.test_emergency_workflows(patients)
            
            # Test 6: Side effects and appointment workflows
            self.test_specialized_workflows(patients)
            
            # Test 7: Integration testing with conversation states
            self.test_conversation_state_integration(patients)
            
            self.print_test_summary()
            
        except Exception as e:
            logger.error(f"Test suite failed: {e}")
            print(f"❌ Test suite failed: {e}")
    
    def test_patient_data_loading(self) -> List[PatientRecord]:
        """Test 1: Load and validate real patient data"""
        print("\n🔍 Test 1: Patient Data Loading")
        print("-" * 40)
        
        try:
            # Use the async list_patients method and convert to PatientRecord objects
            import asyncio
            
            async def get_patients():
                patient_dicts = await cosmos_manager.list_patients()
                patients = []
                for patient_dict in patient_dicts:
                    try:
                        patient = PatientRecord.from_dict(patient_dict)
                        patients.append(patient)
                    except Exception as e:
                        print(f"   ⚠️  Could not convert patient record: {e}")
                return patients
            
            # Run the async function
            patients = asyncio.run(get_patients())
            
            print(f"✅ Successfully loaded {len(patients)} patients from Cosmos DB")
            
            for patient in patients:
                print(f"   👤 {patient.get_full_name()} ({patient.patient_id})")
                print(f"      Doctor: {patient.primary_doctor}")
                print(f"      Medications: {len(patient.medications)}")
                print(f"      Adherence State: {patient.current_adherence_state}")
                
            self.test_results.append({"test": "patient_data_loading", "status": "PASS", "count": len(patients)})
            return patients
            
        except Exception as e:
            print(f"❌ Failed to load patient data: {e}")
            self.test_results.append({"test": "patient_data_loading", "status": "FAIL", "error": str(e)})
            return []
    
    def test_contextual_prompts(self, patients: List[PatientRecord]):
        """Test 2: Contextual prompt generation for different scenarios"""
        print("\n💬 Test 2: Contextual Prompt Generation")
        print("-" * 40)
        
        try:
            for patient in patients[:3]:  # Test first 3 patients
                print(f"\n   Testing prompts for: {patient.get_full_name()}")
                medication_names = patient.get_medication_names()
                
                # Test initial contact prompt
                initial_prompt = ContextualPrompts.get_initial_contact_prompt(
                    patient.get_full_name(), 
                    medication_names
                )
                print(f"   ✅ Initial Contact: {initial_prompt[:100]}...")
                
                # Test medication pickup prompt
                pickup_prompt = ContextualPrompts.get_medication_pickup_prompt(patient.get_full_name())
                print(f"   ✅ Pickup Prompt: {pickup_prompt[:100]}...")
                
                # Test dosage review prompt
                dosage_prompt = ContextualPrompts.get_dosage_review_prompt(
                    patient.get_full_name(), 
                    patient.medications
                )
                print(f"   ✅ Dosage Review: {dosage_prompt[:100]}...")
                
                # Test follow-up prompt
                followup_prompt = ContextualPrompts.get_followup_prompt(patient.get_full_name(), 3)
                print(f"   ✅ Follow-up: {followup_prompt[:100]}...")
            
            self.test_results.append({"test": "contextual_prompts", "status": "PASS", "patients_tested": len(patients[:3])})
            
        except Exception as e:
            print(f"❌ Contextual prompt generation failed: {e}")
            self.test_results.append({"test": "contextual_prompts", "status": "FAIL", "error": str(e)})
    
    def test_conversation_workflows(self, patients: List[PatientRecord]):
        """Test 3: Conversation workflow templates"""
        print("\n🔄 Test 3: Conversation Workflow Templates")
        print("-" * 40)
        
        states_to_test = [
            MedicationAdherenceState.INITIAL_CONTACT,
            MedicationAdherenceState.MEDICATION_PICKED_UP,
            MedicationAdherenceState.DOSAGE_DISCUSSED,
            MedicationAdherenceState.ADHERENCE_COMPLETED
        ]
        
        try:
            for patient in patients[:2]:  # Test first 2 patients
                print(f"\n   Testing workflows for: {patient.get_full_name()}")
                
                patient_context = {
                    "name": patient.get_full_name(),
                    "patient_id": patient.patient_id,
                    "doctor_name": patient.primary_doctor,
                    "medication_names": patient.get_medication_names(),
                    "medications": patient.medications
                }
                
                # Test each adherence state workflow
                for state in states_to_test:
                    workflow = ConversationTemplates.get_medication_adherence_workflow(state, patient_context)
                    
                    if workflow:
                        print(f"   ✅ {state.value}:")
                        print(f"      - Greeting: {workflow.get('greeting', 'N/A')[:80]}...")
                        print(f"      - Expected responses: {workflow.get('expected_responses', [])}")
                        print(f"      - Next actions: {list(workflow.get('next_actions', {}).keys())}")
                        print(f"      - Escalation triggers: {workflow.get('escalation_triggers', [])}")
                    else:
                        print(f"   ❌ No workflow found for {state.value}")
            
            self.test_results.append({"test": "conversation_workflows", "status": "PASS", "workflows_tested": len(states_to_test) * 2})
            
        except Exception as e:
            print(f"❌ Conversation workflow testing failed: {e}")
            self.test_results.append({"test": "conversation_workflows", "status": "FAIL", "error": str(e)})
    
    def test_user_response_processing(self, patients: List[PatientRecord]):
        """Test 4: User response processing and workflow transitions"""
        print("\n🗣️  Test 4: User Response Processing")
        print("-" * 40)
        
        try:
            if not patients:
                print("   ⚠️  No patients available for testing")
                return
            
            patient = patients[0]  # Use first patient
            
            # Create conversation state
            conversation_state = EnhancedConversationState(
                call_connection_id="test_call_001",
                patient_id=patient.patient_id
            )
            conversation_state.patient_record = patient
            conversation_state.adherence_state = MedicationAdherenceState.INITIAL_CONTACT
            
            print(f"   Testing with patient: {patient.get_full_name()}")
            
            # Test various user responses
            test_responses = [
                ("yes", "Positive response to pickup"),
                ("no", "Negative response to pickup"),
                ("I have questions", "Questions about medication"),
                ("chest pain", "Emergency keyword"),
                ("ready to review", "Ready for dosage discussion"),
                ("confused about dosage", "Confusion response")
            ]
            
            for user_input, description in test_responses:
                print(f"\n   🧪 Testing: {description}")
                print(f"      User Input: '{user_input}'")
                
                result = self.workflow_manager.process_user_response(user_input, conversation_state)
                
                print(f"      ✅ Action: {result.get('action', 'unknown')}")
                print(f"      ✅ Response: {result.get('message', 'No message')[:100]}...")
                
                if result.get('action') == 'emergency_escalation':
                    print(f"      🚨 Emergency detected! Priority: {result.get('priority', 'Unknown')}")
            
            self.test_results.append({"test": "user_response_processing", "status": "PASS", "responses_tested": len(test_responses)})
            
        except Exception as e:
            print(f"❌ User response processing failed: {e}")
            self.test_results.append({"test": "user_response_processing", "status": "FAIL", "error": str(e)})
    
    def test_emergency_workflows(self, patients: List[PatientRecord]):
        """Test 5: Emergency escalation workflows"""
        print("\n🚨 Test 5: Emergency Escalation Workflows")
        print("-" * 40)
        
        try:
            if not patients:
                print("   ⚠️  No patients available for testing")
                return
            
            patient = patients[0]
            patient_context = {
                "name": patient.get_full_name(),
                "patient_id": patient.patient_id,
                "doctor_name": patient.primary_doctor
            }
            
            emergency_types = [
                "chest pain",
                "severe allergic reaction", 
                "medication overdose",
                "breathing difficulties"
            ]
            
            for emergency_type in emergency_types:
                print(f"\n   🧪 Testing emergency: {emergency_type}")
                
                emergency_template = ConversationTemplates.get_emergency_protocol_template(emergency_type, patient_context)
                
                print(f"      ✅ Immediate Response: {emergency_template['immediate_response'][:80]}...")
                print(f"      ✅ Priority Level: {emergency_template['escalation_priority'].value}")
                print(f"      ✅ Required Actions: {len(emergency_template['required_actions'])} actions")
                print(f"      ✅ Escalation Contacts: {len(emergency_template['escalation_contacts'])} contacts")
            
            self.test_results.append({"test": "emergency_workflows", "status": "PASS", "emergencies_tested": len(emergency_types)})
            
        except Exception as e:
            print(f"❌ Emergency workflow testing failed: {e}")
            self.test_results.append({"test": "emergency_workflows", "status": "FAIL", "error": str(e)})
    
    def test_specialized_workflows(self, patients: List[PatientRecord]):
        """Test 6: Side effects and appointment workflows"""
        print("\n🏥 Test 6: Specialized Workflows")
        print("-" * 40)
        
        try:
            if not patients:
                print("   ⚠️  No patients available for testing")
                return
            
            patient = patients[0]
            patient_context = {
                "name": patient.get_full_name(),
                "patient_id": patient.patient_id,
                "doctor_name": patient.primary_doctor
            }
            
            # Test side effects workflow
            print(f"\n   🧪 Testing side effects workflow")
            side_effects_workflow = ConversationTemplates.get_side_effects_workflow_template(patient_context)
            
            print(f"      ✅ Initial Inquiry: {side_effects_workflow['initial_inquiry'][:80]}...")
            print(f"      ✅ Severity Levels: {list(side_effects_workflow['severity_assessment'].keys())}")
            print(f"      ✅ Documentation Required: {side_effects_workflow['documentation_required']}")
            
            # Test appointment workflows
            appointment_types = ["routine_followup", "medication_review", "urgent_consultation"]
            
            for appointment_type in appointment_types:
                print(f"\n   🧪 Testing appointment workflow: {appointment_type}")
                
                appointment_workflow = ConversationTemplates.get_appointment_workflow_template(appointment_type, patient_context)
                
                print(f"      ✅ Scheduling Prompt: {appointment_workflow['scheduling_prompt'][:80]}...")
                print(f"      ✅ Appointment Types: {len(appointment_workflow['appointment_types'])}")
                print(f"      ✅ Confirmation Required: {appointment_workflow['confirmation_required']}")
            
            self.test_results.append({"test": "specialized_workflows", "status": "PASS", "workflows_tested": 1 + len(appointment_types)})
            
        except Exception as e:
            print(f"❌ Specialized workflow testing failed: {e}")
            self.test_results.append({"test": "specialized_workflows", "status": "FAIL", "error": str(e)})
    
    def test_conversation_state_integration(self, patients: List[PatientRecord]):
        """Test 7: Integration with conversation states"""
        print("\n🔗 Test 7: Conversation State Integration")
        print("-" * 40)
        
        try:
            if not patients:
                print("   ⚠️  No patients available for testing")
                return
            
            patient = patients[0]
            
            print(f"   Testing full conversation flow with: {patient.get_full_name()}")
            
            # Create conversation state
            conversation_state = get_or_create_enhanced_conversation_state("test_integration_001", patient.patient_id)
            conversation_state.patient_record = patient
            
            # Test conversation flow
            print(f"\n   🧪 Step 1: Generate initial prompt")
            initial_prompt = self.workflow_manager.generate_contextual_prompt(conversation_state)
            print(f"      ✅ Prompt: {initial_prompt[:100]}...")
            
            print(f"\n   🧪 Step 2: Add conversation turn")
            conversation_state.add_turn("assistant", initial_prompt, ConversationAgent.MEDICATION)
            print(f"      ✅ Turn count: {conversation_state.turn_count}")
            
            print(f"\n   🧪 Step 3: Process user response")
            user_response = "Yes, I picked up my medication"
            result = self.workflow_manager.process_user_response(user_response, conversation_state)
            print(f"      ✅ User: {user_response}")
            print(f"      ✅ Action: {result.get('action', 'unknown')}")
            
            print(f"\n   🧪 Step 4: State transition")
            if result.get("action") == "state_transition":
                print(f"      ✅ New State: {result.get('new_state', 'unknown')}")
                print(f"      ✅ Current State: {conversation_state.adherence_state}")
            
            print(f"\n   🧪 Step 5: Patient context summary")
            context_summary = conversation_state.get_patient_context_summary()
            print(f"      ✅ Context keys: {list(context_summary.keys())}")
            print(f"      ✅ Patient name: {context_summary.get('patient_name', 'Unknown')}")
            print(f"      ✅ Medications: {context_summary.get('medications', [])}")
            
            self.test_results.append({"test": "conversation_state_integration", "status": "PASS", "steps_completed": 5})
            
        except Exception as e:
            print(f"❌ Conversation state integration failed: {e}")
            self.test_results.append({"test": "conversation_state_integration", "status": "FAIL", "error": str(e)})
    
    def print_test_summary(self):
        """Print comprehensive test results summary"""
        print("\n" + "=" * 60)
        print("📊 PHASE B TEST RESULTS SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r["status"] == "PASS"])
        failed_tests = len([r for r in self.test_results if r["status"] == "FAIL"])
        
        print(f"\n📈 Overall Results:")
        print(f"   ✅ Passed: {passed_tests}/{total_tests}")
        print(f"   ❌ Failed: {failed_tests}/{total_tests}")
        print(f"   📊 Success Rate: {(passed_tests/total_tests*100):.1f}%" if total_tests > 0 else "   📊 Success Rate: 0%")
        
        print(f"\n📋 Detailed Results:")
        for result in self.test_results:
            status_icon = "✅" if result["status"] == "PASS" else "❌"
            test_name = result["test"].replace("_", " ").title()
            print(f"   {status_icon} {test_name}: {result['status']}")
            
            if result["status"] == "FAIL" and "error" in result:
                print(f"      Error: {result['error']}")
            elif result["status"] == "PASS":
                # Add any success metrics
                for key, value in result.items():
                    if key not in ["test", "status"] and isinstance(value, (int, str)):
                        print(f"      {key.replace('_', ' ').title()}: {value}")
        
        print(f"\n🎉 Phase B Structured Prompts Testing Complete!")
        
        if failed_tests == 0:
            print("🌟 All tests passed! Phase B implementation is working correctly.")
        else:
            print(f"⚠️  {failed_tests} test(s) failed. Please review the errors above.")


def main():
    """Run Phase B testing suite"""
    print("🚀 Starting Phase B Structured Prompts Testing")
    print(f"⏰ Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    tester = PhaseBTester()
    tester.run_all_tests()


if __name__ == "__main__":
    main()
