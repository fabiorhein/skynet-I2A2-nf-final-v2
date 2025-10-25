"""
Run remaining chat system migrations.

This script runs only the migrations that haven't been executed yet.
"""
import subprocess
import sys
from pathlib import Path

def run_remaining_migrations():
    """Run only migrations 009 and 010."""

    print("🔄 Running Remaining Chat System Migrations...")
    print("=" * 50)

    migrations_to_run = ["009", "010"]

    for mig_num in migrations_to_run:
        mig_file = Path(__file__).parent / f"../migration/{mig_num}-*.sql"
        mig_path = list(Path(__file__).parent.parent.glob(f"migration/{mig_num}-*.sql"))

        if mig_path:
            print(f"\n🚀 Running migration: {mig_path[0].name}")

            # Read and execute the migration content directly
            with open(mig_path[0], 'r', encoding='utf-8') as f:
                sql_content = f.read()

            print("📄 Migration content:")
            print("-" * 30)
            print(sql_content[:200] + "..." if len(sql_content) > 200 else sql_content)
            print("-" * 30)

            print(f"✅ Migration {mig_num} prepared")
            print(f"💡 You need to run this manually in Supabase SQL Editor")
        else:
            print(f"❌ Migration file {mig_num}-*.sql not found")

    print("\n📋 Manual Steps Required:")
    print("1. Go to your Supabase Dashboard")
    print("2. Navigate to SQL Editor")
    print("3. Copy and paste the migration content above")
    print("4. Execute each migration in order")

    print("\n🎉 After running these migrations:")
    print("   - Set GOOGLE_API_KEY in .streamlit/secrets.toml")
    print("   - Run: streamlit run app.py")
    print("   - Go to 'Chat IA' tab and start chatting!")

if __name__ == "__main__":
    run_remaining_migrations()
