"""
Test script for the chat system.

This script tests the chat functionality with sample data.
"""
import asyncio
import sys
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.agents.chat_coordinator import ChatCoordinator
from backend.storage import storage_manager


async def test_chat_system():
    """Test the chat system with sample queries."""

    print("🚀 Testing Chat System...")

    try:
        # Initialize chat coordinator
        chat_coordinator = ChatCoordinator(storage_manager.supabase_client)
        print("✅ Chat coordinator initialized")

        # Create a test session
        session_id = await chat_coordinator.initialize_session("Test Session")
        print(f"✅ Test session created: {session_id}")

        # Test queries
        test_queries = [
            "Olá! Como você pode me ajudar?",
            "Quais tipos de documentos fiscais você pode analisar?",
            "Como funciona a análise de dados CSV?",
        ]

        for i, query in enumerate(test_queries, 1):
            print(f"\n📝 Test Query {i}: {query}")
            try:
                response = await chat_coordinator.process_query(
                    session_id=session_id,
                    query=query,
                    context={'query_type': 'general'}
                )

                if response.get('success'):
                    print(f"✅ Response: {response['response'][:100]}...")
                    if response.get('cached'):
                        print("💾 Response from cache")
                    else:
                        print(f"🧠 Tokens used: {response.get('tokens_used', 'N/A')}")
                else:
                    print(f"❌ Error: {response.get('error')}")

            except Exception as e:
                print(f"❌ Query failed: {e}")

        # Test document search
        print("\n🔍 Testing document search...")
        search_results = await chat_coordinator.search_documents("NFe", {"document_type": "NFe"})
        print(f"✅ Found {search_results.get('total', 0)} documents")

        # Get session history
        print("\n📚 Testing session history...")
        history = await chat_coordinator.get_session_history(session_id)
        print(f"✅ Retrieved {len(history)} messages from history")

        print("\n🎉 Chat system test completed successfully!")
        print(f"📊 Session ID: {session_id}")
        print("💡 You can now use the chat system in the Streamlit interface")

    except Exception as e:
        print(f"❌ Chat system test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_chat_system())
