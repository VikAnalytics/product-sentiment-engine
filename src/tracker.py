import requests
import os
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
import google.generativeai as genai
from supabase import create_client

# --- Setup AI and Cloud DB ---
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# We now use two models: one for deep reading, one for fast math
model = genai.GenerativeModel('gemini-2.5-flash')
embedding_model = 'models/text-embedding-004'

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# --- TEMPORAL FILTERS ---
def search_hacker_news(query):
    yesterday_timestamp = int(time.time()) - (24 * 3600)
    url = f"https://hn.algolia.com/api/v1/search_by_date?query={query}&tags=comment&numericFilters=created_at_i>{yesterday_timestamp}"
    try:
        response = requests.get(url)
        comments = []
        for hit in response.json().get('hits', [])[:3]:
            raw_text = hit.get('comment_text', '')
            clean_text = raw_text.replace('\n', ' ') if raw_text else ''
            item_url = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            comments.append(f"{clean_text} [URL: {item_url}]")
        return " ".join(comments) if comments else ""
    except:
        return ""

def search_reddit(query):
    formatted_query = query.replace(' ', '%20')
    url = f"https://www.reddit.com/search.json?q={formatted_query}&sort=new&limit=3&t=day"
    headers = {"User-Agent": "ProductSentimentEngine/5.0"} 
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200: return ""
        posts = response.json().get('data', {}).get('children', [])
        comments = []
        for p in posts:
            title = p['data'].get('title', '')
            raw_body = p['data'].get('selftext', '')[:150]
            clean_body = raw_body.replace('\n', ' ') if raw_body else ''
            post_url = f"https://www.reddit.com{p['data'].get('permalink', '')}"
            comments.append(f"{title} - {clean_body} [URL: {post_url}]")
        return " ".join(comments)
    except:
        return ""

# --- THE MATH ENGINE ---
def get_embedding(text):
    """Converts text into a 768-dimensional mathematical vector."""
    result = genai.embed_content(
        model=embedding_model,
        content=text,
        task_type="semantic_similarity"
    )
    return result['embedding']

def run_tracker():
    print("Starting the V5 Enterprise Vector Engine...\n")
    targets = supabase.table('targets').select('*').eq('status', 'tracking').execute().data
    if not targets: return

    today_str = datetime.utcnow().strftime('%Y-%m-%d')

    for t in targets:
        name = t['name']
        t_id = t['id']
        
        # 1. Daily Idempotency Check
        existing = supabase.table('sentiment').select('*').eq('target_id', t_id).gte('created_at', today_str).execute()
        if len(existing.data) > 0:
            print(f"   -> Already scanned {name} today. Skipping.")
            continue

        print(f"📡 Fetching intelligence for: {name}...")
        hn_data = search_hacker_news(name)
        reddit_data = search_reddit(name)
        
        combined_chatter = ""
        if hn_data: combined_chatter += f"[SOURCE: Hacker News] {hn_data} "
        if reddit_data: combined_chatter += f"[SOURCE: Reddit] {reddit_data}"
        
        if not combined_chatter.strip():
            print(f"   -> No fresh chatter found.")
            continue

        # --- THE VECTOR FILTER ---
        # 2. Convert today's chatter into a math coordinate
        try:
            chatter_vector = get_embedding(combined_chatter)
        except Exception as e:
            print(f"   ⚠️ Embedding API Error for {name}: {e}")
            continue

        # 3. Query Supabase for semantic similarity (Threshold: 82% match)
        match_response = supabase.rpc('match_sentiment', {
            'query_embedding': chatter_vector,
            'match_threshold': 0.82, 
            'p_target_id': t_id
        }).execute()

        # If we get a match back, the data is redundant. Discard it.
        if match_response.data and len(match_response.data) > 0:
            similarity_score = match_response.data[0]['similarity']
            print(f"   🛑 Vector Match (Score: {similarity_score:.2f}): {name} noise is redundant. Discarding.")
            continue

        # --- THE INTELLIGENCE EXTRACTION ---
        # 4. If the data is mathematically new, extract the insights
        prompt = f"""
        You are a Principal Market Intelligence Analyst. 
        Analyze this net-new market chatter for the target: {name}.
        
        Format EXACTLY like this (use | to separate):
        PROS: [summary] | CONS: [summary] | QUOTES: "[Quote]" | URL: [URL]
        
        Data:
        {combined_chatter}
        """
        
        try:
            ai_response = model.generate_content(prompt)
            # Flatten the response to a single line just in case
            line = ai_response.text.strip().replace('\n', ' ') 
            
            if "PROS:" in line and "CONS:" in line and "QUOTES:" in line and "URL:" in line:
                parts = [p.strip() for p in line.split("|", 3)] 
                if len(parts) < 4: continue
                
                pros_part = parts[0].replace("PROS:", "").strip()
                cons_part = parts[1].replace("CONS:", "").strip()
                quotes_part = parts[2].replace("QUOTES:", "").strip()
                url_part = parts[3].replace("URL:", "").strip()
                
                # 5. Save the insights AND the mathematical coordinate
                supabase.table('sentiment').insert({
                    "target_id": t_id,
                    "pros": pros_part,
                    "cons": cons_part,
                    "verbatim_quotes": quotes_part,
                    "source_url": url_part,
                    "embedding": chatter_vector  # <-- Injecting the vector to the DB
                }).execute()
                print(f"   💾 SAVED NET-NEW INTELLIGENCE: {name}")
            else:
                print(f"   ⚠️ AI output format error for {name}.")
        except Exception as e:
            print(f"⚠️ AI API Error: {e}")

if __name__ == "__main__":
    run_tracker()