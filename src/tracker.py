import requests
import os
from dotenv import load_dotenv
import google.generativeai as genai
from supabase import create_client

# --- Setup AI and Cloud DB ---
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase = create_client(supabase_url, supabase_key)

def search_hacker_news(query):
    """Searches Hacker News for recent comments about the target."""
    url = f"https://hn.algolia.com/api/v1/search?query={query}&tags=comment"
    try:
        response = requests.get(url)
        data = response.json()
        # Grab top 3 comments and clean out newlines
        comments = [hit['comment_text'].replace('\n', ' ') for hit in data.get('hits', [])[:3]]
        return " ".join(comments)
    except:
        return ""

def run_tracker():
    print("Starting the V2 Batch Tracker...\n")
    
    # 1. Ask Supabase for everything we are tracking
    response = supabase.table('targets').select('*').eq('status', 'tracking').execute()
    targets = response.data
    
    if not targets:
        print("No targets found in the database. Run the scout first!")
        return

    # --- PHASE 1: GATHER ALL DATA (0 API Calls) ---
    batch_payload = []
    target_map = {} # We use this dictionary to remember which ID belongs to which name
    
    for t in targets:
        name = t['name']
        t_id = t['id']
        
        print(f"📡 Fetching HN comments for: {name}...")
        comments = search_hacker_news(name)
        
        if comments.strip():
            batch_payload.append(f"TARGET: {name}\nCOMMENTS: {comments}\n---")
            target_map[name] = t_id
            
    if not batch_payload:
        print("No internet chatter found for any targets today.")
        return

    print(f"\nGathered comments for {len(batch_payload)} targets.")
    print("Sending ONE batch request to the AI...\n")
    
    # --- PHASE 2: BATCH AI ANALYSIS (1 API Call) ---
    batch_text = "\n".join(batch_payload)
    
    prompt = f"""
    You are a sentiment analysis engine. Read the following internet comments about various tech targets.
    Identify the main Pros and Cons for EACH target based *only* on the comments provided.
    
    Format your response exactly like this, with one target per line:
    [Target Name] | PROS: [short summary] | CONS: [short summary]
    
    Data:
    {batch_text}
    """
    
    try:
        ai_response = model.generate_content(prompt)
        lines = ai_response.text.strip().split('\n')
        
        for line in lines:
            if "|" in line and "PROS:" in line and "CONS:" in line:
                parts = line.split("|")
                name_part = parts[0].strip()
                pros_part = parts[1].replace("PROS:", "").strip()
                cons_part = parts[2].replace("CONS:", "").strip()
                
                # Match the AI's name back to our database ID
                t_id = target_map.get(name_part)
                
                if t_id:
                    sentiment_data = {
                        "target_id": t_id,
                        "pros": pros_part,
                        "cons": cons_part
                    }
                    supabase.table('sentiment').insert(sentiment_data).execute()
                    print(f"   💾 SAVED SENTIMENT FOR: {name_part}")
                    
        print("\n✅ Tracker completed successfully.")
        
    except Exception as e:
        print(f"⚠️ AI API Error (You might still be out of quota!): {e}")

if __name__ == "__main__":
    run_tracker()