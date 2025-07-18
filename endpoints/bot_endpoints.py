"""
Bot Service Endpoints
Handles Azure Bot Service integration and conversation handling
"""

import azure.functions as func
import logging
import json
import os
from services.cosmos_manager import cosmos_manager
from services.bot_service import (
    process_bot_message_sync, 
    create_bot_response
)


def register_bot_endpoints(app: func.FunctionApp):
    """Register Bot Service endpoints with the Function App"""
    
    # Configuration from environment variables
    ACS_CONNECTION_STRING = os.environ.get("ACS_CONNECTION_STRING", "")
    COGNITIVE_SERVICES_ENDPOINT = os.environ.get("COGNITIVE_SERVICES_ENDPOINT", "")
    TARGET_USER_ID = os.environ.get("TARGET_USER_ID", "")
    TARGET_PHONE_NUMBER = os.environ.get("TARGET_PHONE_NUMBER", "+917447474405")
    SOURCE_CALLER_ID = os.environ.get("SOURCE_CALLER_ID", "")

    @app.route(route="bot/messages", methods=["POST", "OPTIONS"])
    def bot_messages(req: func.HttpRequest) -> func.HttpResponse:
        """Main bot endpoint to handle incoming messages from Azure Bot Service"""
        # Handle CORS preflight requests
        if req.method == "OPTIONS":
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization',
                'Access-Control-Max-Age': '86400'
            }
            return func.HttpResponse("", status_code=200, headers=headers)
        
        logging.info('Bot messages endpoint called')
        
        try:
            # Get the activity from the request body
            activity_data = req.get_json()
            if not activity_data:
                logging.error("No activity data received")
                return func.HttpResponse(
                    json.dumps({"error": "No activity data received"}),
                    status_code=400,
                    mimetype="application/json"
                )
            
            logging.info(f"Activity type: {activity_data.get('type')}, Text: {activity_data.get('text')}")
            
            # Only process message activities
            if activity_data.get('type') != 'message':
                return func.HttpResponse(
                    json.dumps({"type": "message", "text": "Hello! I'm ready to help."}),
                    status_code=200,
                    mimetype="application/json"
                )
            
            # Process the message using the bot service module
            bot_result = process_bot_message_sync(activity_data)
            response_text = bot_result.get('response_text', 'I understand your message.')
            
            # Log call information if applicable
            if bot_result.get('call_initiated'):
                logging.info(f"Bot successfully initiated call. Call ID: {bot_result.get('call_id')}")
            elif bot_result.get('call_error'):
                logging.error(f"Bot failed to initiate call: {bot_result.get('call_error')}")
            
            # Create bot response using the bot service module
            response_activity = create_bot_response(activity_data, response_text)
            
            # Return the response activity
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization'
            }
            
            return func.HttpResponse(
                json.dumps(response_activity),
                status_code=200,
                mimetype="application/json",
                headers=headers
            )
            
        except json.JSONDecodeError:
            logging.error("Invalid JSON in request body")
            return func.HttpResponse(
                json.dumps({"error": "Invalid JSON in request body"}),
                status_code=400,
                mimetype="application/json"
            )
        except Exception as e:
            logging.error(f"Unexpected error in bot endpoint: {str(e)}")
            return func.HttpResponse(
                json.dumps({"error": f"Unexpected error: {str(e)}"}),
                status_code=500,
                mimetype="application/json"
            )

    @app.route(route="test_bot_call", methods=["GET", "POST", "OPTIONS"])
    def test_bot_call(req: func.HttpRequest) -> func.HttpResponse:
        """Test endpoint to simulate bot message and call initiation"""
        # Handle CORS preflight requests
        if req.method == "OPTIONS":
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '86400'
            }
            return func.HttpResponse("", status_code=200, headers=headers)
        
        logging.info('Test bot call endpoint called')
        
        try:
            # Get test message from query params or request body
            test_message = req.params.get('message', 'call the patient')
            custom_message = req.params.get('customMessage')
            
            if req.method == "POST":
                try:
                    req_body = req.get_json()
                    if req_body:
                        test_message = req_body.get('message', test_message)
                        custom_message = req_body.get('customMessage', custom_message)
                except ValueError:
                    pass
            
            logging.info(f"Testing bot with message: '{test_message}'")
            
            # Create a simulated bot activity
            test_activity = {
                "type": "message",
                "text": test_message,
                "from": {"id": "test-user", "name": "Test User"},
                "conversation": {"id": "test-conversation"},
                "id": "test-message-id",
                "serviceUrl": "https://test.botframework.com",
                "channelId": "test"
            }
            
            # If custom message is provided, append it
            if custom_message:
                test_activity["text"] += f" and say '{custom_message}'"
            
            # Process the message using the bot service module
            bot_result = process_bot_message_sync(test_activity)
            
            # Add CORS headers
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
            
            response_data = {
                "success": True,
                "testMessage": test_message,
                "botResponse": bot_result.get('response_text'),
                "callInitiated": bot_result.get('call_initiated', False),
                "callId": bot_result.get('call_id'),
                "callError": bot_result.get('call_error'),
                "configuration": {
                    "acsConfigured": bool(ACS_CONNECTION_STRING),
                    "cognitiveServicesConfigured": bool(COGNITIVE_SERVICES_ENDPOINT),
                    "targetUserIdConfigured": bool(TARGET_USER_ID),
                    "targetPhoneConfigured": bool(TARGET_PHONE_NUMBER),
                    "sourceCallerIdConfigured": bool(SOURCE_CALLER_ID),
                    "cosmosDbConfigured": cosmos_manager.is_connected()
                }
            }
            
            return func.HttpResponse(
                json.dumps(response_data, indent=2),
                status_code=200,
                mimetype="application/json",
                headers=headers
            )
            
        except Exception as e:
            logging.error(f"Error in test_bot_call: {str(e)}")
            
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
            
            return func.HttpResponse(
                json.dumps({"success": False, "error": str(e)}),
                status_code=500,
                mimetype="application/json",
                headers=headers
            )
