import os
from datetime import datetime, timedelta
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

script_dir = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(script_dir, '..', 'reports')

def get_cloud_data():
    """Pulls targets and ONLY their sentiment from the last 24 hours."""
    targets_response = supabase.table('targets').select('*').eq('status', 'tracking').execute()
    targets = targets_response.data
    
    if not targets:
        return []
        
    # Calculate the timestamp for 24 hours ago
    yesterday_str = (datetime.utcnow() - timedelta(days=1)).isoformat()
    
    full_data = []
    for t in targets:
        # Only pull sentiment rows created AFTER yesterday
        sentiment_response = supabase.table('sentiment')\
            .select('*')\
            .eq('target_id', t['id'])\
            .gte('created_at', yesterday_str)\
            .execute()
            
        sentiments = sentiment_response.data
        
        # If there is no fresh sentiment for this target today, skip it!
        if not sentiments:
            continue
        
        # Combine the fresh pros and cons
        all_pros = " ".join([s['pros'] for s in sentiments if s.get('pros') and s['pros'] != "None found"])
        all_cons = " ".join([s['cons'] for s in sentiments if s.get('cons') and s['cons'] != "None found"])
        
        # NEW: Combine the quotes and dynamically embed the source URL as a markdown link
        quotes_with_links = []
        for s in sentiments:
            if s.get('verbatim_quotes'):
                quote = s['verbatim_quotes']
                # If there's no URL for some reason, default to a # symbol
                link = s.get('source_url', '#') 
                quotes_with_links.append(f'"{quote}" - [View Source]({link})')
                
        all_quotes = " ".join(quotes_with_links)
        
        if all_pros or all_cons or all_quotes:
            full_data.append({
                "name": t['name'],
                "type": t['target_type'],
                "description": t['description'],
                "pros": all_pros,
                "cons": all_cons,
                "quotes": all_quotes # Inject the new quotes into the payload
            })
            
    return full_data

def generate_batch_report(data):
    """Asks AI to write ONE master intelligence report for all targets."""
    # 1. Assemble the massive payload
    payload_lines = []
    for item in data:
        payload_lines.append(
            f"[{item['type']}] {item['name']}\n"
            f"Context: {item['description']}\n"
            f"PROS: {item['pros']}\n"
            f"CONS: {item['cons']}\n"
            f"VOICE OF CUSTOMER: {item['quotes']}\n"
            f"---"
        )
    batch_text = "\n".join(payload_lines)
    
    prompt = f"""
    You are a Principal Market Intelligence Analyst. Write a highly professional "Market Intelligence Report" 
    based on the following raw sentiment data.
    
    Structure the report precisely with these sections:
    # 🌐 Daily Market Intelligence Report
    
    ## 📊 Executive Summary
    (A brief 2-paragraph macro view of today's market movements based on the data)
    
    ## 🎯 Target Deep Dives
    (For EVERY target provided, create a sub-section formatted exactly like this):
    ### [Target Name]
    * **Strategic Analysis:** (Your expert synthesis of the context, pros, and cons)
    * **Voice of the Customer:** (Present the provided verbatim user quotes as bulleted blockquotes. YOU MUST KEEP THE [View Source](URL) MARKDOWN LINK INTACT AT THE END OF THE QUOTE).
    
    ## 🔭 Forward Outlook
    (2-3 bullet points predicting where this sentiment might lead).
    
    Raw Intelligence:
    {batch_text}
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"   ⚠️ AI Limit Hit. Generating Mock Intelligence Report instead.")
        
        # Fallback mock report updated for V3
        mock = "# 🌐 Daily Market Intelligence Report (MOCK)\n\n*Data pending AI quota reset.*\n\n## Raw Intelligence Summary\n\n"
        for item in data:
            mock += f"### {item['name']} ({item['type']})\n* **Pros:** {item['pros'][:75]}...\n* **Cons:** {item['cons'][:75]}...\n* **Quotes:** {item['quotes']}\n\n"
        return mock

def save_report(report_content):
    """Saves the markdown report to a file with today's date."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    # Updated file name to reflect the new Intelligence format
    file_path = os.path.join(REPORTS_DIR, f"market_intelligence_{date_str}.md")
    
    with open(file_path, "w") as file:
        file.write(report_content)
        
    print(f"   📄 MASTER REPORT GENERATED: {file_path}")

def run_reporter():
    print("Starting the V3 Intelligence Reporter...\n")
    data = get_cloud_data()
    
    if not data:
        print("No fresh intelligence data found for today.")
        return
        
    print(f"Drafting comprehensive intelligence report for {len(data)} targets...")
    report_content = generate_batch_report(data)
    save_report(report_content)
    print("\n✅ Reporter completed successfully.")

if __name__ == "__main__":
    run_reporter()