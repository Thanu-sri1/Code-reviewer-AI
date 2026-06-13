from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
import sqlite3
import hashlib
import os

app = FastAPI(title="Auth Service")

DB_FILE = "auth.db"

def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password TEXT)''')
    conn.commit()
    conn.close()

# Initialize DB on startup
init_db()

def hash_password(password: str) -> str:
    salt = "anthropic_secure_salt"
    return hashlib.sha256((password + salt).encode()).hexdigest()

class UserAuth(BaseModel):
    username: str
    password: str

@app.post("/register")
def register_user(user: UserAuth):
    if not user.username or not user.password:
        raise HTTPException(status_code=400, detail="Username and password required")
    
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users VALUES (?, ?)', 
                 (user.username, hash_password(user.password)))
        conn.commit()
        return {"message": "Registration successful"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists")
    finally:
        conn.close()

@app.post("/login")
def login(user: UserAuth):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('SELECT password FROM users WHERE username=?', (user.username,))
    result = c.fetchone()
    conn.close()
    
    if result and result[0] == hash_password(user.password):
        # In a full production system, return a JWT token here
        # For simplicity, returning a success flag
        return {"message": "Login successful", "username": user.username}
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
