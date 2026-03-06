import os
from dotenv import load_dotenv
from supabase import create_client

# Load the secret keys
load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

def test_connection():
    try:
        # Create the connection
        supabase = create_client(url, key)
        
        # Try to read from the new 'targets' table
        response = supabase.table('targets').select('*').execute()
        
        print("✅ Connection Successful!")
        print(f"Data found: {response.data} (It should be empty right now!)")
        
    except Exception as e:
        print(f"❌ Connection Failed. Error: {e}")

if __name__ == "__main__":
    test_connection()