from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import os
import random
import fitz  # PyMuPDF
import docx2txt
import re

load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

# Simulated real companies with job roles and skills
job_database = [
    {"company": "Google", "role": "Software Engineer", "skills": ["Python", "Data Structures", "Algorithms", "Distributed Systems", "Cloud", "C++"]},
    {"company": "Microsoft", "role": "Data Scientist", "skills": ["Python", "SQL", "Machine Learning", "Pandas", "Statistics", "Azure"]},
    {"company": "Amazon", "role": "Backend Developer", "skills": ["Java", "Microservices", "AWS", "Docker", "REST API", "CI/CD"]},
    {"company": "Meta", "role": "AI Research Engineer", "skills": ["Deep Learning", "PyTorch", "Transformers", "Computer Vision", "Research Papers"]},
    {"company": "Netflix", "role": "Site Reliability Engineer", "skills": ["DevOps", "Monitoring", "AWS", "Kubernetes", "Linux", "Incident Management"]},
    {"company": "Flipkart", "role": "Frontend Developer", "skills": ["React", "JavaScript", "HTML", "CSS", "Redux", "Responsive Design"]},
    {"company": "Zomato", "role": "Product Manager", "skills": ["Product Roadmaps", "Market Research", "Agile", "User Stories", "Analytics"]},
    {"company": "CRED", "role": "ML Engineer", "skills": ["Machine Learning", "TensorFlow", "Python", "Data Pipelines", "Feature Engineering"]},
    {"company": "Uber", "role": "Data Analyst", "skills": ["SQL", "Tableau", "Python", "Business Insights", "Excel"]},
    {"company": "TCS", "role": "Software Tester", "skills": ["Manual Testing", "Automation", "Selenium", "Bug Reporting", "Test Cases"]},
    {"company": "Paytm", "role": "Android Developer", "skills": ["Kotlin", "Java", "Android Studio", "MVVM", "Firebase"]},
    {"company": "Byju's", "role": "Business Development Associate", "skills": ["Sales", "Communication", "Negotiation", "CRM Tools", "Presentation"]},
    {"company": "Infosys", "role": "System Engineer", "skills": ["Java", ".NET", "Database", "SDLC", "Communication Skills"]}
]

@app.route('/')
def home():
    return render_template("index.html")

@app.route('/upload')
def upload():
    return render_template("upload.html")

@app.route('/courses')
def courses():
    return render_template("courses.html")

@app.route('/ping')
def ping():
    return jsonify({'message': 'pong'})

def extract_text(file, ext):
    try:
        if ext == "pdf":
            doc = fitz.open(stream=file.read(), filetype='pdf')
            return "".join([page.get_text() for page in doc])
        elif ext in ["doc", "docx"]:
            return docx2txt.process(file)
        elif ext == "txt":
            return file.read().decode()
    except Exception as e:
        return ""
    return ""

def get_skills_from_resume(text):
    keywords = set([
        "python", "java", "sql", "aws", "azure", "c++", "html", "css", "javascript", "pytorch",
        "tensorflow", "ml", "data structures", "algorithms", "linux", "docker", "kubernetes",
        "react", "redux", "excel", "power bi", "tableau", "agile", "communication", "sales"
    ])
    resume_words = set(word.lower() for word in re.findall(r'\w+', text))
    return list(keywords.intersection(resume_words))

@app.route("/analyze", methods=["POST"])
def analyze_resume():
    if 'resume' not in request.files:
        return jsonify({'error': 'No resume uploaded'}), 400

    file = request.files['resume']
    ext = file.filename.split(".")[-1].lower()
    resume_text = extract_text(file, ext)

    if not resume_text.strip():
        return jsonify({'error': "Couldn't extract text from the resume"}), 500

    resume_skills = get_skills_from_resume(resume_text)
    selected_jobs = random.sample(job_database, 10)

    results = []
    tips = []
    best_score = 0
    best_match = None

    for job in selected_jobs:
        role = job["role"]
        company = job["company"]
        required = job["skills"]
        matched = [s for s in required if s.lower() in map(str.lower, resume_skills)]
        missing = [s for s in required if s.lower() not in map(str.lower, resume_skills)]
        score = int((len(matched) / len(required)) * 100)

        if score > best_score:
            best_score = score
            best_match = {
                "role": role,
                "company": company,
                "score": score,
                "missing": missing
            }

        results.append({
            "role": role,
            "company": company,
            "score": score,
            "matched": matched,
            "missing": missing
        })

        for m in missing:
            tips.append(f"Improve knowledge or experience with '{m}' for {role} at {company}.")

    summary = (
        f"The resume shows experience in {', '.join(resume_skills[:6])}."
        if resume_skills else
        "The resume could benefit from stronger skill descriptions."
    )
    if best_match:
        summary += f" Best match: {best_match['role']} at {best_match['company']} with score {best_match['score']}%."

    return jsonify({
        "analysis": summary,
        "score": best_score,
        "jobs": [f"{j['role']} at {j['company']} - {j['score']}%" for j in results],
        "tips": tips,
        "best_company": best_match['company'] if best_match else None,
        "best_role": best_match['role'] if best_match else None,
        "missing_skills": best_match['missing'] if best_match else []
    })

if __name__ == "__main__":
    print("🚀 SkillWale is running at http://localhost:5001")
    app.run(debug=True, port=5001)
