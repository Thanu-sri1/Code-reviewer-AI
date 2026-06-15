import streamlit as st
import requests
import subprocess
from streamlit_ace import st_ace
import uuid
from datetime import datetime
import sqlite3
import hashlib
import os
import base64
import json
import urllib.error
import urllib.request
from PIL import Image
# import pytesseract
import io


import ast  # To check if extracted code is valid Python

def is_valid_python_code(text):
    """Check if the extracted text is valid Python code."""
    try:
        ast.parse(text)  # Try parsing the text as Python code
        return True
    except SyntaxError:
        return False


AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip().rstrip("/")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip()
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview").strip()

if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY or not AZURE_OPENAI_DEPLOYMENT:
    st.error("Azure OpenAI settings are missing. Please set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, and AZURE_OPENAI_DEPLOYMENT.")
    st.stop()


def azure_chat_completion(messages, max_tokens=1800, temperature=0.2):
    url = (
        f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT}"
        f"/chat/completions?api-version={AZURE_OPENAI_API_VERSION}"
    )
    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "api-key": AZURE_OPENAI_API_KEY,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"] or ""
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            message = json.loads(detail).get("error", {}).get("message", detail)
        except json.JSONDecodeError:
            message = detail
        raise RuntimeError(message)
    except Exception as exc:
        raise RuntimeError(str(exc))


def extract_valid_python_block(text):
    marker = "```python"
    if marker not in text:
        return ""
    try:
        block = text.split(marker, 1)[1].split("```", 1)[0].strip()
    except IndexError:
        return ""
    return block if is_valid_python_code(block) else ""

# Database setup
def init_db():
    conn = sqlite3.connect('code_review.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS reviews
                 (id TEXT PRIMARY KEY,
                  username TEXT,
                  code TEXT,
                  review_output TEXT,
                  run_output TEXT,
                  fixed_code TEXT,
                  timestamp TEXT,
                  FOREIGN KEY (username) REFERENCES users(username))''')
    conn.commit()
    conn.close()

# User authentication functions
def hash_password(password):
    salt = "anthropic_secure_salt"
    return hashlib.sha256((password + salt).encode()).hexdigest()

def authenticate(username, password):
    conn = sqlite3.connect('code_review.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('SELECT password FROM users WHERE username=?', (username,))
    result = c.fetchone()
    conn.close()
    return result and result[0] == hash_password(password)

def register_user(username, password):
    if not username or not password:
        return False
    conn = sqlite3.connect('code_review.db', check_same_thread=False)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users VALUES (?, ?)', 
                 (username, hash_password(password)))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

# Database operations for reviews
def load_user_reviews(username):
    conn = sqlite3.connect('code_review.db', check_same_thread=False)
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

def save_review(username, tab_id, tab_data):
    if not username:  # Don't save if user is not logged in
        return
    conn = sqlite3.connect('code_review.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO reviews 
                 VALUES (?, ?, ?, ?, ?, ?, ?)''',
              (tab_id, username, tab_data["code"], 
               tab_data["review_output"], tab_data["run_output"],
               tab_data["fixed_code"], tab_data["timestamp"]))
    conn.commit()
    conn.close()

# Function to extract code using Azure AI
def extract_code_from_image_with_genai(uploaded_image):
    try:
        image_bytes = uploaded_image.getvalue()
        content_type = uploaded_image.type or "image/png"
        encoded_image = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{content_type};base64,{encoded_image}"
        return azure_chat_completion(
            [
                {"role": "system", "content": system_prompt2},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": system_prompt2},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            max_tokens=1200,
            temperature=0,
        ).strip()

    except Exception as e:
        st.error(f"Error extracting code from image using AI: {str(e)}")
        return ""



def run_code(code, tab_id):
    """Execute Python code and capture output."""
    try:
        # Create a temporary file to execute the code
        temp_file = f"temp_{tab_id}.py"
        with open(temp_file, "w") as f:
            f.write(code)
        
        # Run the code and capture output
        result = subprocess.run(
            ["python3", temp_file],
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout
        )
        
        # Clean up temp file
        os.remove(temp_file)
        
        # Return both stdout and stderr
        output = result.stdout
        if result.stderr:
            output += "\nErrors:\n" + result.stderr
        
        return output
    except subprocess.TimeoutExpired:
        return "Error: Code execution timed out (30 second limit)"
    except Exception as e:
        return f"Error: {str(e)}"
    finally:
        # Ensure temp file is removed even if there's an error
        if os.path.exists(temp_file):
            os.remove(temp_file)

# Initialize session state
def init_session_state():
    if "tabs" not in st.session_state:
        new_tab_id = str(uuid.uuid4())
        st.session_state["tabs"] = {
            new_tab_id: {
                "code": "",
                "review_output": "",
                "run_output": "",
                "fixed_code": "",
                "editor_key": 0,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        }
        st.session_state["current_tab"] = new_tab_id
    
    if 'username' not in st.session_state:
        st.session_state['username'] = None

# Core application functions
def review_code(code, tab_id):
    """Send code to Azure AI for review and store response."""
    try:
        prompt = f"""Review this code in simple words and provide a minimal fix.

Include these sections:
- Problems Found
- Simple Suggestions
- Corrected Code

Code:
{code}
"""
        review_output = azure_chat_completion(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]
        )
        st.session_state["tabs"][tab_id]["review_output"] = review_output

        fixed_code = extract_valid_python_block(review_output)
        if fixed_code:
            st.session_state["tabs"][tab_id]["fixed_code"] = fixed_code
        
        if st.session_state.get('username'):
            save_review(st.session_state['username'], tab_id, st.session_state["tabs"][tab_id])
    except Exception as e:
        st.error(f"Error during code review: {str(e)}")

def create_new_tab():
    new_tab_id = str(uuid.uuid4())
    st.session_state["current_tab"] = new_tab_id
    st.session_state["tabs"][new_tab_id] = {
        "code": "",
        "review_output": "",
        "run_output": "",
        "fixed_code": "",
        "editor_key": 0,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    if st.session_state.get('username'):
        save_review(st.session_state['username'], new_tab_id, st.session_state["tabs"][new_tab_id])

def delete_tab(tab_id):
    if tab_id in st.session_state["tabs"]:
        if tab_id == st.session_state["current_tab"]:
            remaining_tabs = [t for t in st.session_state["tabs"].keys() if t != tab_id]
            if remaining_tabs:
                st.session_state["current_tab"] = remaining_tabs[0]
            else:
                create_new_tab()
        
        if st.session_state.get('username'):
            conn = sqlite3.connect('code_review.db', check_same_thread=False)
            c = conn.cursor()
            c.execute('DELETE FROM reviews WHERE id=?', (tab_id,))
            conn.commit()
            conn.close()
        
        del st.session_state["tabs"][tab_id]

def apply_fixed_code(tab_id):
    if st.session_state["tabs"][tab_id]["fixed_code"]:
        st.session_state["tabs"][tab_id]["code"] = st.session_state["tabs"][tab_id]["fixed_code"]
        st.session_state["tabs"][tab_id]["editor_key"] += 1
        if st.session_state.get('username'):
            save_review(st.session_state['username'], tab_id, st.session_state["tabs"][tab_id])

def get_sorted_tabs():
    return dict(sorted(
        st.session_state["tabs"].items(),
        key=lambda x: x[1]['timestamp'],
        reverse=True
    ))

# Initialize application
init_db()
init_session_state()

# Azure AI review prompt
system_prompt = """You are a helpful Python code reviewer. Explain problems in simple words.
Find bugs, risky code, slow code, unused variables, and confusing functions.
Give short suggestions for memory use, speed, readability, and structure.
Return one compact corrected Python version only when a clear fix is needed.
Do not rewrite the code into a large framework, class hierarchy, menu, or template.
Always wrap only the corrected Python code in triple backticks with the python language identifier.
"""


system_prompt2 = """Extract only the programming code from this image.
Do not include explanations, comments, markdown, JSON, headers, or extra text.
Preserve indentation, special characters, and syntax exactly as seen in the image.
If the image does not contain code, return: No code detected in the image.
"""


def show_about():
    st.title("About CodeRaptor")
    st.markdown(
        """
        **CodeRaptor** is an advanced AI-powered platform designed for effortless code extraction, 
        execution, and review. Whether you're a developer debugging scripts, an educator analyzing 
        student code, or a researcher working with complex algorithms, CodeRaptor streamlines the process 
        with cutting-edge AI models.

        ### Key Features:
        - **AI-Powered Code Extraction**: Extracts code from images with high accuracy.
        - **Instant Code Execution**: Run extracted or uploaded code directly within the app.
        - **Automated Code Review**: Get AI-generated feedback on code quality, efficiency, and security.
        - **User-Friendly Interface**: Simplified workflow with secure authentication.

        Built with **Streamlit**, **Python**, and **AI-driven analysis**, CodeRaptor is here to transform 
        how you interact with code.

        ---
        **Contact & Support:**  
        📧 Email: yeswanthyerra07@gmail.com  
        🌐 Website: [coderaptor.app/](https://coderaptor.streamlit.app/)
        """
    )

# Sidebar
with st.sidebar:
        # Ensure 'show_about' is in session state
    if "show_about" not in st.session_state:
        st.session_state.show_about = False

    # Toggle function
    def toggle_about():
        st.session_state.show_about = not st.session_state.show_about

    # Main UI
    st.title("**Code Raptor**")
    
    st.button("About", on_click=toggle_about)  # Toggles the About section
    
    # Conditionally display the About section
    if st.session_state.show_about:
        show_about()
        st.button("Close", on_click=toggle_about)  # Button to hide the About section
    else:
        st.write("Welcome to the main page!")
    
    st.divider()
    st.title("Code Review History")
    
    # Login/Register/Logout section
    if not st.session_state.get('username'):
        with st.expander("Login/Register"):
            tab1, tab2 = st.tabs(["Login", "Register"])
            
            with tab1:
                username = st.text_input("Username", key="login_username")
                password = st.text_input("Password", type="password", key="login_password")
                if st.button("Login"):
                    if authenticate(username, password):
                        st.session_state['username'] = username
                        st.session_state["tabs"] = load_user_reviews(username)
                        if not st.session_state["tabs"]:
                            create_new_tab()
                        st.rerun()
                    else:
                        st.error("Invalid username or password")

            with tab2:
                new_username = st.text_input("Username", key="reg_username")
                new_password = st.text_input("Password", type="password", key="reg_password")
                if st.button("Register"):
                    if register_user(new_username, new_password):
                        st.success("Registration successful! Please login.")
                    else:
                        st.error("Username already exists or invalid input")
    else:
        st.write(f"Logged in as: {st.session_state['username']}")
        if st.button("Logout"):
            st.session_state['username'] = None
            st.session_state["tabs"] = {}  # Clear tabs on logout
            st.rerun()
    
    if st.button("New Review", type="primary"):
        create_new_tab()
        st.rerun()
    
    st.divider()
    
    # Display history
    sorted_tabs = get_sorted_tabs()
    for tab_id, tab_data in sorted_tabs.items():
        col1, col2 = st.columns([4, 1])
        with col1:
            if st.button(
                f"Review from {tab_data['timestamp']}",
                key=f"history_{tab_id}",
                use_container_width=True
            ):
                st.session_state["current_tab"] = tab_id
                st.rerun()
        with col2:
            if st.button("🗑️", key=f"delete_{tab_id}"):
                delete_tab(tab_id)
                st.rerun()
    

# Main content area
if "tabs" in st.session_state and st.session_state["tabs"]:
    current_tab = st.session_state.get("current_tab", None)
    
    if current_tab in st.session_state["tabs"]:
        current_tab_data = st.session_state["tabs"][current_tab]
    else:
        st.error("The selected tab no longer exists. Creating a new tab.")
        create_new_tab()  # Create a new tab if the current one is invalid
        current_tab = st.session_state["current_tab"]
        current_tab_data = st.session_state["tabs"][current_tab]
else:
    st.error("No tabs available. Creating a new tab.")
    create_new_tab()
    current_tab = st.session_state["current_tab"]
    current_tab_data = st.session_state["tabs"][current_tab]

st.title("Code Raptor")

# Code Editor
code = st_ace(
    language="python",
    theme="monokai",
    height=300,
    value=current_tab_data["code"],
    key=f"editor_{current_tab}_{current_tab_data['editor_key']}"
)

    # File upload section
st.divider()
# Unified file uploader for both Python files and images

uploaded_file = st.file_uploader("Upload a file (Python or Image)", type=["py", "png", "jpg", "jpeg"])
st.caption("Note : 1. for images wait for 1 min while extracting code from images \n\n2.To make changes in editor clear uploaded file")


if uploaded_file is not None:

    # Get the file type

    file_type = uploaded_file.type


    if file_type == "text/x-python":  # Python file
        
        code = uploaded_file.read().decode("utf-8")
        
        # Update the code in the current tab
        code_hash = hashlib.md5(code.encode()).hexdigest()

        if code_hash != st.session_state.get("last_processed_code_hash"):
            if code:
                st.session_state["tabs"][st.session_state["current_tab"]]["code"] = code
                st.session_state["tabs"][st.session_state["current_tab"]]["editor_key"] += 1

                # Save review if the user is logged in
                if st.session_state.get('username'):
                    save_review(st.session_state['username'], st.session_state["current_tab"], st.session_state["tabs"][st.session_state["current_tab"]])
                
                st.session_state["last_processed_code_hash"] = code_hash
                st.success("Python file uploaded and code updated in the editor!")
                st.rerun()  # Refresh UI
            else:    
                st.warning("No code detected in the uploaded image.")

    elif file_type in ["image/png", "image/jpeg"]:  # Image file
        # Compute hash of the uploaded image
        image_bytes = uploaded_file.getvalue()
        image_hash = hashlib.md5(image_bytes).hexdigest()
        # Check if this image was already processed
        if image_hash != st.session_state.get("last_processed_image_hash"):
            extracted_code = extract_code_from_image_with_genai(uploaded_file)
            if extracted_code:
                if is_valid_python_code(extracted_code):
            # Update only if it's actual code
                    st.session_state["tabs"][st.session_state["current_tab"]]["code"] = extracted_code
                    st.session_state["tabs"][st.session_state["current_tab"]]["editor_key"] += 1
                    st.success("Code extracted and updated in the editor!")
                else:
                    # Store in review output instead
                    st.session_state["tabs"][st.session_state["current_tab"]]["review_output"] = extracted_code
                    st.warning("Extracted text does not seem like code. Stored in review section.")
                    # Save review if user is logged in
                if st.session_state.get('username'):
                    
                    save_review(

                        st.session_state['username'],

                        st.session_state["current_tab"],

                        st.session_state["tabs"][st.session_state["current_tab"]]

                    )
                # Update session to avoid re-processing the same image
                st.session_state["last_processed_image_hash"] = image_hash
                st.success("Code extracted using AI and updated in the editor!")               
                st.rerun()  # Refresh UI            
            else:
                st.warning("No code detected in the uploaded image.")
        else:
            st.info("This image has already been processed.")


# Update code in session state and database
st.session_state["tabs"][current_tab]["code"] = code
if st.session_state.get('username'):
    save_review(st.session_state['username'], current_tab, st.session_state["tabs"][current_tab])

# Chat-like interface
chat_container = st.container()

with chat_container:
    # Run Code Section
    if st.button("Run Code", key=f"run_{current_tab}"):
        if code.strip():
            result = run_code(code, current_tab)
            st.session_state["tabs"][current_tab]["run_output"] = result
            if st.session_state.get('username'):
                save_review(st.session_state['username'], current_tab, st.session_state["tabs"][current_tab])
        else:
            st.warning("Please enter some code.")

    if current_tab_data["run_output"]:
        st.markdown("#### Output:")
        st.code(current_tab_data["run_output"])

    # Code Review Section
    if st.button("Review Code", key=f"review_{current_tab}"):
        if code.strip():
            review_code(code, current_tab)
        else:
            st.warning("Please enter some code.")

    if current_tab_data["review_output"]:
        st.markdown("#### Review Feedback:")
        st.markdown(current_tab_data["review_output"])
        
        if current_tab_data["fixed_code"]:
            if st.button("Apply Fixed Code", key=f"apply_{current_tab}"):
                apply_fixed_code(current_tab)
                st.rerun()

