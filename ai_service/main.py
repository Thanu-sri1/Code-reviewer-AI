from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
import google.generativeai as genai
import os
from PIL import Image
import io

app = FastAPI(title="AI Service")

key = os.getenv("GEMINI_API_KEY")  
if not key:
    raise RuntimeError("Gemini API key not found. Please set GEMINI_API_KEY.")

genai.configure(api_key=key)

system_prompt = """You are a code reviewer specializing in Python. Your task is to:
- Analyze submitted code.
- Identify potential bugs or errors.
- Suggest optimizations or improvements.
- Provide the corrected version in Python if the code is in another language.

🔍 **Response Structure**:
1️⃣ **Bug/Error Identification**
   - Detect errors in the provided code.
   - If it's **not Python**, identify the language and explain syntax differences.
   
2️⃣ **Suggested Fixes/Optimizations**
   - Recommend fixes for errors.
   - If the code is in another language, show the **correct equivalent in Python**.

3️⃣ **Corrected Code**
   - Provide the correct **Python version**.
   - Ensure it's fully functional and valid.
   - Explain the changes.

📌 **Important**:
- If the code is in Java, C++, JavaScript, etc., explain how to translate it into Python.
- DO NOT reject non-Python code; instead, analyze it and convert it if possible.
- Always wrap the corrected Python code in triple backticks with 'python' language identifier.
"""

system_prompt2 = """📌 Role: You are an advanced AI model specialized in extracting raw programming code from images.

🎯 Task:

    Extract only the programming code from the given image.
    Do NOT include explanations, comments, or any extra text.
    Do NOT format the output as markdown, JSON, or any other structured format—just return the plain code.
    Preserve indentation, special characters, and syntax exactly as seen in the image.

⚠️ Restrictions:
    
    Do not add headers, footers, or descriptions.
    Do not modify, interpret, or translate the code.
    If the image contains multiple code snippets, extract them in the same order as they appear.
    if it doesn't contain any code just return a polite request to include a photo that contains code.

✅ Expected Output:
    
    The raw programming code extracted as plain text, exactly as shown in the image."""

model = genai.GenerativeModel("gemini-2.5-flash", system_instruction=system_prompt)
model2 = genai.GenerativeModel("gemini-2.5-flash", system_instruction=system_prompt2)

class ReviewRequest(BaseModel):
    code: str

class ReviewResponse(BaseModel):
    review_output: str
    fixed_code: str

@app.post("/review", response_model=ReviewResponse)
def review_code(request: ReviewRequest):
    try:
        prompt = f"Review this code and provide fixes:\n{request.code}"
        response = model.generate_content(prompt)
        review_output = response.text
        
        fixed_code = ""
        if "```python" in response.text:
            try:
                fixed_code = response.text.split("```python")[1].split("```")[0].strip()
            except IndexError:
                pass
                
        return {"review_output": review_output, "fixed_code": fixed_code}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/extract")
async def extract_code(file: UploadFile = File(...)):
    try:
        image_bytes = await file.read()
        image = Image.open(io.BytesIO(image_bytes))
        
        response = model2.generate_content([
            "Extract only the programming code from this image.Do NOT include explanations, comments, or extra text. Just return the raw python code: ", 
            image
        ])
        
        extracted_code = response.text.strip() if response.text else ""
        return {"extracted_code": extracted_code}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
