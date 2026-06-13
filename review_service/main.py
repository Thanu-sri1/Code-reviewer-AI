from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sqlite3

app = FastAPI(title="Review Management Service")

DB_FILE = "reviews.db"

def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS reviews
                 (id TEXT PRIMARY KEY,
                  username TEXT,
                  code TEXT,
                  review_output TEXT,
                  run_output TEXT,
                  fixed_code TEXT,
                  timestamp TEXT)''')
    conn.commit()
    conn.close()

# Initialize DB on startup
init_db()

class ReviewData(BaseModel):
    id: str
    code: str
    review_output: str
    run_output: str
    fixed_code: str
    timestamp: str

@app.get("/reviews/{username}")
def get_reviews(username: str):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('''SELECT id, code, review_output, run_output, fixed_code, timestamp 
                 FROM reviews WHERE username=? ORDER BY timestamp DESC''', (username,))
    reviews = c.fetchall()
    conn.close()
    
    tabs = {}
    for review in reviews:
        tabs[review[0]] = {
            "code": review[1],
            "review_output": review[2],
            "run_output": review[3],
            "fixed_code": review[4],
            "timestamp": review[5],
            "editor_key": 0
        }
    return tabs

@app.post("/reviews/{username}")
def save_review(username: str, review: ReviewData):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO reviews 
                 VALUES (?, ?, ?, ?, ?, ?, ?)''',
              (review.id, username, review.code, 
               review.review_output, review.run_output,
               review.fixed_code, review.timestamp))
    conn.commit()
    conn.close()
    return {"message": "Review saved"}

@app.delete("/reviews/{tab_id}")
def delete_review(tab_id: str):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('DELETE FROM reviews WHERE id=?', (tab_id,))
    conn.commit()
    conn.close()
    return {"message": "Review deleted"}
