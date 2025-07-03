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

# 📘 Skill Glossary with Explanations
SKILL_EXPLANATIONS = {
    "Deep Learning": "Building neural networks for image, speech, and language tasks.",
    "PyTorch": "Popular framework for deep learning model development and research.",
    "Transformers": "State-of-the-art models used in NLP (e.g., BERT, GPT).",
    "TensorFlow": "End-to-end open-source platform for machine learning.",
    "NLP": "Natural Language Processing — making machines understand human language.",
    "SQL": "Structured Query Language for managing and querying databases.",
    "React": "A JavaScript library for building interactive user interfaces.",
    "Docker": "Tool for containerizing and deploying applications.",
    "Kubernetes": "System for automating container deployment, scaling, and management.",
    "System Design": "Designing scalable and efficient software systems.",
    "AWS": "Amazon Web Services — cloud computing platform.",
    "CI/CD": "Automated testing and deployment in development pipelines.",
    "Redux": "State management library used with React.",
    "Scikit-learn": "Python library for simple and efficient machine learning.",
    "Spring": "Java framework for building scalable backend applications.",
    "Figma": "Design tool for UI/UX collaboration.",
    "JIRA": "Tool for project management and issue tracking.",
    "Firebase": "Google platform for mobile/web app development.",
    "MVVM": "Architecture pattern used in Android development.",
    "Pandas": "Data manipulation and analysis library in Python.",
    "Excel": "Spreadsheet tool for data analysis and modeling.",
    "HTML": "Standard markup language for web pages.",
    "CSS": "Stylesheet language for styling HTML elements.",
    "JavaScript": "Scripting language for interactive web functionality.",
    "Manual Testing": "Manually checking software for bugs and issues.",
    "Bug Reporting": "Logging defects found during testing.",
    "Roadmapping": "Planning and strategizing product features.",
    "Analytics": "Interpreting data to make informed decisions.",
    "Communication": "Effectively exchanging information and ideas.",
}

# 🧠 Known skills set
KNOWN_SKILLS = set(map(str.lower, SKILL_EXPLANATIONS.keys()))

# 🏢 Simulated Job Descriptions
JOB_DATABASE = [
    {"company": "Google", "role": "Software Engineer", "skills": ["Python", "C++", "Distributed Systems", "Cloud", "Algorithms", "System Design"]},
    {"company": "Microsoft", "role": "Data Scientist", "skills": ["Python", "SQL", "Machine Learning", "Pandas", "Power BI", "Azure"]},
    {"company": "Amazon", "role": "Backend Developer", "skills": ["Java", "Spring", "Docker", "AWS", "REST API", "CI/CD"]},
    {"company": "Meta", "role": "AI Researcher", "skills": ["Deep Learning", "PyTorch", "Transformers", "NLP", "Research Papers"]},
    {"company": "Netflix", "role": "SRE", "skills": ["Kubernetes", "Linux", "Monitoring", "AWS", "DevOps", "Incident Management"]},
    {"company": "CRED", "role": "ML Engineer", "skills": ["Python", "TensorFlow", "Scikit-learn", "Data Pipelines", "Feature Engineering"]},
    {"company": "Flipkart", "role": "Frontend Developer", "skills": ["React", "JavaScript", "HTML", "CSS", "Redux", "Figma"]},
    {"company": "Zomato", "role": "Product Manager", "skills": ["Roadmapping", "Analytics", "Communication", "Market Research", "A/B Testing"]},
    {"company": "Uber", "role": "Data Analyst", "skills": ["SQL", "Excel", "Tableau", "Python", "Business Insights"]},
    {"company": "Infosys", "role": "QA Engineer", "skills": ["Manual Testing", "Selenium", "Bug Reporting", "Test Cases", "JIRA"]},
    {"company": "Paytm", "role": "Android Developer", "skills": ["Kotlin", "Java", "Android Studio", "MVVM", "Firebase"]},
]

# 📄 Extract text from uploaded resume
def extract_text(file, ext):
    try:
        if ext == "pdf":
            doc = fitz.open(stream=file.read(), filetype='pdf')
            return "".join([page.get_text() for page in doc])
        elif ext in ["doc", "docx"]:
            return docx2txt.process(file)
        elif ext == "txt":
            return file.read().decode()
        else:
            return ""
    except Exception as e:
        print(f"[ERROR] Failed to extract text: {e}")
        return ""

# 🧠 Extract lowercase skills from resume
def extract_skills(text):
    words = set(word.lower() for word in re.findall(r'\w+', text))
    return sorted(KNOWN_SKILLS.intersection(words))

# 🔎 Analyze resume against job DB
def analyze_against_jobs(resume_skills, jobs):
    results = []
    best_match = None
    best_score = 0
    tips = []

    for job in jobs:
        required = job["skills"]
        matched = [s for s in required if s.lower() in resume_skills]
        missing = [s for s in required if s.lower() not in resume_skills]
        score = int((len(matched) / len(required)) * 100)

        # Suggestions
        explanation_lines = [
            f"- **{skill}**: {SKILL_EXPLANATIONS.get(skill, 'No description available.')}"
            for skill in missing[:4]
        ]
        improvement_text = f"Improve your skills for **{job['role']}**:\n" + "\n".join(explanation_lines)

        if score > best_score:
            best_score = score
            best_match = {
                "company": job["company"],
                "role": job["role"],
                "score": score,
                "missing": missing
            }

        results.append({
            "company": job["company"],
            "role": job["role"],
            "match": score,
            "matchDetail": f"{len(matched)}/{len(required)} skills matched",
            "matchedSkills": matched,
            "missingSkills": missing,
            "improvement": improvement_text
        })

        tips.extend([
            f"{skill}: {SKILL_EXPLANATIONS.get(skill, 'No description.')}"
            for skill in missing
        ])

    results.sort(key=lambda x: x["match"], reverse=True)
    return results, best_match, list(set(tips))

# 🌐 Routes
@app.route('/')
def loading_screen():
    return render_template("loading.html")

@app.route('/home')
def home():
    return render_template("index.html")

@app.route('/upload')
def upload_page():
    return render_template("upload.html")

@app.route('/courses')
def courses_page():
    return render_template("courses.html")

@app.route('/ping')
def ping():
    return jsonify({'message': 'pong'})

# 📤 Upload and analyze resume
@app.route('/analyze', methods=["POST"])
def analyze_resume():
    if 'resume' not in request.files:
        return jsonify({"error": "No resume uploaded"}), 400

    file = request.files["resume"]
    ext = file.filename.split('.')[-1].lower()

    if ext not in ["pdf", "doc", "docx", "txt"]:
        return jsonify({"error": f"Unsupported file type: .{ext}"}), 400

    resume_text = extract_text(file, ext)

    if not resume_text.strip():
        return jsonify({"error": "Couldn't extract text from the resume"}), 500

    resume_skills = extract_skills(resume_text)

    if not resume_skills:
        return jsonify({"error": "No recognizable skills found in the resume. Please include industry-relevant skills."}), 200

    selected_jobs = [
        job for job in JOB_DATABASE
        if any(skill.lower() in resume_skills for skill in job["skills"])
    ]

    if len(selected_jobs) < 5:
        selected_jobs += random.sample(JOB_DATABASE, 5)

    results, best_match, tips = analyze_against_jobs(resume_skills, selected_jobs)

    summary = (
        f"The resume demonstrates skills in {', '.join(resume_skills[:6])}."
        if resume_skills else
        "No significant skills were detected in the resume."
    )
    if best_match:
        summary += f" Best match: {best_match['role']} at {best_match['company']} ({best_match['score']}%)."

    return jsonify({
        "analysis": summary,
        "score": best_match["score"] if best_match else 0,
        "resume_skills": resume_skills,
        "resume_skill_count": len(resume_skills),
        "jobs": results,
        "tips": tips,
        "best_company": best_match["company"] if best_match else None,
        "best_role": best_match["role"] if best_match else None,
        "missing_skills": best_match["missing"] if best_match else []
    })

# 🛠 Error handler
@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error occurred."}), 500

# 🚀 Start Server
if __name__ == "__main__":
    print("🚀 SkillWale running on http://localhost:5001")
    app.run(debug=True, port=5001)
