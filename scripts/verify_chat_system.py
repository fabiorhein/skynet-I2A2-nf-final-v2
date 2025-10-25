"""
Quick verification script for the chat system.

This script checks if all components are working correctly.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def verify_chat_system():
    """Verify chat system components."""

    print("🔍 Chat System Verification")
    print("=" * 40)

    # Check database tables
    try:
        from backend.storage import DatabaseManager
        db = DatabaseManager()
        db.connect()

        # Check chat tables
        chat_tables = ['chat_sessions', 'chat_messages', 'analysis_cache', 'document_summaries']
        existing_tables = []

        for table in chat_tables:
            try:
                result = db.execute_query(f"SELECT 1 FROM {table} LIMIT 1")
                existing_tables.append(table)
                print(f"✅ {table}: Available")
            except Exception as e:
                print(f"❌ {table}: Not available - {str(e)[:50]}")

        print(f"\n📊 Database: {len(existing_tables)}/{len(chat_tables)} tables ready")

    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

    # Check configuration
    try:
        import config
        print("✅ Configuration: Loaded successfully")
    except Exception as e:
        print(f"❌ Configuration failed: {e}")
        return False

    # Check secrets
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and 'GOOGLE_API_KEY' in st.secrets:
            print("✅ API Key: Configured")
        else:
            print("⚠️  API Key: Not configured (add to .streamlit/secrets.toml)")
    except Exception as e:
        print(f"⚠️  Secrets: Check .streamlit/secrets.toml file - {e}")

    print("\n🚀 Verification Complete!")
    print("\n💡 Next steps:")
    print("   1. Ensure GOOGLE_API_KEY in .streamlit/secrets.toml")
    print("   2. Run: streamlit run app.py")
    print("   3. Navigate to 'Chat IA' tab")
    print("   4. Start chatting with your documents!")

    return True

if __name__ == "__main__":
    verify_chat_system()
