"""
Phone Calling Endpoints (PSTN)
Handles PSTN phone calling functionality and webhooks with integrated bot service
"""

import azure.functions as func
import logging
import json
import os
from services.phone_calling import (
    create_pstn_call, 
    handle_pstn_webhook_event, 
    get_call_status as get_pstn_call_status
)
from services.bot_service import generate_response_sync


def register_phone_endpoints(app: func.FunctionApp):
    """Register PSTN phone calling endpoints with the Function App"""
    
    # Configuration from environment variables
    TARGET_PHONE_NUMBER = os.environ.get("TARGET_PHONE_NUMBER", "+917447474405")

    @app.route(route="make_phone_call", methods=["GET", "POST", "OPTIONS"])
    def make_phone_call(req: func.HttpRequest) -> func.HttpResponse:
        """Create a PSTN call to a phone number with configurable parameters"""
        # Handle CORS preflight requests
        if req.method == "OPTIONS":
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '86400'
            }
            return func.HttpResponse("", status_code=200, headers=headers)
        
        logging.info('PSTN phone call endpoint called')
        
        try:
            # Get parameters from query string or request body
            target_phone = req.params.get('phoneNumber') or req.params.get('phone')
            custom_message = req.params.get('message')
            custom_voice = req.params.get('voice')
            
            # Check if parameters were provided in request body (for POST requests)
            if req.method == "POST":
                try:
                    req_body = req.get_json()
                    if req_body:
                        target_phone = target_phone or req_body.get('phoneNumber') or req_body.get('phone')
                        custom_message = custom_message or req_body.get('message')
                        custom_voice = custom_voice or req_body.get('voice')
                except ValueError:
                    pass
            
            # Use provided phone number or default
            if not target_phone:
                target_phone = TARGET_PHONE_NUMBER
                
            if not target_phone:
                return func.HttpResponse(
                    json.dumps({
                        "error": "Phone number is required. Provide via 'phoneNumber' parameter or set TARGET_PHONE_NUMBER environment variable.",
                        "example": "?phoneNumber=+917447474405"
                    }),
                    status_code=400,
                    mimetype="application/json"
                )
            
            # Create the PSTN call using the phone calling module
            call_result = create_pstn_call(
                target_phone=target_phone,
                custom_message=custom_message,
                custom_voice=custom_voice
            )
            
            # Add CORS headers
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
            
            status_code = 200 if call_result['success'] else 500
            
            return func.HttpResponse(
                json.dumps(call_result, indent=2),
                status_code=status_code,
                mimetype="application/json",
                headers=headers
            )
            
        except Exception as e:
            logging.error(f"Error in make_phone_call: {str(e)}")
            
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
            
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": f"Failed to create PSTN call: {str(e)}",
                    "call_type": "PSTN"
                }),
                status_code=500,
                mimetype="application/json",
                headers=headers
            )

    @app.route(route="make_smart_phone_call", methods=["GET", "POST", "OPTIONS"])
    def make_smart_phone_call(req: func.HttpRequest) -> func.HttpResponse:
        """Create a PSTN call with AI-generated greeting message"""
        # Handle CORS preflight requests
        if req.method == "OPTIONS":
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '86400'
            }
            return func.HttpResponse("", status_code=200, headers=headers)
        
        logging.info('Smart PSTN phone call endpoint called')
        
        try:
            # Get parameters from query string or request body
            target_phone = req.params.get('phoneNumber') or req.params.get('phone')
            call_purpose = req.params.get('purpose') or req.params.get('reason')
            custom_voice = req.params.get('voice')
            patient_name = req.params.get('patientName') or req.params.get('name')
            
            # Check if parameters were provided in request body (for POST requests)
            if req.method == "POST":
                try:
                    req_body = req.get_json()
                    if req_body:
                        target_phone = target_phone or req_body.get('phoneNumber') or req_body.get('phone')
                        call_purpose = call_purpose or req_body.get('purpose') or req_body.get('reason')
                        custom_voice = custom_voice or req_body.get('voice')
                        patient_name = patient_name or req_body.get('patientName') or req_body.get('name')
                except ValueError:
                    pass
            
            # Use provided phone number or default
            if not target_phone:
                target_phone = TARGET_PHONE_NUMBER
                
            if not target_phone:
                return func.HttpResponse(
                    json.dumps({
                        "error": "Phone number is required. Provide via 'phoneNumber' parameter or set TARGET_PHONE_NUMBER environment variable.",
                        "example": "?phoneNumber=+917447474405&purpose=appointment reminder"
                    }),
                    status_code=400,
                    mimetype="application/json"
                )
            
            # Generate intelligent greeting message using bot service
            try:
                if call_purpose:
                    bot_prompt = f"Generate a professional healthcare greeting message for a phone call. Purpose: {call_purpose}"
                    if patient_name:
                        bot_prompt += f". Patient name: {patient_name}"
                    bot_prompt += ". Keep it under 30 seconds when spoken and sound natural and caring."
                else:
                    bot_prompt = "Generate a professional healthcare greeting message for a general phone call. Keep it under 30 seconds when spoken and sound natural and caring."
                
                logging.info(f"Generating smart greeting with bot service: '{bot_prompt}'")
                smart_message = generate_response_sync(bot_prompt)
                
                if not smart_message or not smart_message.strip():
                    # Fallback to default message
                    smart_message = f"Hello{f' {patient_name}' if patient_name else ''}! This is your healthcare assistant calling{f' regarding {call_purpose}' if call_purpose else ''}. How can I help you today?"
                    logging.warning("Bot service returned empty message, using fallback")
                else:
                    logging.info(f"Generated smart message: '{smart_message[:100]}...'")
                    
            except Exception as bot_error:
                logging.error(f"Bot service failed for greeting generation: {str(bot_error)}")
                # Fallback to basic personalized message
                smart_message = f"Hello{f' {patient_name}' if patient_name else ''}! This is your healthcare assistant calling{f' regarding {call_purpose}' if call_purpose else ''}. How can I help you today?"
            
            # Create the PSTN call with the smart message
            call_result = create_pstn_call(
                target_phone=target_phone,
                custom_message=smart_message,
                custom_voice=custom_voice
            )
            
            # Add bot-related info to the response
            if call_result.get('success'):
                call_result['smart_features'] = {
                    'ai_generated_greeting': True,
                    'call_purpose': call_purpose,
                    'patient_name': patient_name,
                    'conversational_ai_enabled': True
                }
            
            # Add CORS headers
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
            
            status_code = 200 if call_result['success'] else 500
            
            return func.HttpResponse(
                json.dumps(call_result, indent=2),
                status_code=status_code,
                mimetype="application/json",
                headers=headers
            )
            
        except Exception as e:
            logging.error(f"Error in make_smart_phone_call: {str(e)}")
            
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
            
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": f"Failed to create smart PSTN call: {str(e)}",
                    "call_type": "PSTN",
                    "smart_features_attempted": True
                }),
                status_code=500,
                mimetype="application/json",
                headers=headers
            )

    @app.route(route="phone_call_webhook", methods=["POST"])
    def phone_call_webhook(req: func.HttpRequest) -> func.HttpResponse:
        """Webhook endpoint for PSTN phone call events"""
        logging.info('PSTN phone call webhook called')
        
        try:
            # Get the event data
            event_data = req.get_body().decode('utf-8')
            logging.info(f"Raw webhook event data: {event_data}")
            
            # Parse the JSON event
            events = json.loads(event_data)
            if not isinstance(events, list):
                events = [events]
            
            # Process each event using the phone calling module
            for event in events:
                success = handle_pstn_webhook_event(event)
                if not success:
                    logging.warning(f"Failed to handle event: {event.get('type', 'Unknown')}")
            
            return func.HttpResponse(
                "PSTN webhook processed successfully",
                status_code=200
            )
            
        except json.JSONDecodeError as json_error:
            logging.error(f"Invalid JSON in webhook request: {str(json_error)}")
            return func.HttpResponse(
                "Invalid JSON in request body",
                status_code=400
            )
            
        except Exception as e:
            logging.error(f"Error processing PSTN webhook: {str(e)}")
            return func.HttpResponse(
                f"Error processing PSTN webhook: {str(e)}",
                status_code=500
            )

    @app.route(route="get_call_status", methods=["GET"])
    def get_call_status(req: func.HttpRequest) -> func.HttpResponse:
        """Get the status of a call by call ID"""
        logging.info('Call status endpoint called')
        
        try:
            call_id = req.params.get('callId')
            
            if not call_id:
                return func.HttpResponse(
                    json.dumps({"error": "callId parameter is required"}),
                    status_code=400,
                    mimetype="application/json"
                )
            
            # Get call status (works for both PSTN and VoIP calls)
            status_result = get_pstn_call_status(call_id)
            
            # Add CORS headers
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
            
            return func.HttpResponse(
                json.dumps(status_result, indent=2),
                status_code=200,
                mimetype="application/json",
                headers=headers
            )
            
        except Exception as e:
            logging.error(f"Error getting call status: {str(e)}")
            
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
            
            return func.HttpResponse(
                json.dumps({"error": f"Failed to get call status: {str(e)}"}),
                status_code=500,
                mimetype="application/json",
                headers=headers
            )

    @app.route(route="get_conversation_history", methods=["GET"])
    def get_conversation_history(req: func.HttpRequest) -> func.HttpResponse:
        """Get conversation history for a specific call"""
        logging.info('Get conversation history endpoint called')
        
        try:
            call_id = req.params.get('callId')
            
            if not call_id:
                return func.HttpResponse(
                    json.dumps({"error": "callId parameter is required"}),
                    status_code=400,
                    mimetype="application/json"
                )
            
            # Get conversation state from the phone calling module
            from services.phone_calling import get_conversation_state
            conversation_state = get_conversation_state(call_id)
            
            # Add CORS headers
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
            
            response_data = {
                "call_id": call_id,
                "conversation_state": conversation_state,
                "has_active_conversation": bool(conversation_state)
            }
            
            return func.HttpResponse(
                json.dumps(response_data, indent=2),
                status_code=200,
                mimetype="application/json",
                headers=headers
            )
            
        except Exception as e:
            logging.error(f"Error getting conversation history: {str(e)}")
            
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
            
            return func.HttpResponse(
                json.dumps({"error": f"Failed to get conversation history: {str(e)}"}),
                status_code=500,
                mimetype="application/json",
                headers=headers
            )
