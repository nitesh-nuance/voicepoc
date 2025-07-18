"""
Patient Management Endpoints
Handles patient data management with Azure Cosmos DB
"""

import azure.functions as func
import logging
import json
import time
from services.cosmos_manager import cosmos_manager


def register_patient_endpoints(app: func.FunctionApp):
    """Register patient management endpoints with the Function App"""

    @app.route(route="patients", methods=["GET", "POST", "OPTIONS"])
    def manage_patients(req: func.HttpRequest) -> func.HttpResponse:
        """Patient management endpoint - GET: List patients, POST: Create patient"""
        # Handle CORS preflight requests
        if req.method == "OPTIONS":
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '86400'
            }
            return func.HttpResponse("", status_code=200, headers=headers)
        
        logging.info(f'Patient management: {req.method} request received')
        
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
            response_data = {"success": False, "error": "Unknown error"}  # Initialize with default
            
            if req.method == "GET":
                # List patients
                limit = int(req.params.get('limit', 100))
                
                try:
                    # Using synchronous method for Azure Functions v1 compatibility
                    query = "SELECT * FROM c ORDER BY c.createdAt DESC"
                    items = list(cosmos_manager.patients_container.query_items(
                        query=query,
                        max_item_count=limit,
                        enable_cross_partition_query=True
                    ))
                    
                    response_data = {
                        "success": True,
                        "patients": items,
                        "count": len(items),
                        "message": f"Retrieved {len(items)} patients"
                    }
                    
                except Exception as e:
                    logging.error(f"Error listing patients: {str(e)}")
                    response_data = {
                        "success": False,
                        "error": f"Failed to list patients: {str(e)}"
                    }
                    
            elif req.method == "POST":
                # Create patient
                try:
                    patient_data = req.get_json()
                    if not patient_data:
                        response_data = {
                            "success": False,
                            "error": "No patient data provided in request body"
                        }
                    else:
                        # Ensure required fields
                        if 'id' not in patient_data:
                            patient_data['id'] = patient_data.get('patientId', str(int(time.time())))
                        if 'patientId' not in patient_data:
                            patient_data['patientId'] = patient_data['id']
                            
                        # Add metadata
                        patient_data['createdAt'] = int(time.time())
                        patient_data['updatedAt'] = int(time.time())
                        
                        # Create patient
                        response = cosmos_manager.patients_container.create_item(body=patient_data)
                        
                        response_data = {
                            "success": True,
                            "patient": response,
                            "message": f"Patient created successfully with ID: {patient_data['id']}"
                        }
                    
                except Exception as e:
                    logging.error(f"Error creating patient: {str(e)}")
                    response_data = {
                        "success": False,
                        "error": f"Failed to create patient: {str(e)}"
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
            logging.error(f"Patient management error: {str(e)}")
            
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

    @app.route(route="patients/{patient_id}", methods=["GET", "PUT", "DELETE", "OPTIONS"])
    def manage_patient(req: func.HttpRequest) -> func.HttpResponse:
        """Individual patient management - GET/PUT/DELETE by patient ID"""
        # Handle CORS preflight requests
        if req.method == "OPTIONS":
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '86400'
            }
            return func.HttpResponse("", status_code=200, headers=headers)
        
        patient_id = req.route_params.get('patient_id')
        if not patient_id:
            return func.HttpResponse(
                json.dumps({"error": "Patient ID is required"}),
                status_code=400,
                mimetype="application/json"
            )
        
        logging.info(f'Patient {req.method}: {patient_id}')
        
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
                # Get patient by ID
                try:
                    response = cosmos_manager.patients_container.read_item(item=patient_id, partition_key=patient_id)
                    response_data = {
                        "success": True,
                        "patient": response,
                        "message": f"Patient retrieved successfully: {patient_id}"
                    }
                except Exception as e:
                    if "NotFound" in str(e):
                        response_data = {
                            "success": False,
                            "error": f"Patient with ID {patient_id} not found"
                        }
                    else:
                        response_data = {
                            "success": False,
                            "error": f"Failed to retrieve patient: {str(e)}"
                        }
                        
            elif req.method == "PUT":
                # Update patient
                try:
                    updates = req.get_json()
                    if not updates:
                        raise Exception("No update data provided")
                    
                    # Get existing patient first
                    existing_patient = cosmos_manager.patients_container.read_item(item=patient_id, partition_key=patient_id)
                    
                    # Update fields
                    existing_patient.update(updates)
                    existing_patient['updatedAt'] = int(time.time())
                    
                    response = cosmos_manager.patients_container.replace_item(item=patient_id, body=existing_patient)
                    response_data = {
                        "success": True,
                        "patient": response,
                        "message": f"Patient updated successfully: {patient_id}"
                    }
                    
                except Exception as e:
                    if "NotFound" in str(e):
                        response_data = {
                            "success": False,
                            "error": f"Patient with ID {patient_id} not found"
                        }
                    else:
                        response_data = {
                            "success": False,
                            "error": f"Failed to update patient: {str(e)}"
                        }
                        
            elif req.method == "DELETE":
                # Delete patient
                try:
                    cosmos_manager.patients_container.delete_item(item=patient_id, partition_key=patient_id)
                    response_data = {
                        "success": True,
                        "message": f"Patient deleted successfully: {patient_id}"
                    }
                except Exception as e:
                    if "NotFound" in str(e):
                        response_data = {
                            "success": False,
                            "error": f"Patient with ID {patient_id} not found"
                        }
                    else:
                        response_data = {
                            "success": False,
                            "error": f"Failed to delete patient: {str(e)}"
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
            logging.error(f"Patient management error: {str(e)}")
            
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
