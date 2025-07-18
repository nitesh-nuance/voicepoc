"""
Azure Functions App - Modular Endpoint Architecture
Voice Phone Agent with separated endpoint modules for maximum maintainability
Version: 3.0 - Modular Endpoints
"""

import azure.functions as func
import logging
import os
import json
import time
from typing import Optional, Any, Dict, List

# Load local.settings.json for development
def load_local_settings():
    """Load environment variables from local.settings.json during development"""
    try:
        if not os.environ.get('AZURE_FUNCTIONS_ENVIRONMENT'):
            with open('local.settings.json', 'r') as f:
                settings = json.load(f)
                for key, value in settings.get('Values', {}).items():
                    if key not in os.environ:
                        os.environ[key] = value
                logging.info("Loaded local.settings.json for development")
    except FileNotFoundError:
        logging.warning("local.settings.json not found")
    except Exception as e:
        logging.error(f"Error loading local.settings.json: {e}")

# Load settings at module level
load_local_settings()

# Initialize the Function App
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Import and register all endpoint modules
from endpoints.health_endpoints import register_health_endpoints
from endpoints.phone_endpoints import register_phone_endpoints
from endpoints.voip_endpoints import register_voip_endpoints
from endpoints.bot_endpoints import register_bot_endpoints
from endpoints.patient_endpoints import register_patient_endpoints
from endpoints.appointment_endpoints import register_appointment_endpoints

# Register all endpoint modules
register_health_endpoints(app)
register_phone_endpoints(app)
register_voip_endpoints(app)
register_bot_endpoints(app)
register_patient_endpoints(app)
register_appointment_endpoints(app)

# Add a special endpoint to provide information about the modular architecture
@app.route(route="architecture_info", methods=["GET"])
def architecture_info(req: func.HttpRequest) -> func.HttpResponse:
    """Information about the modular endpoint architecture"""
    
    architecture_details = {
        "version": "4.0-services-organized",
        "refactoring_date": "2025-01-18",
        "architecture": {
            "description": "Modular endpoint architecture with organized service layer",
            "structure": {
                "function_app.py": "Main Azure Functions app entry point - registers endpoint modules",
                "services/": {
                    "cosmos_manager.py": "Azure Cosmos DB operations for patients and appointments",
                    "phone_calling.py": "PSTN phone calling functionality",
                    "voip_calling.py": "VoIP calling functionality for Communication Service users",
                    "bot_service.py": "Azure Bot Service integration and conversation handling"
                },
                "endpoints/": {
                    "health_endpoints.py": "Health check and token generation endpoints",
                    "phone_endpoints.py": "PSTN calling endpoints (make_phone_call, webhook, status)",
                    "voip_endpoints.py": "VoIP calling endpoints (voip_call, webhook, test_call)",
                    "bot_endpoints.py": "Bot service endpoints (bot/messages, test_bot_call)",
                    "patient_endpoints.py": "Patient management CRUD endpoints",
                    "appointment_endpoints.py": "Appointment management CRUD endpoints"
                }
            }
        },
        "benefits": [
            "Maximum code organization and maintainability",
            "Clear separation of concerns: endpoints/ for API layer, services/ for business logic",
            "Each module can be independently modified and tested",
            "Minimal function_app.py with focused responsibility as orchestrator",
            "Easy to add new modules without touching existing code",
            "Better development team collaboration - clear ownership boundaries",
            "Service layer can be reused across different endpoint modules"
        ],
        "endpoint_modules": {
            "health_endpoints": ["health_check", "get_token"],
            "phone_endpoints": ["make_phone_call", "phone_call_webhook", "get_call_status"],
            "voip_endpoints": ["make_voip_call", "voip_call_webhook", "make_test_call"],
            "bot_endpoints": ["bot/messages", "test_bot_call"],
            "patient_endpoints": ["patients", "patients/{patient_id}"],
            "appointment_endpoints": ["appointments", "appointments/{appointment_id}"]
        },
        "total_endpoints": 12,
        "deployment_compatibility": {
            "azure_functions_v1": True,
            "azure_functions_v2": True,
            "local_development": True,
            "existing_configuration": "Fully compatible - no configuration changes needed",
            "scaling": "Each endpoint module can be optimized independently"
        },
        "development_workflow": {
            "adding_endpoints": "Create new endpoint module in endpoints/ folder and register in function_app.py",
            "adding_services": "Create new service module in services/ folder and import in endpoint modules",
            "modifying_endpoints": "Edit the specific endpoint module file in endpoints/",
            "modifying_business_logic": "Edit the specific service module file in services/",
            "testing": "Each endpoint and service module can be unit tested independently",
            "debugging": "Clear separation makes debugging easier and faster"
        }
    }
    
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET',
        'Access-Control-Allow-Headers': 'Content-Type'
    }
    
    return func.HttpResponse(
        json.dumps(architecture_details, indent=2),
        status_code=200,
        mimetype="application/json",
        headers=headers
    )

# Legacy endpoint for backward compatibility
@app.route(route="refactor_info", methods=["GET"])
def refactor_info(req: func.HttpRequest) -> func.HttpResponse:
    """Legacy endpoint - redirects to architecture_info"""
    return architecture_info(req)

if __name__ == "__main__":
    logging.info("Azure Functions App initialized with organized service architecture")
    logging.info("Available services: cosmos_manager, phone_calling, voip_calling, bot_service")
    logging.info("Available endpoint modules: health, phone, voip, bot, patient, appointment")
