from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import os
import fitz  # PyMuPDF
import docx2txt
from openai import OpenAI

# Load environment variables
load_dotenv()

# Initialize OpenAI client with your API key
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

# ------------------ ROUTES ------------------

@app.route('/')
def loading_screen():
    return render_template("loading.html")

@app.route('/home')
def home():
    return render_template("index.html")

@app.route('/courses')
def courses():
    return render_template("courses.html")

@app.route('/upload')
def upload_page():
    return render_template("upload.html")

@app.route('/ping')
def ping():
    return jsonify({'message': 'pong'})

@app.route('/analyze', methods=['POST'])
def analyze_resume():
    if 'resume' not in request.files:
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
        return jsonify({'error': f'Error reading file: {str(e)}'}), 500

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
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.5
        )
        return jsonify({'analysis': response.choices[0].message.content})
    except Exception as e:
        return jsonify({'error': f'OpenAI API error: {str(e)}'}), 500

# ------------------ MAIN ------------------

if __name__ == '__main__':
    print("🌍 App running at http://localhost:5001/")
    app.run(debug=True, port=5001)
