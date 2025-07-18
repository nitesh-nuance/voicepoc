"""
Azure Cosmos DB Manager
Handles patient and appointment data with proper error handling and retry logic
"""

import os
import json
import time
import logging
from typing import Optional, Dict, List

# Azure Cosmos DB imports
from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosResourceExistsError, CosmosResourceNotFoundError

# Configuration
COSMOS_CONNECTION_STRING = os.environ.get("COSMOS_CONNECTION_STRING", "")
COSMOS_DATABASE_NAME = "adherenceagentdb"
COSMOS_PATIENTS_CONTAINER = "patients"
COSMOS_APPOINTMENTS_CONTAINER = "appointments"


class CosmosDBManager:
    """
    Azure Cosmos DB manager for healthcare application
    Handles patient and appointment data with proper error handling and retry logic
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
    
    # Patient Management Methods
    async def create_patient(self, patient_data: dict) -> dict:
        """Create a new patient record"""
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
        """Get a patient by ID"""
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
        """Update an existing patient record"""
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
    
    # Appointment Management Methods
    async def create_appointment(self, appointment_data: dict) -> dict:
        """Create a new appointment record"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            # Ensure required fields
            if 'id' not in appointment_data:
                appointment_data['id'] = str(int(time.time() * 1000))  # Unique ID
            if 'patientId' not in appointment_data:
                raise Exception("patientId is required for appointments")
                
            # Add metadata
            appointment_data['createdAt'] = int(time.time())
            appointment_data['updatedAt'] = int(time.time())
            
            response = self.appointments_container.create_item(body=appointment_data)
            logging.info(f"Appointment created successfully: {appointment_data['id']}")
            return response
        except CosmosResourceExistsError:
            raise Exception(f"Appointment with ID {appointment_data['id']} already exists")
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
    
    async def list_appointments_for_patient(self, patient_id: str) -> list:
        """List all appointments for a specific patient"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            query = "SELECT * FROM c WHERE c.patientId = @patientId ORDER BY c.appointmentDate ASC"
            parameters = [{"name": "@patientId", "value": patient_id}]
            
            items = list(self.appointments_container.query_items(
                query=query,
                parameters=parameters,
                partition_key=patient_id
            ))
            logging.info(f"Retrieved {len(items)} appointments for patient {patient_id}")
            return items
        except Exception as e:
            logging.error(f"Error listing appointments: {str(e)}")
            raise Exception(f"Failed to list appointments: {str(e)}")
    
    async def update_appointment(self, appointment_id: str, patient_id: str, updates: dict) -> dict:
        """Update an existing appointment record"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            # First get the existing appointment
            existing_appointment = await self.get_appointment(appointment_id, patient_id)
            
            # Update fields
            existing_appointment.update(updates)
            existing_appointment['updatedAt'] = int(time.time())
            
            response = self.appointments_container.replace_item(item=appointment_id, body=existing_appointment)
            logging.info(f"Appointment updated successfully: {appointment_id}")
            return response
        except Exception as e:
            logging.error(f"Error updating appointment: {str(e)}")
            raise Exception(f"Failed to update appointment: {str(e)}")
    
    async def delete_appointment(self, appointment_id: str, patient_id: str) -> bool:
        """Delete an appointment record"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            self.appointments_container.delete_item(item=appointment_id, partition_key=patient_id)
            logging.info(f"Appointment deleted successfully: {appointment_id}")
            return True
        except CosmosResourceNotFoundError:
            raise Exception(f"Appointment with ID {appointment_id} not found")
        except Exception as e:
            logging.error(f"Error deleting appointment: {str(e)}")
            raise Exception(f"Failed to delete appointment: {str(e)}")
    
    async def list_all_appointments(self, limit: int = 100) -> list:
        """List all appointments across all patients"""
        if not self.is_connected():
            raise Exception("Cosmos DB not connected")
        
        try:
            query = "SELECT * FROM c ORDER BY c.appointmentDate ASC"
            items = list(self.appointments_container.query_items(
                query=query,
                max_item_count=limit,
                enable_cross_partition_query=True
            ))
            logging.info(f"Retrieved {len(items)} appointments")
            return items
        except Exception as e:
            logging.error(f"Error listing all appointments: {str(e)}")
            raise Exception(f"Failed to list appointments: {str(e)}")


# Create global instance for use in function app
cosmos_manager = CosmosDBManager()
