"""
Appointment Management Endpoints
Handles appointment data management with Azure Cosmos DB
"""

import azure.functions as func
import logging
import json
import time
from services.cosmos_manager import cosmos_manager


def register_appointment_endpoints(app: func.FunctionApp):
    """Register appointment management endpoints with the Function App"""

    @app.route(route="appointments", methods=["GET", "POST", "OPTIONS"])
    def manage_appointments(req: func.HttpRequest) -> func.HttpResponse:
        """Appointment management endpoint - GET: List appointments, POST: Create appointment"""
        # Handle CORS preflight requests
        if req.method == "OPTIONS":
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '86400'
            }
            return func.HttpResponse("", status_code=200, headers=headers)
        
        logging.info(f'Appointment management: {req.method} request received')
        
        # Check if Cosmos DB is configured
        if not cosmos_manager.is_connected():
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
            return func.HttpResponse(
                json.dumps({"error": "Cosmos DB not configured. Please set COSMOS_CONNECTION_STRING."}),
                status_code=500,
                mimetype="application/json",
                headers=headers
            )
        
        try:
            if req.method == "GET":
                # List appointments
                patient_id = req.params.get('patientId')
                
                try:
                    if patient_id:
                        # List appointments for specific patient
                        query = "SELECT * FROM c WHERE c.patientId = @patientId ORDER BY c.appointmentDate ASC"
                        parameters = [{"name": "@patientId", "value": patient_id}]
                        items = list(cosmos_manager.appointments_container.query_items(
                            query=query,
                            parameters=parameters,
                            partition_key=patient_id
                        ))
                        message = f"Retrieved {len(items)} appointments for patient {patient_id}"
                    else:
                        # List all appointments
                        query = "SELECT * FROM c ORDER BY c.appointmentDate ASC"
                        items = list(cosmos_manager.appointments_container.query_items(
                            query=query,
                            enable_cross_partition_query=True
                        ))
                        message = f"Retrieved {len(items)} appointments"
                    
                    response_data = {
                        "success": True,
                        "appointments": items,
                        "count": len(items),
                        "message": message
                    }
                    
                except Exception as e:
                    logging.error(f"Error listing appointments: {str(e)}")
                    response_data = {
                        "success": False,
                        "error": f"Failed to list appointments: {str(e)}"
                    }
                    
            elif req.method == "POST":
                # Create appointment
                try:
                    appointment_data = req.get_json()
                    if not appointment_data:
                        response_data = {
                            "success": False,
                            "error": "No appointment data provided in request body"
                        }
                    else:
                        # Ensure required fields
                        if 'id' not in appointment_data:
                            appointment_data['id'] = appointment_data.get('appointmentId', str(int(time.time())))
                        if 'appointmentId' not in appointment_data:
                            appointment_data['appointmentId'] = appointment_data['id']
                            
                        # Add metadata
                        appointment_data['createdAt'] = int(time.time())
                        appointment_data['updatedAt'] = int(time.time())
                        
                        # Ensure patientId for partitioning
                        if 'patientId' not in appointment_data:
                            appointment_data['patientId'] = appointment_data.get('patient_id', 'default')
                        
                        # Create appointment
                        response = cosmos_manager.appointments_container.create_item(body=appointment_data)
                        
                        response_data = {
                            "success": True,
                            "appointment": response,
                            "message": f"Appointment created successfully with ID: {appointment_data['id']}"
                        }
                    
                except Exception as e:
                    logging.error(f"Error creating appointment: {str(e)}")
                    response_data = {
                        "success": False,
                        "error": f"Failed to create appointment: {str(e)}"
                    }
            
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
            
            status_code = 200 if response_data.get("success") else 400
            
            return func.HttpResponse(
                json.dumps(response_data),
                status_code=status_code,
                mimetype="application/json",
                headers=headers
            )
            
        except Exception as e:
            logging.error(f"Appointment management error: {str(e)}")
            
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
            
            return func.HttpResponse(
                json.dumps({"success": False, "error": str(e)}),
                status_code=500,
                mimetype="application/json",
                headers=headers
            )

    @app.route(route="appointments/{appointment_id}", methods=["GET", "PUT", "DELETE", "OPTIONS"])
    def manage_appointment(req: func.HttpRequest) -> func.HttpResponse:
        """Individual appointment management - GET/PUT/DELETE by appointment ID"""
        # Handle CORS preflight requests
        if req.method == "OPTIONS":
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '86400'
            }
            return func.HttpResponse("", status_code=200, headers=headers)
        
        appointment_id = req.route_params.get('appointment_id')
        if not appointment_id:
            return func.HttpResponse(
                json.dumps({"error": "Appointment ID is required"}),
                status_code=400,
                mimetype="application/json"
            )
        
        logging.info(f'Appointment {req.method}: {appointment_id}')
        
        # Check if Cosmos DB is configured
        if not cosmos_manager.is_connected():
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
            return func.HttpResponse(
                json.dumps({"error": "Cosmos DB not configured. Please set COSMOS_CONNECTION_STRING."}),
                status_code=500,
                mimetype="application/json",
                headers=headers
            )
        
        try:
            # For appointments, we need the patient_id to access the correct partition
            patient_id = req.params.get('patientId')
            
            if req.method == "GET":
                # Get appointment by ID
                try:
                    if patient_id:
                        # Use patient_id as partition key
                        response = cosmos_manager.appointments_container.read_item(
                            item=appointment_id, 
                            partition_key=patient_id
                        )
                    else:
                        # Search across partitions if patient_id not provided
                        query = "SELECT * FROM c WHERE c.id = @appointment_id"
                        parameters = [{"name": "@appointment_id", "value": appointment_id}]
                        items = list(cosmos_manager.appointments_container.query_items(
                            query=query,
                            parameters=parameters,
                            enable_cross_partition_query=True
                        ))
                        if not items:
                            raise Exception("NotFound")
                        response = items[0]
                    
                    response_data = {
                        "success": True,
                        "appointment": response,
                        "message": f"Appointment retrieved successfully: {appointment_id}"
                    }
                except Exception as e:
                    if "NotFound" in str(e):
                        response_data = {
                            "success": False,
                            "error": f"Appointment with ID {appointment_id} not found"
                        }
                    else:
                        response_data = {
                            "success": False,
                            "error": f"Failed to retrieve appointment: {str(e)}"
                        }
                        
            elif req.method == "PUT":
                # Update appointment
                try:
                    updates = req.get_json()
                    if not updates:
                        raise Exception("No update data provided")
                    
                    # Get existing appointment first
                    if patient_id:
                        existing_appointment = cosmos_manager.appointments_container.read_item(
                            item=appointment_id, 
                            partition_key=patient_id
                        )
                    else:
                        # Search for appointment if patient_id not provided
                        query = "SELECT * FROM c WHERE c.id = @appointment_id"
                        parameters = [{"name": "@appointment_id", "value": appointment_id}]
                        items = list(cosmos_manager.appointments_container.query_items(
                            query=query,
                            parameters=parameters,
                            enable_cross_partition_query=True
                        ))
                        if not items:
                            raise Exception("NotFound")
                        existing_appointment = items[0]
                        patient_id = existing_appointment.get('patientId')
                    
                    # Update fields
                    existing_appointment.update(updates)
                    existing_appointment['updatedAt'] = int(time.time())
                    
                    response = cosmos_manager.appointments_container.replace_item(
                        item=appointment_id, 
                        body=existing_appointment
                    )
                    response_data = {
                        "success": True,
                        "appointment": response,
                        "message": f"Appointment updated successfully: {appointment_id}"
                    }
                    
                except Exception as e:
                    if "NotFound" in str(e):
                        response_data = {
                            "success": False,
                            "error": f"Appointment with ID {appointment_id} not found"
                        }
                    else:
                        response_data = {
                            "success": False,
                            "error": f"Failed to update appointment: {str(e)}"
                        }
                        
            elif req.method == "DELETE":
                # Delete appointment
                try:
                    if patient_id:
                        cosmos_manager.appointments_container.delete_item(
                            item=appointment_id, 
                            partition_key=patient_id
                        )
                    else:
                        # Find appointment first to get patient_id
                        query = "SELECT * FROM c WHERE c.id = @appointment_id"
                        parameters = [{"name": "@appointment_id", "value": appointment_id}]
                        items = list(cosmos_manager.appointments_container.query_items(
                            query=query,
                            parameters=parameters,
                            enable_cross_partition_query=True
                        ))
                        if not items:
                            raise Exception("NotFound")
                        appointment = items[0]
                        patient_id = appointment.get('patientId')
                        
                        cosmos_manager.appointments_container.delete_item(
                            item=appointment_id, 
                            partition_key=patient_id
                        )
                    
                    response_data = {
                        "success": True,
                        "message": f"Appointment deleted successfully: {appointment_id}"
                    }
                except Exception as e:
                    if "NotFound" in str(e):
                        response_data = {
                            "success": False,
                            "error": f"Appointment with ID {appointment_id} not found"
                        }
                    else:
                        response_data = {
                            "success": False,
                            "error": f"Failed to delete appointment: {str(e)}"
                        }
            
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
            
            status_code = 200 if response_data.get("success") else 404
            
            return func.HttpResponse(
                json.dumps(response_data),
                status_code=status_code,
                mimetype="application/json",
                headers=headers
            )
            
        except Exception as e:
            logging.error(f"Appointment management error: {str(e)}")
            
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
            
            return func.HttpResponse(
                json.dumps({"success": False, "error": str(e)}),
                status_code=500,
                mimetype="application/json",
                headers=headers
            )
