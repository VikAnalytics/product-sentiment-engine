import sqlite3
import os

# 1. Figure out exactly where we are saving the database
# This ensures it always goes into your 'data' folder
script_directory = os.path.dirname(os.path.abspath(__file__))
database_path = os.path.join(script_directory, '..', 'data', 'sentiment_engine.db')

def setup_database():
    print("Building the database...")

    # 2. Connect to SQLite (this automatically creates the file if it doesn't exist)
    connection = sqlite3.connect(database_path)
    cursor = connection.cursor()

    # 3. Create the 'products' table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            description TEXT,
            launch_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'tracking'
        )
    ''')
    print("- 'products' table is ready.")

    # 4. Create the 'sentiment' table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sentiment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            source_url TEXT,
            pros TEXT,
            cons TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    ''')
    print("- 'sentiment' table is ready.")

    # 5. Save our changes and close the connection
    connection.commit()
    connection.close()
    
    print(f"Success! Database saved securely at: {database_path}")

# This line just tells Python to run the setup_database function when we run the file
if __name__ == "__main__":
    setup_database()