from flask import Flask
import os
import subprocess

app = Flask(__name__)

# This is the "Doorway". When cron-job.org visits this URL, this function runs.
@app.route('/run-engine')
def run_all():
    try:
        # This tells Python to run your scripts exactly like you did in the terminal
        subprocess.run(["python3", "src/scout.py"], check=True)
        subprocess.run(["python3", "src/tracker.py"], check=True)
        subprocess.run(["python3", "src/report.py"], check=True)
        return "Engine ran successfully!", 200
    except Exception as e:
        return f"Error: {str(e)}", 500

if __name__ == '__main__':
    # Render (the host) will use this port
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)