"""
Azure Cosmos DB Manager
Handles patient and appointment data with proper error handling and retry logic
Enhanced with medication adherence tracking and bot.js-style patient records
"""

import os
import json
import time
import logging
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# Azure Cosmos DB imports
from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosResourceExistsError, CosmosResourceNotFoundError

# Import bot configuration
from bot_config import MedicationAdherenceState, bot_config

# Configuration
COSMOS_CONNECTION_STRING = os.environ.get("COSMOS_CONNECTION_STRING", "")
COSMOS_DATABASE_NAME = "nursevoiceagentdb"
COSMOS_PATIENTS_CONTAINER = "patients"
COSMOS_APPOINTMENTS_CONTAINER = "appointments"


@dataclass
class MedicationInfo:
    """Medication information for patient records"""
    name: str
    dosage: str
    frequency: str
    instructions: str
    prescribed_date: str
    prescribing_doctor: str
    pharmacy_name: Optional[str] = None
    pickup_date: Optional[str] = None
    side_effects_noted: List[str] = field(default_factory=list)
    adherence_notes: List[str] = field(default_factory=list)


@dataclass
class PatientRecord:
    """Enhanced patient record with medication adherence tracking"""
    # Basic patient information
    id: str
    patient_id: str
    first_name: str
    last_name: str
    phone_number: str
    date_of_birth: Optional[str] = None
    email: Optional[str] = None
    
    # Healthcare context
    primary_doctor: str = bot_config.default_doctor_name
    doctor_specialty: str = bot_config.default_doctor_specialty
    facility_name: str = bot_config.facility_name
    discharge_date: Optional[str] = None
    admission_reason: Optional[str] = None
    
    # Medication adherence tracking
    medications: List[MedicationInfo] = field(default_factory=list)
    adherence_state: MedicationAdherenceState = MedicationAdherenceState.INITIAL_CONTACT
    pickup_status: Dict[str, bool] = field(default_factory=dict)  # medication_name -> pickup_status
    dosage_discussed: Dict[str, bool] = field(default_factory=dict)  # medication_name -> discussed_status
    adherence_concerns: List[str] = field(default_factory=list)
    
    # Emergency and safety information
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    allergies: List[str] = field(default_factory=list)
    medical_conditions: List[str] = field(default_factory=list)
    
    # Conversation and follow-up tracking
    last_contact_date: Optional[str] = None
    next_follow_up_date: Optional[str] = None
    conversation_notes: List[str] = field(default_factory=list)
    escalation_history: List[str] = field(default_factory=list)
    
    # Metadata
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))
    
    def to_dict(self) -> dict:
        """Convert patient record to dictionary for Cosmos DB storage"""
        return {
            'id': self.id,
            'patientId': self.patient_id,
            'firstName': self.first_name,
            'lastName': self.last_name,
            'phoneNumber': self.phone_number,
            'dateOfBirth': self.date_of_birth,
            'email': self.email,
            
            # Healthcare context
            'primaryDoctor': self.primary_doctor,
            'doctorSpecialty': self.doctor_specialty,
            'facilityName': self.facility_name,
            'dischargeDate': self.discharge_date,
            'admissionReason': self.admission_reason,
            
            # Medication adherence
            'medications': [
                {
                    'name': med.name,
                    'dosage': med.dosage,
                    'frequency': med.frequency,
                    'instructions': med.instructions,
                    'prescribedDate': med.prescribed_date,
                    'prescribingDoctor': med.prescribing_doctor,
                    'pharmacyName': med.pharmacy_name,
                    'pickupDate': med.pickup_date,
                    'sideEffectsNoted': med.side_effects_noted,
                    'adherenceNotes': med.adherence_notes
                }
                for med in self.medications
            ],
            'adherenceState': self.adherence_state.value,
            'pickupStatus': self.pickup_status,
            'dosageDiscussed': self.dosage_discussed,
            'adherenceConcerns': self.adherence_concerns,
            
            # Emergency and safety
            'emergencyContactName': self.emergency_contact_name,
            'emergencyContactPhone': self.emergency_contact_phone,
            'allergies': self.allergies,
            'medicalConditions': self.medical_conditions,
            
            # Conversation tracking
            'lastContactDate': self.last_contact_date,
            'nextFollowUpDate': self.next_follow_up_date,
            'conversationNotes': self.conversation_notes,
            'escalationHistory': self.escalation_history,
            
            # Metadata
            'createdAt': self.created_at,
            'updatedAt': self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'PatientRecord':
        """Create patient record from dictionary (from Cosmos DB)"""
        medications = []
        for med_data in data.get('medications', []):
            medications.append(MedicationInfo(
                name=med_data['name'],
                dosage=med_data['dosage'],
                frequency=med_data['frequency'],
                instructions=med_data['instructions'],
                prescribed_date=med_data['prescribedDate'],
                prescribing_doctor=med_data['prescribingDoctor'],
                pharmacy_name=med_data.get('pharmacyName'),
                pickup_date=med_data.get('pickupDate'),
                side_effects_noted=med_data.get('sideEffectsNoted', []),
                adherence_notes=med_data.get('adherenceNotes', [])
            ))
        
        return cls(
            id=data['id'],
            patient_id=data.get('patientId', data['id']),
            first_name=data['firstName'],
            last_name=data['lastName'],
            phone_number=data['phoneNumber'],
            date_of_birth=data.get('dateOfBirth'),
            email=data.get('email'),
            
            # Healthcare context
            primary_doctor=data.get('primaryDoctor', bot_config.default_doctor_name),
            doctor_specialty=data.get('doctorSpecialty', bot_config.default_doctor_specialty),
            facility_name=data.get('facilityName', bot_config.facility_name),
            discharge_date=data.get('dischargeDate'),
            admission_reason=data.get('admissionReason'),
            
            # Medication adherence
            medications=medications,
            adherence_state=MedicationAdherenceState(data.get('adherenceState', 'initial_contact')),
            pickup_status=data.get('pickupStatus', {}),
            dosage_discussed=data.get('dosageDiscussed', {}),
            adherence_concerns=data.get('adherenceConcerns', []),
            
            # Emergency and safety
            emergency_contact_name=data.get('emergencyContactName'),
            emergency_contact_phone=data.get('emergencyContactPhone'),
            allergies=data.get('allergies', []),
            medical_conditions=data.get('medicalConditions', []),
            
            # Conversation tracking
            last_contact_date=data.get('lastContactDate'),
            next_follow_up_date=data.get('nextFollowUpDate'),
            conversation_notes=data.get('conversationNotes', []),
            escalation_history=data.get('escalationHistory', []),
            
            # Metadata
            created_at=data.get('createdAt', int(time.time())),
            updated_at=data.get('updatedAt', int(time.time()))
        )
    
    def get_full_name(self) -> str:
        """Get patient's full name"""
        return f"{self.first_name} {self.last_name}"
    
    def get_medication_names(self) -> List[str]:
        """Get list of medication names"""
        return [med.name for med in self.medications]
    
    @property
    def current_adherence_state(self) -> MedicationAdherenceState:
        """Get current medication adherence state"""
        return self.adherence_state
    
    def update_adherence_state(self, new_state: MedicationAdherenceState):
        """Update medication adherence state"""
        self.adherence_state = new_state
        self.updated_at = int(time.time())
    
    def mark_medication_picked_up(self, medication_name: str, pickup_date: str):
        """Mark a medication as picked up"""
        self.pickup_status[medication_name] = True
        # Update the medication record
        for med in self.medications:
            if med.name == medication_name:
                med.pickup_date = pickup_date
        self.updated_at = int(time.time())
    
    def mark_dosage_discussed(self, medication_name: str):
        """Mark dosage as discussed for a medication"""
        self.dosage_discussed[medication_name] = True
        self.updated_at = int(time.time())
    
    def add_conversation_note(self, note: str):
        """Add a conversation note"""
        timestamp = datetime.now().isoformat()
        self.conversation_notes.append(f"{timestamp}: {note}")
        self.last_contact_date = timestamp
        self.updated_at = int(time.time())
    
    def add_adherence_concern(self, concern: str):
        """Add an adherence concern"""
        if concern not in self.adherence_concerns:
            self.adherence_concerns.append(concern)
        self.updated_at = int(time.time())


class CosmosDBManager:
    """
    Azure Cosmos DB manager for healthcare application
    Handles patient and appointment data with proper error handling and retry logic
    Enhanced with medication adherence tracking
    """
    
    def __init__(self):
        """Initialize Cosmos DB client with connection string"""
        if not COSMOS_CONNECTION_STRING:
            logging.warning("COSMOS_CONNECTION_STRING not configured")
            self.client = None
            self.database = None
            self.patients_container = None
            self.appointments_container = None
            return
            
        try:
            self.client = CosmosClient.from_connection_string(COSMOS_CONNECTION_STRING)
            self.database = self.client.get_database_client(COSMOS_DATABASE_NAME)
            self.patients_container = self.database.get_container_client(COSMOS_PATIENTS_CONTAINER)
            self.appointments_container = self.database.get_container_client(COSMOS_APPOINTMENTS_CONTAINER)
            logging.info("CosmosDB client initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize CosmosDB client: {str(e)}")
            self.client = None
            self.database = None
            self.patients_container = None
            self.appointments_container = None
    
    def is_connected(self) -> bool:
        """Check if Cosmos DB is properly connected"""
        return self.client is not None
    
    # Enhanced Patient Management Methods with Medication Adherence
    async def create_patient_record(self, patient_record: PatientRecord) -> dict:
        """Create a new enhanced patient record with medication adherence tracking"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            patient_dict = patient_record.to_dict()
            response = self.patients_container.create_item(body=patient_dict)
            logging.info(f"Enhanced patient record created successfully: {patient_record.id}")
            return response
        except CosmosResourceExistsError:
            raise Exception(f"Patient with ID {patient_record.id} already exists")
        except Exception as e:
            logging.error(f"Error creating enhanced patient record: {str(e)}")
            raise Exception(f"Failed to create patient record: {str(e)}")
    
    async def get_patient_record(self, patient_id: str) -> PatientRecord:
        """Get enhanced patient record by ID"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            response = self.patients_container.read_item(item=patient_id, partition_key=patient_id)
            patient_record = PatientRecord.from_dict(response)
            logging.info(f"Enhanced patient record retrieved successfully: {patient_id}")
            return patient_record
        except CosmosResourceNotFoundError:
            raise Exception(f"Patient with ID {patient_id} not found")
        except Exception as e:
            logging.error(f"Error retrieving patient record: {str(e)}")
            raise Exception(f"Failed to retrieve patient record: {str(e)}")
    
    async def update_patient_record(self, patient_record: PatientRecord) -> dict:
        """Update enhanced patient record with medication adherence tracking"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            patient_record.updated_at = int(time.time())
            patient_dict = patient_record.to_dict()
            response = self.patients_container.replace_item(item=patient_record.id, body=patient_dict)
            logging.info(f"Enhanced patient record updated successfully: {patient_record.id}")
            return response
        except Exception as e:
            logging.error(f"Error updating patient record: {str(e)}")
            raise Exception(f"Failed to update patient record: {str(e)}")
    
    async def update_medication_adherence_state(self, patient_id: str, new_state: MedicationAdherenceState) -> dict:
        """Update patient's medication adherence state"""
        patient_record = await self.get_patient_record(patient_id)
        patient_record.update_adherence_state(new_state)
        return await self.update_patient_record(patient_record)
    
    async def mark_medication_pickup(self, patient_id: str, medication_name: str, pickup_date: str) -> dict:
        """Mark a medication as picked up for a patient"""
        patient_record = await self.get_patient_record(patient_id)
        patient_record.mark_medication_picked_up(medication_name, pickup_date)
        return await self.update_patient_record(patient_record)
    
    async def add_patient_conversation_note(self, patient_id: str, note: str) -> dict:
        """Add a conversation note to patient record"""
        patient_record = await self.get_patient_record(patient_id)
        patient_record.add_conversation_note(note)
        return await self.update_patient_record(patient_record)
    
    # Legacy Patient Management Methods (for backward compatibility)
    async def create_patient(self, patient_data: dict) -> dict:
        """Create a new patient record (legacy method)"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            # Ensure required fields
            if 'id' not in patient_data:
                patient_data['id'] = patient_data.get('patientId', str(int(time.time())))
            if 'patientId' not in patient_data:
                patient_data['patientId'] = patient_data['id']
                
            # Add metadata
            patient_data['createdAt'] = int(time.time())
            patient_data['updatedAt'] = int(time.time())
            
            response = self.patients_container.create_item(body=patient_data)
            logging.info(f"Patient created successfully: {patient_data['id']}")
            return response
        except CosmosResourceExistsError:
            raise Exception(f"Patient with ID {patient_data['id']} already exists")
        except Exception as e:
            logging.error(f"Error creating patient: {str(e)}")
            raise Exception(f"Failed to create patient: {str(e)}")
    
    async def get_patient(self, patient_id: str) -> dict:
        """Get a patient by ID (legacy method)"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            response = self.patients_container.read_item(item=patient_id, partition_key=patient_id)
            logging.info(f"Patient retrieved successfully: {patient_id}")
            return response
        except CosmosResourceNotFoundError:
            raise Exception(f"Patient with ID {patient_id} not found")
        except Exception as e:
            logging.error(f"Error retrieving patient: {str(e)}")
            raise Exception(f"Failed to retrieve patient: {str(e)}")
    
    async def update_patient(self, patient_id: str, updates: dict) -> dict:
        """Update an existing patient record (legacy method)"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            # First get the existing patient
            existing_patient = await self.get_patient(patient_id)
            
            # Update fields
            existing_patient.update(updates)
            existing_patient['updatedAt'] = int(time.time())
            
            response = self.patients_container.replace_item(item=patient_id, body=existing_patient)
            logging.info(f"Patient updated successfully: {patient_id}")
            return response
        except Exception as e:
            logging.error(f"Error updating patient: {str(e)}")
            raise Exception(f"Failed to update patient: {str(e)}")
    
    async def delete_patient(self, patient_id: str) -> bool:
        """Delete a patient record"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            self.patients_container.delete_item(item=patient_id, partition_key=patient_id)
            logging.info(f"Patient deleted successfully: {patient_id}")
            return True
        except CosmosResourceNotFoundError:
            raise Exception(f"Patient with ID {patient_id} not found")
        except Exception as e:
            logging.error(f"Error deleting patient: {str(e)}")
            raise Exception(f"Failed to delete patient: {str(e)}")
    
    async def list_patients(self, limit: int = 100) -> list:
        """List all patients with optional limit"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            query = "SELECT * FROM c ORDER BY c.createdAt DESC"
            items = list(self.patients_container.query_items(
                query=query,
                max_item_count=limit,
                enable_cross_partition_query=True
            ))
            logging.info(f"Retrieved {len(items)} patients")
            return items
        except Exception as e:
            logging.error(f"Error listing patients: {str(e)}")
            raise Exception(f"Failed to list patients: {str(e)}")

    # Appointment Management Methods (keeping existing functionality)
    async def create_appointment(self, appointment_data: dict) -> dict:
        """Create a new appointment"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            # Ensure required fields
            if 'id' not in appointment_data:
                appointment_data['id'] = str(int(time.time()))
            if 'patientId' not in appointment_data:
                raise Exception("patientId is required for appointments")
                
            # Add metadata
            appointment_data['createdAt'] = int(time.time())
            appointment_data['updatedAt'] = int(time.time())
            
            response = self.appointments_container.create_item(body=appointment_data)
            logging.info(f"Appointment created successfully: {appointment_data['id']}")
            return response
        except Exception as e:
            logging.error(f"Error creating appointment: {str(e)}")
            raise Exception(f"Failed to create appointment: {str(e)}")
    
    async def get_appointment(self, appointment_id: str, patient_id: str) -> dict:
        """Get an appointment by ID"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            response = self.appointments_container.read_item(item=appointment_id, partition_key=patient_id)
            logging.info(f"Appointment retrieved successfully: {appointment_id}")
            return response
        except CosmosResourceNotFoundError:
            raise Exception(f"Appointment with ID {appointment_id} not found")
        except Exception as e:
            logging.error(f"Error retrieving appointment: {str(e)}")
            raise Exception(f"Failed to retrieve appointment: {str(e)}")
    
    async def get_patient_appointments(self, patient_id: str) -> list:
        """Get all appointments for a patient"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            query = "SELECT * FROM c WHERE c.patientId = @patientId ORDER BY c.createdAt DESC"
            parameters = [{"name": "@patientId", "value": patient_id}]
            items = list(self.appointments_container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ))
            logging.info(f"Retrieved {len(items)} appointments for patient {patient_id}")
            return items
        except Exception as e:
            logging.error(f"Error retrieving patient appointments: {str(e)}")
            raise Exception(f"Failed to retrieve patient appointments: {str(e)}")


# Global instance
cosmos_manager = CosmosDBManager()
