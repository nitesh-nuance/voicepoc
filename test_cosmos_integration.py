#!/usr/bin/env python3
"""
Test script for Azure Cosmos DB integration
This script tests the basic Cosmos DB connectivity and CRUD operations
"""

import json
import time
import requests
import sys

# Test configuration
BASE_URL = "http://localhost:7071/api"  # Local Azure Functions endpoint
TEST_PATIENT_ID = f"test_patient_{int(time.time())}"
TEST_APPOINTMENT_ID = f"test_appointment_{int(time.time() * 1000)}"

def test_cosmos_connectivity():
    """Test basic Cosmos DB connectivity through the Azure Functions endpoints"""
    print("🔍 Testing Azure Cosmos DB Integration...")
    print("=" * 50)
    
    try:
        # Test 1: List patients (should work even if empty)
        print("\n1️⃣ Testing patient listing...")
        response = requests.get(f"{BASE_URL}/patients")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Patients endpoint accessible")
            print(f"   Current patient count: {data.get('count', 0)}")
        elif response.status_code == 500:
            error_data = response.json()
            if "Cosmos DB not configured" in error_data.get('error', ''):
                print("❌ Cosmos DB not configured - check COSMOS_CONNECTION_STRING")
                return False
            else:
                print(f"❌ Server error: {error_data.get('error', 'Unknown error')}")
                return False
        else:
            print(f"❌ Unexpected response: {response.status_code}")
            return False
        
        # Test 2: Create a test patient
        print("\n2️⃣ Testing patient creation...")
        test_patient = {
            "id": TEST_PATIENT_ID,
            "patientId": TEST_PATIENT_ID,
            "firstName": "John",
            "lastName": "Doe",
            "email": "john.doe@example.com",
            "phone": "+1234567890",
            "dateOfBirth": "1990-01-01",
            "medicalHistory": "No known allergies"
        }
        
        response = requests.post(f"{BASE_URL}/patients", json=test_patient)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print(f"✅ Patient created successfully: {TEST_PATIENT_ID}")
            else:
                print(f"❌ Patient creation failed: {data.get('error')}")
                return False
        else:
            print(f"❌ Failed to create patient: {response.status_code}")
            try:
                error_data = response.json()
                print(f"   Error: {error_data.get('error', 'Unknown error')}")
            except:
                print(f"   Response: {response.text}")
            return False
        
        # Test 3: Retrieve the created patient
        print("\n3️⃣ Testing patient retrieval...")
        response = requests.get(f"{BASE_URL}/patients/{TEST_PATIENT_ID}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                patient = data.get("patient", {})
                print(f"✅ Patient retrieved successfully")
                print(f"   Name: {patient.get('firstName')} {patient.get('lastName')}")
                print(f"   Email: {patient.get('email')}")
            else:
                print(f"❌ Patient retrieval failed: {data.get('error')}")
                return False
        else:
            print(f"❌ Failed to retrieve patient: {response.status_code}")
            return False
        
        # Test 4: Create a test appointment
        print("\n4️⃣ Testing appointment creation...")
        test_appointment = {
            "id": TEST_APPOINTMENT_ID,
            "patientId": TEST_PATIENT_ID,
            "appointmentDate": "2025-08-15T10:00:00Z",
            "appointmentType": "Annual Checkup",
            "provider": "Dr. Smith",
            "status": "scheduled",
            "notes": "Regular annual health checkup"
        }
        
        response = requests.post(f"{BASE_URL}/appointments", json=test_appointment)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print(f"✅ Appointment created successfully: {TEST_APPOINTMENT_ID}")
            else:
                print(f"❌ Appointment creation failed: {data.get('error')}")
                return False
        else:
            print(f"❌ Failed to create appointment: {response.status_code}")
            return False
        
        # Test 5: List appointments for the patient
        print("\n5️⃣ Testing appointment listing for patient...")
        response = requests.get(f"{BASE_URL}/appointments?patientId={TEST_PATIENT_ID}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                appointments = data.get("appointments", [])
                print(f"✅ Appointments retrieved successfully")
                print(f"   Count: {len(appointments)}")
                if appointments:
                    apt = appointments[0]
                    print(f"   First appointment: {apt.get('appointmentType')} on {apt.get('appointmentDate')}")
            else:
                print(f"❌ Appointment listing failed: {data.get('error')}")
                return False
        else:
            print(f"❌ Failed to list appointments: {response.status_code}")
            return False
        
        # Test 6: Update the patient
        print("\n6️⃣ Testing patient update...")
        update_data = {
            "phone": "+1987654321",
            "email": "john.doe.updated@example.com"
        }
        
        response = requests.put(f"{BASE_URL}/patients/{TEST_PATIENT_ID}", json=update_data)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print(f"✅ Patient updated successfully")
                patient = data.get("patient", {})
                print(f"   New phone: {patient.get('phone')}")
                print(f"   New email: {patient.get('email')}")
            else:
                print(f"❌ Patient update failed: {data.get('error')}")
                return False
        else:
            print(f"❌ Failed to update patient: {response.status_code}")
            return False
        
        print("\n🎉 All tests passed! Azure Cosmos DB integration is working correctly.")
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to Azure Functions. Make sure the functions host is running:")
        print("   Run: func host start")
        return False
    except Exception as e:
        print(f"❌ Unexpected error during testing: {str(e)}")
        return False
    
    finally:
        # Cleanup: Delete test data
        print("\n🧹 Cleaning up test data...")
        try:
            # Delete appointment
            requests.delete(f"{BASE_URL}/appointments/{TEST_APPOINTMENT_ID}?patientId={TEST_PATIENT_ID}")
            print("   Deleted test appointment")
            
            # Delete patient
            requests.delete(f"{BASE_URL}/patients/{TEST_PATIENT_ID}")
            print("   Deleted test patient")
        except:
            print("   Cleanup completed (some items may not have existed)")

def test_endpoint_availability():
    """Test which endpoints are available"""
    print("\n📋 Testing endpoint availability...")
    
    endpoints_to_test = [
        ("GET", "/TestMessage", "Configuration test"),
        ("GET", "/patients", "Patient listing"),
        ("GET", "/appointments", "Appointment listing"),
    ]
    
    for method, endpoint, description in endpoints_to_test:
        try:
            if method == "GET":
                response = requests.get(f"{BASE_URL}{endpoint}")
            
            if response.status_code in [200, 400]:  # 400 is ok for some endpoints
                print(f"✅ {endpoint} - {description} (Status: {response.status_code})")
            else:
                print(f"❌ {endpoint} - {description} (Status: {response.status_code})")
                
        except Exception as e:
            print(f"❌ {endpoint} - Connection failed: {str(e)}")

if __name__ == "__main__":
    print("🚀 Azure Healthcare Functions - Cosmos DB Integration Test")
    print("=" * 60)
    
    # Test endpoint availability first
    test_endpoint_availability()
    
    # Test Cosmos DB integration
    success = test_cosmos_connectivity()
    
    if success:
        print("\n✅ Integration test completed successfully!")
        print("\n📚 Available endpoints for your healthcare application:")
        print("   • GET  /api/patients              - List all patients")
        print("   • POST /api/patients              - Create new patient")
        print("   • GET  /api/patients/{id}         - Get patient by ID")
        print("   • PUT  /api/patients/{id}         - Update patient")
        print("   • DELETE /api/patients/{id}       - Delete patient")
        print("   • GET  /api/appointments          - List appointments")
        print("   • GET  /api/appointments?patientId={id} - List appointments for patient")
        print("   • POST /api/appointments          - Create new appointment")
        print("   • GET  /api/appointments/{id}?patientId={id} - Get appointment")
        print("   • PUT  /api/appointments/{id}?patientId={id} - Update appointment")
        print("   • DELETE /api/appointments/{id}?patientId={id} - Delete appointment")
        print("\n🔊 Voice Communication endpoints are also available:")
        print("   • GET  /api/MakeTestCallNoWebhook - Most reliable call method")
        print("   • GET  /api/GetToken              - Get ACS authentication token")
        print("   • GET  /api/TestMessage           - View configuration and endpoints")
        sys.exit(0)
    else:
        print("\n❌ Integration test failed. Please check:")
        print("   1. Azure Functions host is running (func host start)")
        print("   2. COSMOS_CONNECTION_STRING is set in local.settings.json")
        print("   3. Cosmos DB database 'HealthcareDB' exists")
        print("   4. Containers 'patients' and 'appointments' exist")
        sys.exit(1)
