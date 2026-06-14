from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, EmailStr
import sqlite3
import hashlib
import os

app = FastAPI(title="Auth Service")

DB_FILE = "auth.db"

@app.get("/health")
def health_check():
    return {"service": "auth-service", "status": "ok"}

def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, email TEXT UNIQUE, password TEXT)''')
    c.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in c.fetchall()]
    if "email" not in columns:
        c.execute("ALTER TABLE users ADD COLUMN email TEXT")
        c.execute("UPDATE users SET email = username WHERE email IS NULL OR email = ''")
    conn.commit()
    conn.close()

# Initialize DB on startup
init_db()

def hash_password(password: str) -> str:
    salt = "anthropic_secure_salt"
    return hashlib.sha256((password + salt).encode()).hexdigest()

class UserAuth(BaseModel):
    email: EmailStr
    password: str

class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str

@app.post("/register")
def register_user(user: UserRegister):
    if not user.username or not user.email or not user.password:
        raise HTTPException(status_code=400, detail="Username, email, and password required")
    
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                 (user.username, str(user.email), hash_password(user.password)))
        conn.commit()
        return {"message": "Registration successful"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username or email already exists")
    finally:
        conn.close()

@app.post("/login")
def login(user: UserAuth):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('SELECT username, password FROM users WHERE email=?', (str(user.email),))
    result = c.fetchone()
    conn.close()
    
    if result and result[1] == hash_password(user.password):
        # In a full production system, return a JWT token here
        # For simplicity, returning a success flag
        return {"message": "Login successful", "username": result[0], "email": str(user.email)}
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
