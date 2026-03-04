import sqlite3
import os
import requests
import google.generativeai as genai
from dotenv import load_dotenv

# --- Setup AI ---
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

# --- Setup Database Path ---
script_dir = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(script_dir, '..', 'data', 'sentiment_engine.db')

def get_products_to_track():
    """Gets all products from the database that have the status 'tracking'."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, product_name FROM products WHERE status = 'tracking'")
    active_products = cursor.fetchall() 
    conn.close()
    return active_products

def save_sentiment(product_id, pros, cons):
    """Saves the AI's pros and cons into our sentiment table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sentiment (product_id, pros, cons)
        VALUES (?, ?, ?)
    ''', (product_id, pros, cons))
    conn.commit()
    conn.close()
    print(f"💾 SAVED SENTIMENT TO DATABASE!")

def analyze_comments_with_ai(product_name, comments_text):
    """Sends the internet comments to Gemini to find Pros and Cons."""
    prompt = f"""
    Analyze these comments. Extract a list of pros and cons regarding this product: '{product_name}'.
    If there isn't much info, do your best to summarize what is there.
    
    Reply EXACTLY in this single-line format:
    PROS: [list pros here] | CONS: [list cons here]
    
    Comments:
    {comments_text}
    """
    response = model.generate_content(prompt)
    return response.text.strip()

def run_tracker():
    print("Starting The Tracker...\n")
    products = get_products_to_track()
    
    if not products:
        print("No active products to track right now.")
        return
        
    for product_id, product_name in products:
        print(f"Searching Hacker News for: {product_name}...")
        url = f"http://hn.algolia.com/api/v1/search?query={product_name}"
        response = requests.get(url)
        hits = response.json().get('hits', [])
        
        # 1. Gather all the text from the top 5 forum posts/comments
        combined_comments = ""
        for hit in hits[:5]:
            # The text could be hiding in different spots depending on if it's a post or a comment
            text = hit.get('story_text') or hit.get('comment_text') or hit.get('title') or ""
            combined_comments += text + " \n"
            
        print("Analyzing comments with AI...")
        
        # 2. Give the gathered text to the AI
        ai_result = analyze_comments_with_ai(product_name, combined_comments)
        print(f"\nAI Analysis:\n{ai_result}\n")
        
        # 3. Split the AI's answer into Pros and Cons and save it
        try:
            parts = ai_result.split("|")
            pros = parts[0].replace("PROS:", "").strip()
            cons = parts[1].replace("CONS:", "").strip()
            save_sentiment(product_id, pros, cons)
        except Exception as e:
            print("Oops, couldn't split the AI response correctly.")
            
        print("-" * 50)

if __name__ == "__main__":
    run_tracker()