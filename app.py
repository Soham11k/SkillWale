from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import openai
import os
import fitz  # PyMuPDF
import docx2txt

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

# Load OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")
print("🔑 OpenAI Key Loaded:", openai.api_key is not None)

# ------------------ ROUTES ------------------

# Landing route — Loading screen
@app.route('/')
def loading_screen():
    print("⏳ Serving loading.html")
    return render_template("loading.html")

# Homepage route
@app.route('/home')
def home():
    print("🏠 Serving index.html")
    return render_template("index.html")

# Courses page route
@app.route('/courses')
def courses():
    print("📚 Serving courses.html")
    return render_template("courses.html")

# Upload page route
@app.route('/upload')
def upload_page():
    print("📤 Serving upload.html")
    return render_template("upload.html")

# Health check
@app.route('/ping')
def ping():
    return jsonify({'message': 'pong'})

# Resume analysis
@app.route('/analyze', methods=['POST'])
def analyze_resume():
    print("🚀 /analyze endpoint hit")

    if 'resume' not in request.files:
        print("❌ No resume file provided")
        return jsonify({'error': 'No resume file provided'}), 400

    file = request.files['resume']
    filename = file.filename
    ext = filename.split('.')[-1].lower()

    try:
        if ext == 'pdf':
            doc = fitz.open(stream=file.read(), filetype='pdf')
            text = ''.join([page.get_text() for page in doc])
        elif ext in ['doc', 'docx']:
            text = docx2txt.process(file)
        elif ext == 'txt':
            text = file.read().decode()
        else:
            return jsonify({'error': 'Unsupported file type'}), 400
    except Exception as e:
        print("❌ Error reading file:", e)
        return jsonify({'error': 'Error reading file'}), 500

    prompt = f"""
Analyze the following resume and suggest:

1. Most suitable job role
2. Estimated salary (INR range)
3. Key strengths and skills
4. Any weak areas or resume improvement tips

Resume:
{text}
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5
        )
        reply = response['choices'][0]['message']['content']
        print("✅ Analysis complete")
        return jsonify({'analysis': reply})
    except Exception as e:
        print("❌ OpenAI API error:", e)
        return jsonify({'error': str(e)}), 500

# ------------------ MAIN ------------------

if __name__ == '__main__':
    print("🌍 App running at http://localhost:5001/ (loading screen)")
    app.run(debug=True, port=5001)
