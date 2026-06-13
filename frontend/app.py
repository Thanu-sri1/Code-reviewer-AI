import streamlit as st
import requests
from streamlit_ace import st_ace
import uuid
from datetime import datetime
import hashlib
from PIL import Image
import io
import ast

# Microservices URLs
AUTH_SERVICE_URL = "http://auth-service:8001"
EXECUTION_SERVICE_URL = "http://execution-service:8002"
AI_SERVICE_URL = "http://ai-service:8003"
REVIEW_SERVICE_URL = "http://review-service:8004"

# If running locally without docker-compose, you might need localhost URLs instead:
# AUTH_SERVICE_URL = "http://localhost:8001"
# EXECUTION_SERVICE_URL = "http://localhost:8002"
# AI_SERVICE_URL = "http://localhost:8003"
# REVIEW_SERVICE_URL = "http://localhost:8004"

def is_valid_python_code(text):
    try:
        ast.parse(text)
        return True
    except SyntaxError:
        return False

# User authentication functions
def authenticate(username, password):
    try:
        response = requests.post(f"{AUTH_SERVICE_URL}/login", json={"username": username, "password": password})
        if response.status_code == 200:
            return True
        return False
    except requests.ConnectionError:
        st.error("Auth Service is unreachable.")
        return False

def register_user(username, password):
    if not username or not password:
        return False
    try:
        response = requests.post(f"{AUTH_SERVICE_URL}/register", json={"username": username, "password": password})
        if response.status_code == 200:
            return True
        return False
    except requests.ConnectionError:
        st.error("Auth Service is unreachable.")
        return False

# Database operations for reviews (via Review Service)
def load_user_reviews(username):
    try:
        response = requests.get(f"{REVIEW_SERVICE_URL}/reviews/{username}")
        if response.status_code == 200:
            return response.json()
        return {}
    except requests.ConnectionError:
        st.error("Review Service is unreachable.")
        return {}

def save_review(username, tab_id, tab_data):
    if not username:
        return
    try:
        payload = {
            "id": tab_id,
            "code": tab_data["code"],
            "review_output": tab_data["review_output"],
            "run_output": tab_data["run_output"],
            "fixed_code": tab_data["fixed_code"],
            "timestamp": tab_data["timestamp"]
        }
        requests.post(f"{REVIEW_SERVICE_URL}/reviews/{username}", json=payload)
    except requests.ConnectionError:
        pass

def delete_tab(tab_id):
    if tab_id in st.session_state["tabs"]:
        if tab_id == st.session_state["current_tab"]:
            remaining_tabs = [t for t in st.session_state["tabs"].keys() if t != tab_id]
            if remaining_tabs:
                st.session_state["current_tab"] = remaining_tabs[0]
            else:
                create_new_tab()
        
        if st.session_state.get('username'):
            try:
                requests.delete(f"{REVIEW_SERVICE_URL}/reviews/{tab_id}")
            except requests.ConnectionError:
                pass
        
        del st.session_state["tabs"][tab_id]

# Function to extract code using AI Service
def extract_code_from_image_with_genai(uploaded_image):
    try:
        files = {"file": (uploaded_image.name, uploaded_image.getvalue(), uploaded_image.type)}
        response = requests.post(f"{AI_SERVICE_URL}/extract", files=files)
        if response.status_code == 200:
            return response.json().get("extracted_code", "")
        else:
            st.error(f"Error from AI Service: {response.text}")
            return ""
    except Exception as e:
        st.error(f"Error extracting code from image: {str(e)}")
        return ""

def run_code(code, tab_id):
    """Execute Python code using Execution Service."""
    try:
        response = requests.post(f"{EXECUTION_SERVICE_URL}/run", json={"code": code, "tab_id": tab_id})
        if response.status_code == 200:
            return response.json().get("output", "")
        else:
            return f"Error from Execution Service: {response.text}"
    except Exception as e:
        return f"Error: {str(e)}"

def review_code(code, tab_id):
    """Send code to AI Service for review."""
    try:
        response = requests.post(f"{AI_SERVICE_URL}/review", json={"code": code})
        if response.status_code == 200:
            data = response.json()
            st.session_state["tabs"][tab_id]["review_output"] = data.get("review_output", "")
            if data.get("fixed_code"):
                st.session_state["tabs"][tab_id]["fixed_code"] = data.get("fixed_code")
            
            if st.session_state.get('username'):
                save_review(st.session_state['username'], tab_id, st.session_state["tabs"][tab_id])
        else:
            st.error(f"Error from AI Service: {response.text}")
    except Exception as e:
        st.error(f"Error during code review: {str(e)}")

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

init_session_state()

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
        """
    )

# Sidebar
with st.sidebar:
    if "show_about" not in st.session_state:
        st.session_state.show_about = False

    def toggle_about():
        st.session_state.show_about = not st.session_state.show_about

    st.title("**Code Raptor**")
    st.button("About", on_click=toggle_about)
    
    if st.session_state.show_about:
        show_about()
        st.button("Close", on_click=toggle_about)
    else:
        st.write("Welcome to the main page!")
    
    st.divider()
    st.title("Code Review History")
    
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
            st.session_state["tabs"] = {}
            st.rerun()
    
    if st.button("New Review", type="primary"):
        create_new_tab()
        st.rerun()
    
    st.divider()
    
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
        create_new_tab()
        current_tab = st.session_state["current_tab"]
        current_tab_data = st.session_state["tabs"][current_tab]
else:
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

st.divider()
uploaded_file = st.file_uploader("Upload a file (Python or Image)", type=["py", "png", "jpg", "jpeg"])
st.caption("Note: 1. for images wait while extracting code from images \n2. To make changes in editor clear uploaded file")

if uploaded_file is not None:
    file_type = uploaded_file.type

    if file_type == "text/x-python":
        new_code = uploaded_file.read().decode("utf-8")
        code_hash = hashlib.md5(new_code.encode()).hexdigest()

        if code_hash != st.session_state.get("last_processed_code_hash"):
            if new_code:
                st.session_state["tabs"][st.session_state["current_tab"]]["code"] = new_code
                st.session_state["tabs"][st.session_state["current_tab"]]["editor_key"] += 1
                if st.session_state.get('username'):
                    save_review(st.session_state['username'], st.session_state["current_tab"], st.session_state["tabs"][st.session_state["current_tab"]])
                
                st.session_state["last_processed_code_hash"] = code_hash
                st.success("Python file uploaded and code updated in the editor!")
                st.rerun()
            else:    
                st.warning("No code detected in the uploaded file.")

    elif file_type in ["image/png", "image/jpeg"]:
        image_bytes = uploaded_file.getvalue()
        image_hash = hashlib.md5(image_bytes).hexdigest()
        
        if image_hash != st.session_state.get("last_processed_image_hash"):
            extracted_code = extract_code_from_image_with_genai(uploaded_file)
            if extracted_code:
                if is_valid_python_code(extracted_code):
                    st.session_state["tabs"][st.session_state["current_tab"]]["code"] = extracted_code
                    st.session_state["tabs"][st.session_state["current_tab"]]["editor_key"] += 1
                    st.success("Code extracted and updated in the editor!")
                else:
                    st.session_state["tabs"][st.session_state["current_tab"]]["review_output"] = extracted_code
                    st.warning("Extracted text does not seem like code. Stored in review section.")
                
                if st.session_state.get('username'):
                    save_review(st.session_state['username'], st.session_state["current_tab"], st.session_state["tabs"][st.session_state["current_tab"]])
                
                st.session_state["last_processed_image_hash"] = image_hash
                st.rerun()
            else:
                st.warning("No code detected in the uploaded image.")
        else:
            st.info("This image has already been processed.")

# Update code in session state and database
if code != current_tab_data["code"]:
    st.session_state["tabs"][current_tab]["code"] = code
    if st.session_state.get('username'):
        save_review(st.session_state['username'], current_tab, st.session_state["tabs"][current_tab])

chat_container = st.container()
with chat_container:
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
