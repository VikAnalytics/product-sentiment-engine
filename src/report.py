import os
from datetime import datetime
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
    """Pulls targets and their sentiment from Supabase."""
    targets_response = supabase.table('targets').select('*').eq('status', 'tracking').execute()
    targets = targets_response.data
    
    if not targets:
        return []
        
    full_data = []
    for t in targets:
        sentiment_response = supabase.table('sentiment').select('*').eq('target_id', t['id']).execute()
        sentiments = sentiment_response.data
        
        # Combine all pros and cons for this target
        all_pros = " ".join([s['pros'] for s in sentiments if s.get('pros') and s['pros'] != "None found"])
        all_cons = " ".join([s['cons'] for s in sentiments if s.get('cons') and s['cons'] != "None found"])
        
        if all_pros or all_cons:
            full_data.append({
                "name": t['name'],
                "type": t['target_type'],
                "description": t['description'],
                "pros": all_pros,
                "cons": all_cons
            })
            
    return full_data

def generate_batch_report(data):
    """Asks AI to write ONE master report for all targets."""
    # 1. Assemble the massive payload
    payload_lines = []
    for item in data:
        payload_lines.append(
            f"[{item['type']}] {item['name']}\n"
            f"Context: {item['description']}\n"
            f"PROS: {item['pros']}\n"
            f"CONS: {item['cons']}\n"
            f"---"
        )
    batch_text = "\n".join(payload_lines)
    
    prompt = f"""
    You are an expert tech market analyst. Write a "Daily Executive Market Report" 
    based on the following raw sentiment data.
    
    Structure the report with these exact sections:
    # 📈 Daily Executive Market Report
    ## 🏢 Company Movements
    (Summarize the sentiment and strategic outlook for the companies mentioned)
    
    ## 🚀 Product Intelligence
    (Summarize the reception and outlook for the products mentioned)
    
    ## 💡 Key Takeaways
    (Provide 2-3 strategic bullet points overall)
    
    Raw Data:
    {batch_text}
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"   ⚠️ AI Limit Hit. Generating Mock Executive Report instead.")
        
        # Fallback mock report
        mock = "# 📈 Daily Executive Market Report (MOCK)\n\n*Data pending AI quota reset.*\n\n## Raw Data Summary\n\n"
        for item in data:
            mock += f"**{item['name']}** ({item['type']}):\n* Pros: {item['pros'][:75]}...\n* Cons: {item['cons'][:75]}...\n\n"
        return mock

def save_report(report_content):
    """Saves the markdown report to a file with today's date."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    file_path = os.path.join(REPORTS_DIR, f"executive_report_{date_str}.md")
    
    with open(file_path, "w") as file:
        file.write(report_content)
        
    print(f"   📄 MASTER REPORT GENERATED: {file_path}")

def run_reporter():
    print("Starting the V2 Batch Reporter...\n")
    data = get_cloud_data()
    
    if not data:
        print("No sentiment data found in the cloud yet.")
        return
        
    print(f"Drafting single executive report for {len(data)} targets...")
    report_content = generate_batch_report(data)
    save_report(report_content)
    print("\n✅ Reporter completed successfully.")

if __name__ == "__main__":
    run_reporter()