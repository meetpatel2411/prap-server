import sqlite3
def get_db():
    conn = sqlite3.connect('app.db', timeout=5.0)
    return conn
def init_db():
    with get_db() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT);')
        conn.commit()
