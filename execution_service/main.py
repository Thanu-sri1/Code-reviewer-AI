# pyrefly: ignore [missing-import]
from fastapi import FastAPI
# pyrefly: ignore [missing-import]
from pydantic import BaseModel
import subprocess
import os

app = FastAPI(title="Execution Service")

class CodeRequest(BaseModel):
    code: str
    tab_id: str

class CodeResponse(BaseModel):
    output: str

@app.post("/run", response_model=CodeResponse)
def run_code(request: CodeRequest):
    """Execute Python code and capture output."""
    temp_file = f"temp_{request.tab_id}.py"
    try:
        # Create a temporary file to execute the code
        with open(temp_file, "w") as f:
            f.write(request.code)
        
        # Run the code and capture output
        result = subprocess.run(
            ["python3", temp_file],
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout
        )
        
        # Return both stdout and stderr
        output = result.stdout
        if result.stderr:
            output += "\nErrors:\n" + result.stderr
            
        return {"output": output}
    except subprocess.TimeoutExpired:
        return {"output": "Error: Code execution timed out (30 second limit)"}
    except Exception as e:
        return {"output": f"Error: {str(e)}"}
    finally:
        # Ensure temp file is removed even if there's an error
        if os.path.exists(temp_file):
            os.remove(temp_file)
