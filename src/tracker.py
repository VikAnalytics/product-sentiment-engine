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
    url = f"https://hn.algolia.com/api/v1/search?query={query}&tags=comment"
    try:
        response = requests.get(url)
        comments = []
        for hit in response.json().get('hits', [])[:3]:
            text = hit.get('comment_text', '').replace('\n', ' ')
            # Build the exact Hacker News comment URL
            item_url = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            comments.append(f"{text} [URL: {item_url}]")
        return " ".join(comments) if comments else ""
    except:
        return ""

def search_reddit(query):
    formatted_query = query.replace(' ', '%20')
    url = f"https://www.reddit.com/search.json?q={formatted_query}&sort=new&limit=3"
    headers = {"User-Agent": "ProductSentimentEngine/1.0"} 
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200: return ""
        posts = response.json().get('data', {}).get('children', [])
        comments = []
        for p in posts:
            title = p['data'].get('title', '')
            body = p['data'].get('selftext', '')[:150]
            # Build the exact Reddit post URL
            post_url = f"https://www.reddit.com{p['data'].get('permalink', '')}"
            comments.append(f"{title} - {body} [URL: {post_url}]".replace('\n', ' '))
        return " ".join(comments)
    except:
        return ""

def run_tracker():
    print("Starting the V3 Two-Pass Tracker with URL Attribution...\n")
    targets = supabase.table('targets').select('*').eq('status', 'tracking').execute().data
    if not targets: return

    batch_payload = []
    target_map = {} 
    
    for t in targets:
        name = t['name']
        print(f"📡 Fetching intelligence for: {name}...")
        hn_data = search_hacker_news(name)
        reddit_data = search_reddit(name)
        
        combined_chatter = ""
        if hn_data: combined_chatter += f"[SOURCE: Hacker News] {hn_data} "
        if reddit_data: combined_chatter += f"[SOURCE: Reddit] {reddit_data}"
        
        if combined_chatter.strip():
            batch_payload.append(f"TARGET: {name}\nDATA: {combined_chatter}\n---")
            target_map[name] = t['id']
            
    if not batch_payload: return

    # --- PASS 1: EXTRACTION WITH URL ATTRIBUTION ---
    batch_text = "\n".join(batch_payload)
    prompt = f"""
    You are a market intelligence analyst. Read the following internet data.
    For each target, identify the strategic Pros and Cons. 
    Crucially, extract 1 exact verbatim user quote, and include the provided URL where that quote came from.
    
    Format EXACTLY like this (use | to separate):
    [Target Name] | PROS: [summary] | CONS: [summary] | QUOTES: "[Quote]" | URL: [The exact URL provided in the data]
    
    Data:
    {batch_text}
    """
    
    try:
        ai_response = model.generate_content(prompt)
        for line in ai_response.text.strip().split('\n'):
            if "|" in line and "PROS:" in line and "CONS:" in line and "QUOTES:" in line and "URL:" in line:
                # Use maxsplit=4 to avoid breaking if the quote itself contains a | character
                parts = [p.strip() for p in line.split("|", 4)] 
                if len(parts) < 5: continue
                
                name_part = parts[0]
                pros_part = parts[1].replace("PROS:", "").strip()
                cons_part = parts[2].replace("CONS:", "").strip()
                quotes_part = parts[3].replace("QUOTES:", "").strip()
                url_part = parts[4].replace("URL:", "").strip()
                
                t_id = target_map.get(name_part)
                if t_id:
                    # Idempotency check
                    existing = supabase.table('sentiment').select('*').eq('target_id', t_id).execute()
                    if len(existing.data) > 0:
                        print(f"   -> Intelligence for {name_part} already logged.")
                    else:
                        supabase.table('sentiment').insert({
                            "target_id": t_id,
                            "pros": pros_part,
                            "cons": cons_part,
                            "verbatim_quotes": quotes_part,
                            "source_url": url_part # <-- Saving the exact URL to Supabase
                        }).execute()
                        print(f"   💾 SAVED INTELLIGENCE: {name_part}")
    except Exception as e:
        print(f"⚠️ AI API Error: {e}")

if __name__ == "__main__":
    run_tracker()