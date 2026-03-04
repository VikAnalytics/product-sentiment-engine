import feedparser
import os
import sqlite3
import google.generativeai as genai
from dotenv import load_dotenv

# --- Setup AI ---
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

# --- Setup Database Path ---
script_dir = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(script_dir, '..', 'data', 'sentiment_engine.db')

RSS_URL = "https://techcrunch.com/feed/"

def save_to_database(product_name, description):
    """Saves the discovered product into our SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # We use ? to safely insert data and prevent database errors
    cursor.execute('''
        INSERT INTO products (product_name, description, status)
        VALUES (?, ?, 'tracking')
    ''', (product_name, description))
    
    conn.commit()
    conn.close()
    print(f"💾 SAVED TO DATABASE: {product_name}")

def analyze_article_with_ai(title, summary):
    prompt = f"""
    Read the following tech news article title and summary. 
    Is this article announcing a brand-new tech product or major feature launch? 
    If YES: Reply exactly in this format -> Product: [Name] | Description: [1-sentence summary]
    If NO: Reply exactly with -> NONE
    
    Title: {title}
    Summary: {summary}
    """
    response = model.generate_content(prompt)
    return response.text.strip()

def run_scout():
    print(f"Scouting for news at: {RSS_URL}...\n")
    
    # Let's test our fake article directly to make sure the database save works!
    fake_title = "Apple Announces the New iPhone 20 Pro with Holographic Display"
    fake_summary = "Today at Apple Park, the company unveiled its latest flagship smartphone featuring a revolutionary holographic projector and a 5-day battery life."
    
    print(f"Checking: {fake_title}")
    ai_result = analyze_article_with_ai(fake_title, fake_summary)
    print(f"AI Says: {ai_result}")
    
    # If the AI did NOT say "NONE", it means it found a product!
    if ai_result != "NONE":
        try:
            # We split the AI's answer at the "|" symbol to separate the name and description
            parts = ai_result.split("|")
            
            # Clean up the text to remove "Product: " and "Description: "
            name = parts[0].replace("Product:", "").strip()
            desc = parts[1].replace("Description:", "").strip()
            
            # Send the clean text to our database function
            save_to_database(name, desc)
        except Exception as e:
            print(f"Oops, couldn't parse the AI response: {e}")

if __name__ == "__main__":
    run_scout()