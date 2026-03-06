import feedparser
import os
import spacy
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

# --- Setup Local NLP ---
# Load the small English model
nlp = spacy.load("en_core_web_sm")

# The NLP "Lemmas" (Root Concepts)
CORE_LEMMAS = {
    "launch", "announce", "release", "unveil", "beta", "debut",
    "acquire", "merge", "buy", "sell", "earn", "revenue", "profit",
    "layoff", "fire", "resign", "hire", "depart",
    "sue", "settle", "fine", "probe", "ban", "block",
    "partner", "collaborate", "expand", "halt", "delay"
}

# 1. The Multi-Source List
RSS_FEEDS = [
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://www.wired.com/feed/rss",
    "https://www.engadget.com/rss.xml",
    "https://www.zdnet.com/news/rss.xml"
]

def passes_filter(text):
    """Uses NLP to break the article into root words and check our concepts."""
    # Process the text through the spaCy brain
    doc = nlp(text.lower())
    
    # Check every word's "lemma" (its base dictionary form)
    for token in doc:
        if token.lemma_ in CORE_LEMMAS:
            return True # It hit a root concept! Pass it to the batch.
            
    return False # No root concepts found. Trash it.

def save_target_to_db(target_type, name, description):
    """Saves the extracted company or product to Supabase."""
    target_type = target_type.strip().upper()
    name = name.strip()
    
    if target_type not in ["COMPANY", "PRODUCT"]:
        return

    try:
        existing = supabase.table('targets').select('*').eq('name', name).execute()
        if len(existing.data) > 0:
            print(f"   -> [{target_type}] {name} is already in the database. Skipping.")
            return

        data = {
            "name": name,
            "target_type": target_type,
            "description": description,
            "status": "tracking"
        }
        supabase.table('targets').insert(data).execute()
        print(f"   💾 SAVED: [{target_type}] {name}")
    except Exception as e:
        print(f"   ❌ Database Error for {name}: {e}")

def run_scout():
    print("Gathering articles from 5 sources...\n")
    articles_to_analyze = []
    
    # --- PHASE 1: GATHER & FILTER (0 API Calls) ---
    for feed_url in RSS_FEEDS:
        try:
            print(f"📡 Scanning: {feed_url}")
            feed = feedparser.parse(feed_url)
            # Grab top 10 from each site (50 articles total)
            for entry in feed.entries[:10]: 
                title = entry.title
                summary = entry.get('summary', '')
                
                if passes_filter(title + " " + summary):
                    articles_to_analyze.append(f"Title: {title}\nSummary: {summary}\n")
        except Exception as e:
            print(f"Could not read {feed_url}: {e}")
            
    if not articles_to_analyze:
        print("\nNo market-moving articles found today.")
        return
        
    print(f"\nFiltered 50 raw articles down to {len(articles_to_analyze)} highly relevant ones.")
    print("Sending ONE batch request to the AI...\n")
    
    # --- PHASE 2: BATCH AI ANALYSIS (1 API Call) ---
    # Glue all the articles together into one big string
    batch_text = "\n---\n".join(articles_to_analyze) 
    
    prompt = f"""
    You are an expert tech market analyst. Read the following batch of news articles.
    Extract EVERY major COMPANY event and EVERY new PRODUCT launch mentioned across all articles.
    
    Rules:
    1. A single article might mention multiple companies and products. Extract all of them.
    2. Format your response exactly like this, with one entity per line:
    COMPANY | [Company Name] | [1-sentence summary of event]
    PRODUCT | [Product Name] | [1-sentence summary of launch]
    
    Do not include any other conversational text, headers, or markdown. 
    If absolutely nothing is found, output NONE.
    
    Articles:
    {batch_text}
    """
    
    try:
        response = model.generate_content(prompt)
        result_lines = response.text.strip().split('\n')
        
        for line in result_lines:
            if "|" in line:
                parts = line.split("|")
                if len(parts) >= 3:
                    save_target_to_db(parts[0], parts[1], parts[2])
                    
        print("\n✅ Scout completed successfully.")
                    
    except Exception as e:
        print(f"\n⚠️ AI API Error (You might still be out of quota!): {e}")

if __name__ == "__main__":
    run_scout()