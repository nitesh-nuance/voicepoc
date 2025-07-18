"""
VoIP Calling Endpoints
Handles VoIP calling functionality for Communication Service users
"""

import azure.functions as func
import logging
import json
import os
from services.voip_calling import (
    create_voip_call, 
    handle_voip_webhook_event, 
    create_test_voip_call_no_webhook
)


def register_voip_endpoints(app: func.FunctionApp):
    """Register VoIP calling endpoints with the Function App"""
    
    # Configuration from environment variables
    TARGET_USER_ID = os.environ.get("TARGET_USER_ID", "")

    @app.route(route="make_voip_call", methods=["GET", "POST", "OPTIONS"])
    def make_voip_call(req: func.HttpRequest) -> func.HttpResponse:
        """Create a VoIP call to a Communication Service user"""
        # Handle CORS preflight requests
        if req.method == "OPTIONS":
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '86400'
            }
            return func.HttpResponse("", status_code=200, headers=headers)
        
        logging.info('VoIP call endpoint called')
        
        try:
            # Get parameters
            target_user_id = req.params.get('userId') or req.params.get('user_id')
            custom_message = req.params.get('message')
            custom_voice = req.params.get('voice')
            
            # Check request body for POST requests
            if req.method == "POST":
                try:
                    req_body = req.get_json()
                    if req_body:
                        target_user_id = target_user_id or req_body.get('userId') or req_body.get('user_id')
                        custom_message = custom_message or req_body.get('message')
                        custom_voice = custom_voice or req_body.get('voice')
                except ValueError:
                    pass
            
            # Use provided user ID or default
            if not target_user_id:
                target_user_id = TARGET_USER_ID
                
            if not target_user_id:
                return func.HttpResponse(
                    json.dumps({
                        "error": "User ID is required. Provide via 'userId' parameter or set TARGET_USER_ID environment variable.",
                        "example": "?userId=8:acs:..."
                    }),
                    status_code=400,
                    mimetype="application/json"
                )
            
            # Create the VoIP call using the VoIP calling module
            call_result = create_voip_call(
                target_user_id=target_user_id,
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
            logging.error(f"Error in make_voip_call: {str(e)}")
            
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
            
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": f"Failed to create VoIP call: {str(e)}",
                    "call_type": "VoIP"
                }),
                status_code=500,
                mimetype="application/json",
                headers=headers
            )

    @app.route(route="voip_call_webhook", methods=["POST"])
    def voip_call_webhook(req: func.HttpRequest) -> func.HttpResponse:
        """Webhook endpoint for VoIP call events"""
        logging.info('VoIP call webhook called')
        
        try:
            # Get the event data
            event_data = req.get_body().decode('utf-8')
            logging.info(f"Raw VoIP webhook event data: {event_data}")
            
            # Parse the JSON event
            events = json.loads(event_data)
            if not isinstance(events, list):
                events = [events]
            
            # Process each event using the VoIP calling module
            for event in events:
                success = handle_voip_webhook_event(event)
                if not success:
                    logging.warning(f"Failed to handle VoIP event: {event.get('type', 'Unknown')}")
            
            return func.HttpResponse(
                "VoIP webhook processed successfully",
                status_code=200
            )
            
        except json.JSONDecodeError as json_error:
            logging.error(f"Invalid JSON in VoIP webhook request: {str(json_error)}")
            return func.HttpResponse(
                "Invalid JSON in request body",
                status_code=400
            )
            
        except Exception as e:
            logging.error(f"Error processing VoIP webhook: {str(e)}")
            return func.HttpResponse(
                f"Error processing VoIP webhook: {str(e)}",
                status_code=500
            )

    @app.route(route="make_test_call", methods=["GET", "POST", "OPTIONS"])
    def make_test_call(req: func.HttpRequest) -> func.HttpResponse:
        """Create a test VoIP call without webhook dependencies"""
        # Handle CORS preflight requests
        if req.method == "OPTIONS":
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '86400'
            }
            return func.HttpResponse("", status_code=200, headers=headers)
        
        logging.info('Test VoIP call (no webhook) endpoint called')
        
        try:
            # Get parameters
            target_user_id = req.params.get('userId')
            custom_message = req.params.get('message')
            custom_voice = req.params.get('voice')
            delay_seconds = int(req.params.get('delay', '3'))
            
            # Check request body for POST requests
            if req.method == "POST":
                try:
                    req_body = req.get_json()
                    if req_body:
                        target_user_id = target_user_id or req_body.get('userId')
                        custom_message = custom_message or req_body.get('message')
                        custom_voice = custom_voice or req_body.get('voice')
                        delay_seconds = req_body.get('delay', delay_seconds)
                except ValueError:
                    pass
            
            # Create the test call using the VoIP calling module
            call_result = create_test_voip_call_no_webhook(
                target_user_id=target_user_id,
                custom_message=custom_message,
                custom_voice=custom_voice,
                delay_seconds=delay_seconds
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
            logging.error(f"Error in make_test_call: {str(e)}")
            
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
            
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": f"Failed to create test call: {str(e)}",
                    "call_type": "VoIP-Test"
                }),
                status_code=500,
                mimetype="application/json",
                headers=headers
            )
