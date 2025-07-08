# SkillWale: Production-Ready, Feature-Rich Flask Backend
import os
import json
import re
import logging
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_file, session, Blueprint, make_response
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from io import BytesIO
import fitz  # PyMuPDF
import docx2txt
from openai import OpenAI
from config import Config

# --- Setup ---
load_dotenv()
app = Flask(__name__)
app.config.from_object(Config)
CORS(app)
db = SQLAlchemy(app)
limiter = Limiter(get_remote_address, app=app, default_limits=["30/minute"])
app.secret_key = Config.SECRET_KEY

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("skillwale")

# --- OpenAI Client ---
client = OpenAI(api_key=Config.OPENAI_API_KEY)

# --- Models ---
class Analysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    session_id = db.Column(db.String(64))
    resume_skills = db.Column(db.Text)
    roles = db.Column(db.Text)
    scores = db.Column(db.Text)
    summary = db.Column(db.Text)
    tips = db.Column(db.Text)
    interview_questions = db.Column(db.Text)

# --- Utility Functions ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

def validate_file(file):
    filename = secure_filename(file.filename)
    if not allowed_file(filename):
        return False, "File type not allowed."
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > Config.MAX_CONTENT_LENGTH:
        return False, "File too large."
    return True, ""

def extract_text(file):
    filename = secure_filename(file.filename)
    if filename.endswith('.pdf'):
        return extract_from_pdf(file)
    elif filename.endswith('.docx') or filename.endswith('.doc'):
        return docx2txt.process(file)
    elif filename.endswith('.txt'):
        return file.read().decode('utf-8')
    return ""

def extract_from_pdf(file):
    content = ""
    file.seek(0)
    with fitz.open(stream=file.read(), filetype="pdf") as doc:
        for page in doc:
            content += page.get_text()
    return content

def parse_json_like(text):
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return []
    return []

def get_session_id():
    if 'session_id' not in session:
        session['session_id'] = os.urandom(16).hex()
    return session['session_id']

# --- AI Functions ---
def summarize_resume(text):
    prompt = f"Summarize this resume into 2–3 lines (role, key skills, experience):\n\n{text[:1500]}"
    res = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4
    )
    return res.choices[0].message.content.strip()

def extract_skills_ai(text):
    prompt = f"""
Extract 10–15 skills (tech + soft) from this resume:
"""
    prompt += text[:1500]
    prompt += """
Return only a JSON array like:
["Python", "Leadership", "SQL", "Public Speaking"]
"""
    res = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return parse_json_like(res.choices[0].message.content.strip())

def generate_job_roles(candidate_summary):
    prompt = f"""
Generate 7 job roles suitable for this candidate summary:
"""
    prompt += candidate_summary
    prompt += """

For each role, include:
- Role Title
- Company (Google, Amazon, Microsoft, Zomato, CRED, etc.)
- Required Skills (5–8)
- Expected Salary in LPA
- Confidence Level (High/Medium/Low)

Return JSON like:
[
  {
    "role": "Data Analyst",
    "company": "Zomato",
    "skills": ["SQL", "Python", "Data Visualization"],
    "salary": "10-14 LPA",
    "confidence": "High"
  },
  ...
]
"""
    res = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5
    )
    return parse_json_like(res.choices[0].message.content.strip())

def get_improvement_tips(missing_skills, resume_snippet, role, company):
    prompt = f"""
Resume snippet:
"""
    prompt += resume_snippet
    prompt += f"""

Missing skills: {', '.join(missing_skills)}

Provide 2–3 specific resources (free or paid) to improve these skills for the role of {role} at {company}.
Return as bullet points.
"""
    res = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6
    )
    return res.choices[0].message.content.strip()

def generate_interview_questions(role, company, summary):
    prompt = f"""
Generate 5 interview questions for the role of {role} at {company}, based on this candidate summary:
"""
    prompt += summary
    prompt += """
Return as a JSON array of questions.
"""
    res = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5
    )
    return parse_json_like(res.choices[0].message.content.strip())

def ai_resume_tips(text):
    prompt = f"Give 3 specific, actionable tips to improve this resume:\n\n{text[:1500]}\n\nReturn as a JSON array."
    res = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5
    )
    return parse_json_like(res.choices[0].message.content.strip())

# --- Blueprints ---
main_bp = Blueprint('main', __name__)
analysis_bp = Blueprint('analysis', __name__)
scoreboard_bp = Blueprint('scoreboard', __name__)
admin_bp = Blueprint('admin', __name__)

# --- Main Routes ---
@main_bp.route('/')
def loading_screen():
    return render_template("loading.html")

@main_bp.route('/home')
def home():
    return render_template("index.html")

@main_bp.route('/upload')
def upload_page():
    return render_template("upload.html")

@main_bp.route('/courses')
def courses_page():
    return render_template("courses.html")

@main_bp.route('/ping')
def ping():
    return jsonify({'message': 'pong'})

# --- Analysis Route ---
@analysis_bp.route('/analyze', methods=["POST"])
@limiter.limit("10/minute")
def analyze_resume():
    if 'resume' not in request.files or 'description' not in request.form:
        return jsonify({"error": "Missing file or description"}), 400
    file = request.files['resume']
    desc = request.form['description']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    valid, msg = validate_file(file)
    if not valid:
        return jsonify({"error": msg}), 400
    try:
        text = extract_text(file)
        if not text:
            return jsonify({"error": "Unable to extract resume text"}), 500
        summary = summarize_resume(text)
        resume_skills = set(s.lower() for s in extract_skills_ai(text))
        job_roles = generate_job_roles(summary)
        results = []
        all_tips = []
        all_questions = []
        for jd in job_roles:
            required_skills = set(skill.lower() for skill in jd['skills'])
            matched = required_skills & resume_skills
            missing = required_skills - resume_skills
            score = round((len(matched) / len(required_skills)) * 10, 1)
            tips = get_improvement_tips(list(missing), text[:1000], jd['role'], jd['company'])
            interview_qs = generate_interview_questions(jd['role'], jd['company'], summary)
            all_tips.append(tips)
            all_questions.append(interview_qs)
            results.append({
                "role": jd['role'],
                "company": jd['company'],
                "expected_salary": jd.get('salary', ''),
                "match_score": score,
                "matched_skills": list(matched),
                "missing_skills": list(missing),
                "improvement_tips": tips,
                "interview_questions": interview_qs
            })
        # AI resume tips
        resume_tips = ai_resume_tips(text)
        # Save analysis to DB
        analysis = Analysis(
            session_id=get_session_id(),
            resume_skills=','.join(resume_skills),
            roles=','.join([r['role'] for r in job_roles]),
            scores=','.join([str(r['match_score']) for r in results]),
            summary=summary,
            tips=json.dumps(resume_tips),
            interview_questions=json.dumps(all_questions)
        )
        db.session.add(analysis)
        db.session.commit()
        return jsonify({"results": results, "resume_summary": summary, "resume_tips": resume_tips})
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return jsonify({"error": f"Analysis failed: {e}"}), 500

# --- Scoreboard Route ---
@scoreboard_bp.route('/scoreboard')
def scoreboard():
    try:
        analyses = Analysis.query.order_by(Analysis.timestamp.desc()).limit(100).all()
        stats = {
            "total_analyses": Analysis.query.count(),
            "recent_roles": [],
            "top_skills": [],
            "avg_score": 0
        }
        all_skills = []
        all_scores = []
        all_roles = []
        for a in analyses:
            all_skills.extend(a.resume_skills.split(','))
            all_scores.extend([float(s) for s in a.scores.split(',') if s])
            all_roles.extend(a.roles.split(','))
        from collections import Counter
        stats["recent_roles"] = all_roles[:10]
        stats["top_skills"] = [s for s, _ in Counter(all_skills).most_common(10)]
        stats["avg_score"] = round(sum(all_scores)/len(all_scores), 2) if all_scores else 0
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Scoreboard error: {e}")
        return jsonify({"error": f"Scoreboard failed: {e}"}), 500

# --- Leaderboard Route ---
@scoreboard_bp.route('/leaderboard')
def leaderboard():
    try:
        analyses = Analysis.query.order_by(Analysis.timestamp.desc()).limit(100).all()
        leaderboard = []
        for a in analyses:
            if a.scores:
                max_score = max([float(s) for s in a.scores.split(',') if s])
                leaderboard.append({
                    "session_id": a.session_id[-6:],
                    "max_score": max_score,
                    "roles": a.roles.split(',')
                })
        leaderboard = sorted(leaderboard, key=lambda x: x["max_score"], reverse=True)[:10]
        return jsonify(leaderboard)
    except Exception as e:
        logger.error(f"Leaderboard error: {e}")
        return jsonify({"error": f"Leaderboard failed: {e}"}), 500

# --- AI Tips Endpoint ---
@analysis_bp.route('/tips', methods=["POST"])
@limiter.limit("20/minute")
def ai_tips():
    data = request.get_json()
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "No text provided"}), 400
    try:
        tips = ai_resume_tips(text)
        return jsonify({"tips": tips})
    except Exception as e:
        logger.error(f"AI tips error: {e}")
        return jsonify({"error": f"AI tips failed: {e}"}), 500

# --- Download Report Endpoint ---
@analysis_bp.route('/download_report', methods=["POST"])
def download_report():
    data = request.get_json()
    summary = data.get("summary", "")
    results = data.get("results", [])
    tips = data.get("tips", [])
    # Generate a simple text report (could be PDF with more work)
    report = f"SkillWale Resume Analysis Report\n\nSummary:\n{summary}\n\nResults:\n"
    for r in results:
        report += f"\nRole: {r['role']} at {r['company']}\nMatch Score: {r['match_score']}\nMatched Skills: {', '.join(r['matched_skills'])}\nMissing Skills: {', '.join(r['missing_skills'])}\nTips: {r['improvement_tips']}\n"
    report += f"\nGeneral Resume Tips:\n"
    for t in tips:
        report += f"- {t}\n"
    buf = BytesIO()
    buf.write(report.encode('utf-8'))
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="SkillWale_Resume_Report.txt", mimetype="text/plain")

# --- Interview Questions Endpoint ---
@analysis_bp.route('/interview_questions', methods=["POST"])
def interview_questions():
    data = request.get_json()
    role = data.get("role", "")
    company = data.get("company", "")
    summary = data.get("summary", "")
    if not (role and company and summary):
        return jsonify({"error": "Missing data"}), 400
    try:
        questions = generate_interview_questions(role, company, summary)
        return jsonify({"questions": questions})
    except Exception as e:
        logger.error(f"Interview questions error: {e}")
        return jsonify({"error": f"Interview questions failed: {e}"}), 500

# --- Admin CLI Commands ---
@admin_bp.cli.command("init-db")
def init_db():
    db.create_all()
    print("Database initialized.")

@admin_bp.cli.command("reset-scoreboard")
def reset_scoreboard():
    db.drop_all()
    db.create_all()
    print("Scoreboard reset.")

@admin_bp.cli.command("export-analyses")
def export_analyses():
    analyses = Analysis.query.all()
    data = [
        {
            "timestamp": a.timestamp.isoformat(),
            "summary": a.summary,
            "roles": a.roles,
            "scores": a.scores,
            "tips": a.tips
        } for a in analyses
    ]
    with open("analyses_export.json", "w") as f:
        json.dump(data, f, indent=2)
    print(f"Exported {len(data)} analyses to analyses_export.json")

# --- Register Blueprints ---
app.register_blueprint(main_bp)
app.register_blueprint(analysis_bp)
app.register_blueprint(scoreboard_bp)
app.register_blueprint(admin_bp)

# --- Main ---
   
if __name__ == "__main__":
    print("🚀 SkillWale AI Backend running at http://localhost:5001")
    app.run(debug=True, port=5001)
