import sqlite3
import os
import google.generativeai as genai
from dotenv import load_dotenv

# --- Setup AI ---
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

# --- Setup Paths ---
script_dir = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(script_dir, '..', 'data', 'sentiment_engine.db')
REPORTS_DIR = os.path.join(script_dir, '..', 'reports')

def get_product_sentiment():
    """Gets the product and all its pros/cons from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # We ask the database to match our products with their sentiment feedback
    cursor.execute('''
        SELECT p.product_name, s.pros, s.cons 
        FROM products p
        JOIN sentiment s ON p.id = s.product_id
        WHERE p.status = 'tracking'
    ''')
    
    results = cursor.fetchall()
    conn.close()
    return results

def generate_markdown_report(product_name, aggregated_feedback):
    """Asks Gemini to write a professional markdown report."""
    print(f"Asking AI to write the report for: {product_name}...")
    
    # This is the strict format we are requesting from the AI
    prompt = f"""
    You are an expert tech market analyst. Based on the following user data points, 
    write a 300-word product analysis article formatted in Markdown. 
    
    Structure the report with these exact headers:
    # Product Analysis: {product_name}
    ## Executive Summary
    ## Top Pros
    ## Top Cons
    ## User Recommendations
    
    Here is the raw sentiment data gathered from the internet:
    {aggregated_feedback}
    """
    
    response = model.generate_content(prompt)
    return response.text

def save_report(product_name, report_content):
    """Saves the markdown report to a file."""
    # 1. Create the 'reports' folder if it doesn't exist yet
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    # 2. Create a safe file name (e.g., "iphone_20_pro_report.md")
    safe_name = product_name.replace(" ", "_").lower()
    file_path = os.path.join(REPORTS_DIR, f"{safe_name}_report.md")
    
    # 3. Save the AI's text into the new file
    with open(file_path, "w") as file:
        file.write(report_content)
        
    print(f"📄 REPORT GENERATED! You can find it at: {file_path}")

def run_reporter():
    print("Starting The Reporter...\n")
    sentiment_data = get_product_sentiment()
    
    if not sentiment_data:
        print("No sentiment data found in the database yet.")
        return
        
    # We will grab the very first product we find in the database
    product_name = sentiment_data[0][0]
    
    # Combine all the pros and cons into one big block of text to show the AI
    aggregated_feedback = ""
    for row in sentiment_data:
        aggregated_feedback += f"- PROS: {row[1]}\n- CONS: {row[2]}\n\n"
        
    # Generate and save the report!
    report_content = generate_markdown_report(product_name, aggregated_feedback)
    save_report(product_name, report_content)

if __name__ == "__main__":
    run_reporter()