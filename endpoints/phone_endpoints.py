"""
Phone Calling Endpoints (PSTN)
Handles PSTN phone calling functionality and webhooks
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
