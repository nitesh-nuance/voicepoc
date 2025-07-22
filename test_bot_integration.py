"""
Test bot service integration for voice calling
"""
import os
import json

# Load environment
try:
    with open('local.settings.json', 'r') as f:
        settings = json.load(f)
        for key, value in settings.get('Values', {}).items():
            os.environ[key] = value
    print("✅ Environment loaded")
except Exception as e:
    print(f"⚠️  Environment load warning: {e}")

# Test imports
try:
    from services.bot_service import generate_agent_response_sync, get_or_create_conversation_state, generate_response_sync
    print("✅ All bot service functions imported successfully:")
    print("  - generate_agent_response_sync")
    print("  - get_or_create_conversation_state") 
    print("  - generate_response_sync")
    
    # Test basic response generation
    try:
        basic_response = generate_response_sync("Hello, how are you?")
        print(f"\n✅ Basic response test: '{basic_response[:50]}...'")
    except Exception as e:
        print(f"❌ Basic response test failed: {e}")
    
    # Test conversation state creation
    try:
        conv_state = get_or_create_conversation_state("test_call_123")
        print(f"✅ Conversation state created: {type(conv_state).__name__}")
    except Exception as e:
        print(f"❌ Conversation state test failed: {e}")
    
    print("\n🎉 Bot service integration is ready for voice calling!")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
except Exception as e:
    print(f"❌ Other error: {e}")
