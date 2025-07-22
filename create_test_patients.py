"""
Script to create test patients in Cosmos DB using connection details from local.settings.json
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timedelta

# Set up logging
logging.basicConfig(level=logging.INFO)

def load_environment_from_local_settings():
    """Load environment variables from local.settings.json"""
    try:
        with open('local.settings.json', 'r') as f:
            settings = json.load(f)
            
        # Set environment variables from local.settings.json
        for key, value in settings['Values'].items():
            os.environ[key] = value
            
        # Fix the Cosmos DB connection string format if needed
        cosmos_conn = os.environ.get('COSMOS_CONNECTION_STRING', '')
        if cosmos_conn and not cosmos_conn.startswith('AccountEndpoint='):
            # The connection string in local.settings.json appears to be missing the AccountEndpoint prefix
            fixed_cosmos_conn = f"AccountEndpoint={cosmos_conn}"
            os.environ['COSMOS_CONNECTION_STRING'] = fixed_cosmos_conn
            print(f"Fixed Cosmos DB connection string format")
            
        print("Environment variables loaded from local.settings.json")
        print(f"Cosmos DB endpoint configured: {cosmos_conn[:50]}...")
        return True
        
    except FileNotFoundError:
        print("local.settings.json not found")
        return False
    except Exception as e:
        print(f"Error loading local.settings.json: {str(e)}")
        return False

# Load environment variables
if not load_environment_from_local_settings():
    print("Failed to load environment variables. Exiting.")
    exit(1)

# Now import the modules that depend on environment variables
from services.cosmos_manager import cosmos_manager, PatientRecord, MedicationInfo
from bot_config import MedicationAdherenceState
from test_patient_data import TEST_PATIENTS

async def create_patients_in_cosmos():
    """Create test patients in Cosmos DB"""
    
    if not cosmos_manager.is_connected():
        print("❌ Cosmos DB is not connected. Please check your connection string.")
        return False
    
    print("✅ Cosmos DB connection successful!")
    print(f"Database: {cosmos_manager.database.id if cosmos_manager.database else 'Not connected'}")
    
    successful_creates = 0
    failed_creates = 0
    
    for patient in TEST_PATIENTS:
        try:
            print(f"\n📝 Creating patient: {patient.get_full_name()}")
            print(f"   Patient ID: {patient.id}")
            print(f"   Doctor: {patient.primary_doctor}")
            print(f"   Medications: {', '.join(patient.get_medication_names())}")
            print(f"   Adherence State: {patient.adherence_state.value}")
            
            # Create patient record in Cosmos DB
            result = await cosmos_manager.create_patient_record(patient)
            
            print(f"✅ Successfully created patient: {patient.get_full_name()}")
            successful_creates += 1
            
        except Exception as e:
            if "already exists" in str(e):
                print(f"⚠️  Patient {patient.get_full_name()} already exists - skipping")
                # Try to update instead
                try:
                    await cosmos_manager.update_patient_record(patient)
                    print(f"✅ Updated existing patient: {patient.get_full_name()}")
                    successful_creates += 1
                except Exception as update_e:
                    print(f"❌ Failed to update patient {patient.get_full_name()}: {str(update_e)}")
                    failed_creates += 1
            else:
                print(f"❌ Failed to create patient {patient.get_full_name()}: {str(e)}")
                failed_creates += 1
    
    print(f"\n📊 Summary:")
    print(f"   ✅ Successful: {successful_creates}")
    print(f"   ❌ Failed: {failed_creates}")
    print(f"   📋 Total: {len(TEST_PATIENTS)}")
    
    return successful_creates > 0

async def verify_patients_in_cosmos():
    """Verify the created patients by listing them"""
    try:
        print(f"\n🔍 Verifying patients in Cosmos DB...")
        patients = await cosmos_manager.list_patients(limit=10)
        
        print(f"Found {len(patients)} patients in database:")
        for patient_data in patients:
            patient = PatientRecord.from_dict(patient_data)
            print(f"   👤 {patient.get_full_name()} ({patient.id})")
            print(f"      Doctor: {patient.primary_doctor}")
            print(f"      Medications: {len(patient.medications)}")
            print(f"      State: {patient.adherence_state.value}")
            print(f"      Last Contact: {patient.last_contact_date or 'Never'}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error verifying patients: {str(e)}")
        return False

async def test_patient_operations():
    """Test some patient operations"""
    try:
        print(f"\n🧪 Testing patient operations...")
        
        # Test getting a specific patient
        test_patient_id = "patient_001"
        patient = await cosmos_manager.get_patient_record(test_patient_id)
        print(f"✅ Retrieved patient: {patient.get_full_name()}")
        
        # Test updating adherence state
        print(f"   Current adherence state: {patient.adherence_state.value}")
        
        # Add a conversation note
        note = f"Test conversation note added at {datetime.now().isoformat()}"
        await cosmos_manager.add_patient_conversation_note(test_patient_id, note)
        print(f"✅ Added conversation note")
        
        # Verify the update
        updated_patient = await cosmos_manager.get_patient_record(test_patient_id)
        print(f"✅ Patient has {len(updated_patient.conversation_notes)} conversation notes")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing patient operations: {str(e)}")
        return False

async def main():
    """Main function to create and test patients"""
    print("🚀 Starting Cosmos DB Patient Creation Script")
    print("=" * 50)
    
    # Create patients
    success = await create_patients_in_cosmos()
    
    if success:
        # Verify patients were created
        await verify_patients_in_cosmos()
        
        # Test some operations
        await test_patient_operations()
        
        print(f"\n🎉 Script completed successfully!")
        print(f"   You can now use these test patients for Phase A testing")
        print(f"   Database: nursevoiceagentdb")
        print(f"   Container: patients")
        
    else:
        print(f"\n❌ Script failed - no patients were created")

if __name__ == "__main__":
    asyncio.run(main())
