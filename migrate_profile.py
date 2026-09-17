import sqlite3

def migrate():
    conn = sqlite3.connect('careerpilot.db')
    cursor = conn.cursor()
    columns = [
        ("portfolio_url", "TEXT DEFAULT 'https://janardhan-d.github.io'"),
        ("linkedin_url", "TEXT DEFAULT 'https://linkedin.com/in/janardhan-devarala'"),
        ("github_url", "TEXT DEFAULT 'https://github.com/janardhan-d'"),
        ("gdrive_resume_url", "TEXT DEFAULT 'https://drive.google.com/file/d/janardhan-devarala-master-resume'"),
    ]
    for col_name, col_type in columns:
        try:
            cursor.execute(f"ALTER TABLE user_profiles ADD COLUMN {col_name} {col_type};")
            print(f"Added column {col_name}")
        except sqlite3.OperationalError as e:
            print(f"Column {col_name} already exists or error: {e}")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
