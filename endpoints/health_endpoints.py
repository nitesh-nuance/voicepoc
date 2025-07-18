"""
Health and Token Endpoints
Handles health checks and Azure Communication Services token generation
"""

import azure.functions as func
import logging
import json
import time
import os
from azure.communication.identity import CommunicationIdentityClient
from services.cosmos_manager import cosmos_manager


def register_health_endpoints(app: func.FunctionApp):
    """Register health and token endpoints with the Function App"""
    
    # Configuration from environment variables
    ACS_CONNECTION_STRING = os.environ.get("ACS_CONNECTION_STRING", "")
    COGNITIVE_SERVICES_ENDPOINT = os.environ.get("COGNITIVE_SERVICES_ENDPOINT", "")
    TARGET_USER_ID = os.environ.get("TARGET_USER_ID", "")
    TARGET_PHONE_NUMBER = os.environ.get("TARGET_PHONE_NUMBER", "+917447474405")
    SOURCE_CALLER_ID = os.environ.get("SOURCE_CALLER_ID", "")

    @app.route(route="health_check", methods=["GET"])
    def health_check(req: func.HttpRequest) -> func.HttpResponse:
        """Health check endpoint to verify service is running"""
        logging.info('Health check endpoint called')
        
        # Check configuration status
        config_status = {
            "acs_configured": bool(ACS_CONNECTION_STRING),
            "cognitive_services_configured": bool(COGNITIVE_SERVICES_ENDPOINT),
            "cosmos_db_configured": cosmos_manager.is_connected(),
            "target_user_configured": bool(TARGET_USER_ID),
            "target_phone_configured": bool(TARGET_PHONE_NUMBER),
            "source_caller_id_configured": bool(SOURCE_CALLER_ID)
        }
        
        all_healthy = all(config_status.values())
        
        response_data = {
            "status": "healthy" if all_healthy else "partial",
            "timestamp": int(time.time()),
            "configuration": config_status,
            "version": "2.0-refactored-endpoints"
        }
        
        return func.HttpResponse(
            json.dumps(response_data, indent=2),
            status_code=200 if all_healthy else 206,
            mimetype="application/json"
        )

    @app.route(route="get_token", methods=["GET", "POST", "OPTIONS"])
    def get_token(req: func.HttpRequest) -> func.HttpResponse:
        """Generate Azure Communication Services access token"""
        # Handle CORS preflight requests
        if req.method == "OPTIONS":
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization',
                'Access-Control-Max-Age': '86400'
            }
            return func.HttpResponse("", status_code=200, headers=headers)
        
        logging.info('Token generation endpoint called')
        
        if not ACS_CONNECTION_STRING:
            return func.HttpResponse(
                json.dumps({"error": "ACS_CONNECTION_STRING not configured"}),
                status_code=500,
                mimetype="application/json"
            )
        
        try:
            # Create identity client
            identity_client = CommunicationIdentityClient.from_connection_string(ACS_CONNECTION_STRING)
            
            # Create user and token
            user = identity_client.create_user()
            token_result = identity_client.get_token(user, ["voip"])
            
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization'
            }
            
            response_data = {
                "success": True,
                "user_id": user.properties['id'],
                "access_token": token_result.token,
                "expires_on": str(token_result.expires_on)
            }
            
            return func.HttpResponse(
                json.dumps(response_data),
                status_code=200,
                mimetype="application/json",
                headers=headers
            )
            
        except Exception as e:
            logging.error(f"Error generating token: {str(e)}")
            return func.HttpResponse(
                json.dumps({"error": f"Failed to generate token: {str(e)}"}),
                status_code=500,
                mimetype="application/json"
            )
