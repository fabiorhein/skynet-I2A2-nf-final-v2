"""Quick helper to test storage selection in app.py."""
import os

def which_storage():
    if os.getenv('SUPABASE_URL') and os.getenv('SUPABASE_KEY'):
        return 'supabase'
    return 'local'

if __name__ == '__main__':
    print('Storage selected:', which_storage())
