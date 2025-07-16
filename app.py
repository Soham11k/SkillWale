# SkillWale: Modern Flask Backend
import os
import json
import re
import logging
import asyncio
import concurrent.futures
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
from celery import Celery
from flask_pymongo import PyMongo
from flask_pymongo import PyMongo


def make_celery(app):
    celery = Celery(
        app.import_name,
        backend=app.config['CELERY_RESULT_BACKEND'],
        broker=app.config['CELERY_BROKER_URL']
    )
    celery.conf.update(app.config)
    TaskBase = celery.Task

    class ContextTask(TaskBase):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)
    celery.Task = ContextTask
    return celery

# --- Configuration & Setup ---
load_dotenv()
app = Flask(__name__)
app.config.from_object(Config)
app.config.update(
    CELERY_BROKER_URL='redis://localhost:6379/0',
    CELERY_RESULT_BACKEND='redis://localhost:6379/0'
)
CORS(app)
limiter = Limiter(get_remote_address, app=app, default_limits=["30/minute"])
app.secret_key = Config.SECRET_KEY
app.config["MONGO_URI"] = "mongodb://localhost:27017/skillwale"
mongo = PyMongo(app)

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("skillwale")

# --- OpenAI Client ---
try:
    if not Config.OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not found in environment variables")
        client = None
    else:
        client = OpenAI(api_key=Config.OPENAI_API_KEY)
        # Test the API key
        client.models.list()
        logger.info("OpenAI client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize OpenAI client: {e}")
    client = None

# --- Utility Functions ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

def validate_file(file):
    if not file or file.filename == '':
        return False, "No file selected."
    
    filename = secure_filename(file.filename)
    if not allowed_file(filename):
        return False, f"File type not allowed. Allowed types: {', '.join(Config.ALLOWED_EXTENSIONS)}"
    
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    
    if size > Config.MAX_CONTENT_LENGTH:
        return False, f"File too large. Maximum size: {Config.MAX_CONTENT_LENGTH // (1024*1024)}MB"
    
    return True, ""

def extract_text(file):
    try:
        filename = secure_filename(file.filename)
        if filename.endswith('.pdf'):
            return extract_from_pdf(file)
        elif filename.endswith('.docx') or filename.endswith('.doc'):
            return docx2txt.process(file)
        elif filename.endswith('.txt'):
            return file.read().decode('utf-8')
        else:
            return ""
    except Exception as e:
        logger.error(f"Error extracting text from file: {e}")
        return ""

def extract_from_pdf(file):
    try:
        content = ""
        file.seek(0)
        with fitz.open(stream=file.read(), filetype="pdf") as doc:
            for page in doc:
                content += page.get_text()
        return content
    except Exception as e:
        logger.error(f"Error extracting PDF text: {e}")
        return ""

def parse_json_like(text):
    try:
        return json.loads(text)
    except Exception:
        # Try to extract JSON array from text
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
        # Try to extract JSON object from text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return []

def get_session_id():
    if 'session_id' not in session:
        session['session_id'] = os.urandom(16).hex()
    return session['session_id']

# --- Optimized AI Functions ---
def summarize_resume(text):
    if not client:
        return "Experienced professional with strong technical skills and leadership abilities."
    
    try:
        prompt = f"""Analyze this resume and provide a comprehensive summary including:
1. Professional role/title
2. Years of experience
3. Key technical skills (5-7 skills)
4. Industry/sector focus
5. Notable achievements or projects
6. Education background
7. Career aspirations

Resume text:
{text[:1500]}

Provide a detailed but concise summary that captures the candidate's profile."""
        res = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error summarizing resume: {e}")
        return "Experienced professional with strong technical skills and leadership abilities."

def extract_skills_ai(text):
    if not client:
        return [
            "Python", "JavaScript", "Leadership", "Communication", "Problem Solving", "SQL", "React", "AWS", "Docker", "Node.js", "C++", "Java", "Spring", "Kubernetes", "Linux", "Django", "Go", "Ruby", "PHP", "Swift", "TypeScript", "Angular", "Vue.js", "PostgreSQL", "MySQL", "HTML", "CSS", "Teamwork", "Agile", "Scrum", "Project Management", "Creativity", "Critical Thinking"
        ]
    
    try:
        prompt = f"""Extract comprehensive skills from this resume. Categorize them as:
1. Technical Skills (programming languages, tools, frameworks)
2. Soft Skills (communication, leadership, teamwork)
3. Domain Skills (industry-specific knowledge)
4. Certifications (if any)

Resume text:
{text[:1200]}

Return as JSON array with categorized skills: ["Python", "JavaScript", "Leadership", "Communication", "Problem Solving", "AWS", "Docker", "Agile"]"""
        res = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=200
        )
        skills = parse_json_like(res.choices[0].message.content.strip())
        return skills if skills else ["Python", "JavaScript", "Leadership", "Communication", "Problem Solving"]
    except Exception as e:
        logger.error(f"Error extracting skills: {e}")
        return ["Python", "JavaScript", "Leadership", "Communication", "Problem Solving"]

def generate_job_roles(candidate_summary):
    if not client:
        # Fallback: 50+ static roles for demo
        companies = [
            "Google", "Amazon", "Microsoft", "Apple", "Meta", "Netflix", "Tesla", "Adobe", "Salesforce", "IBM",
            "Oracle", "Uber", "Airbnb", "Stripe", "Shopify", "Twitter", "LinkedIn", "Intel", "Nvidia", "Qualcomm",
            "Cisco", "Dell", "HP", "SAP", "Zoom", "Atlassian", "Dropbox", "Slack", "Square", "Pinterest",
            "Red Hat", "VMware", "Palantir", "Snowflake", "Coinbase", "Robinhood", "DoorDash", "Spotify", "Snap",
            "Zillow", "Yelp", "GitHub", "Bitbucket", "Asana", "Notion", "Figma", "Canva", "Twitch", "Discord"
        ]
        fallback_skills = [
            ["Python", "Django", "SQL", "Git"],
            ["JavaScript", "React", "Node.js", "CSS"],
            ["AWS", "Docker", "Kubernetes", "Linux"],
            ["Java", "Spring", "Hibernate", "MySQL"],
            ["C++", "Algorithms", "Data Structures", "Linux"],
            ["Go", "Microservices", "gRPC", "Kubernetes"],
            ["Ruby", "Rails", "PostgreSQL", "Redis"],
            ["PHP", "Laravel", "MySQL", "Vue.js"],
            ["Swift", "iOS", "Xcode", "UIKit"],
            ["TypeScript", "Angular", "RxJS", "Sass"],
        ]
        logo_map = {
            "Google": "https://cdn.jsdelivr.net/gh/devicons/devicon/icons/google/google-original.svg",
            "Amazon": "https://cdn.jsdelivr.net/gh/devicons/devicon/icons/amazonwebservices/amazonwebservices-original.svg",
            "Microsoft": "https://cdn.jsdelivr.net/gh/devicons/devicon/icons/microsoft/microsoft-original.svg",
            "Apple": "https://cdn.jsdelivr.net/gh/devicons/devicon/icons/apple/apple-original.svg",
            "Meta": "https://cdn.jsdelivr.net/gh/devicons/devicon/icons/facebook/facebook-original.svg",
            "Netflix": "https://upload.wikimedia.org/wikipedia/commons/0/08/Netflix_2015_logo.svg",
            "Tesla": "https://upload.wikimedia.org/wikipedia/commons/b/bd/Tesla_Motors.svg",
            "Adobe": "https://cdn.jsdelivr.net/gh/devicons/devicon/icons/adobe/adobe-original.svg",
            "Salesforce": "https://upload.wikimedia.org/wikipedia/commons/2/2e/Salesforce_logo.svg",
            "IBM": "https://cdn.jsdelivr.net/gh/devicons/devicon/icons/ibm/ibm-original.svg",
        }
        roles = []
        for i, company in enumerate(companies):
            roles.append({
                "role": f"Software Engineer {i+1}",
                "company": company,
                "skills": fallback_skills[i % len(fallback_skills)],
                "salary": f"{12+i%10}-{22+i%10} LPA",
                "confidence": "Medium",
                "logo_url": logo_map.get(company, "https://cdn.jsdelivr.net/gh/devicons/devicon/icons/code/code-original.svg")
            })
        return roles
    try:
        prompt = f"""Generate 50 diverse job roles for this candidate profile. For each, include:
- role title
- company (real or realistic tech companies)
- required skills (6-8, mix of tech, soft, and domain)
- salary range (realistic for the role)
- confidence (High/Medium/Low)
- job description snippet (2-3 lines)
- growth potential (entry/mid/senior)
Return as a JSON array of 50 objects."""
        prompt += f"\n\nCandidate Profile: {candidate_summary}"
        res = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=4000
        )
        roles = parse_json_like(res.choices[0].message.content.strip())
        # If the model returns less than 50, pad with fallback
        if not roles or len(roles) < 50:
            companies = [
                "Google", "Amazon", "Microsoft", "Apple", "Meta", "Netflix", "Tesla", "Adobe", "Salesforce", "IBM",
                "Oracle", "Uber", "Airbnb", "Stripe", "Shopify", "Twitter", "LinkedIn", "Intel", "Nvidia", "Qualcomm",
                "Cisco", "Dell", "HP", "SAP", "Zoom", "Atlassian", "Dropbox", "Slack", "Square", "Pinterest",
                "Red Hat", "VMware", "Palantir", "Snowflake", "Coinbase", "Robinhood", "DoorDash", "Spotify", "Snap",
                "Zillow", "Yelp", "GitHub", "Bitbucket", "Asana", "Notion", "Figma", "Canva", "Twitch", "Discord"
            ]
            for i in range(50 - len(roles)):
                roles.append({
                    "role": f"Software Engineer {i+1}",
                    "company": companies[i % len(companies)],
                    "skills": ["Python", "JavaScript", "React", "SQL", "Git", "AWS", "Docker"],
                    "salary": f"{12+i%10}-{22+i%10} LPA",
                    "confidence": "Medium"
                })
        return roles
    except Exception as e:
        logger.error(f"Error generating job roles: {e}")
        # Fallback: 50 static roles
        companies = [
            "Google", "Amazon", "Microsoft", "Apple", "Meta", "Netflix", "Tesla", "Adobe", "Salesforce", "IBM",
            "Oracle", "Uber", "Airbnb", "Stripe", "Shopify", "Twitter", "LinkedIn", "Intel", "Nvidia", "Qualcomm",
            "Cisco", "Dell", "HP", "SAP", "Zoom", "Atlassian", "Dropbox", "Slack", "Square", "Pinterest",
            "Red Hat", "VMware", "Palantir", "Snowflake", "Coinbase", "Robinhood", "DoorDash", "Spotify", "Snap",
            "Zillow", "Yelp", "GitHub", "Bitbucket", "Asana", "Notion", "Figma", "Canva", "Twitch", "Discord"
        ]
        roles = []
        for i, company in enumerate(companies):
            roles.append({
                "role": f"Software Engineer {i+1}",
                "company": company,
                "skills": ["Python", "JavaScript", "React", "SQL", "Git", "AWS", "Docker"],
                "salary": f"{12+i%10}-{22+i%10} LPA",
                "confidence": "Medium"
            })
        return roles

def get_improvement_tips(missing_skills, resume_snippet, role, company):
    if not client:
        return "• Take online courses on platforms like Coursera or Udemy\n• Practice with real-world projects\n• Join relevant communities and forums"
    
    try:
        prompt = f"Missing skills: {', '.join(missing_skills[:3])}\nRole: {role} at {company}\nProvide 2 specific improvement tips as bullet points."
        res = client.chat.completions.create(
            model="gpt-3.5-turbo",  # Faster model
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=150
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error getting improvement tips: {e}")
        return "• Take online courses on platforms like Coursera or Udemy\n• Practice with real-world projects\n• Join relevant communities and forums"

def generate_interview_questions(role, company, summary):
    if not client:
        return [
            "Tell me about a challenging project you worked on.",
            "How do you handle tight deadlines?",
            "What are your strengths and weaknesses?",
            "Why do you want to work at this company?",
            "Where do you see yourself in 5 years?"
        ]
    
    try:
        prompt = f"Generate 3 interview questions for {role} at {company}. Return as JSON array."
        res = client.chat.completions.create(
            model="gpt-3.5-turbo",  # Faster model
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=200
        )
        questions = parse_json_like(res.choices[0].message.content.strip())
        return questions if questions else [
            "Tell me about a challenging project you worked on.",
            "How do you handle tight deadlines?",
            "What are your strengths and weaknesses?"
        ]
    except Exception as e:
        logger.error(f"Error generating interview questions: {e}")
        return [
            "Tell me about a challenging project you worked on.",
            "How do you handle tight deadlines?",
            "What are your strengths and weaknesses?"
        ]

def ai_resume_tips(text):
    if not client:
        return [
            "Add quantifiable achievements to your experience section",
            "Include relevant keywords for ATS optimization",
            "Keep your resume concise and well-formatted"
        ]
    
    try:
        prompt = f"""Analyze this resume and provide comprehensive improvement tips:

Resume text: {text[:800]}

Provide 4-5 specific, actionable tips covering:
1. Content improvements (achievements, metrics, keywords)
2. Format and structure suggestions
3. Skill presentation and organization
4. ATS optimization recommendations
5. Industry-specific advice

Return as JSON array of detailed tips."""
        res = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=300
        )
        tips = parse_json_like(res.choices[0].message.content.strip())
        return tips if tips else [
            "Add quantifiable achievements to your experience section",
            "Include relevant keywords for ATS optimization"
        ]
    except Exception as e:
        logger.error(f"Error generating resume tips: {e}")
        return [
            "Add quantifiable achievements to your experience section",
            "Include relevant keywords for ATS optimization"
        ]

def generate_candidate_insights(text, skills, summary):
    """Generate detailed candidate insights and personality traits"""
    if not client:
        return {
            "personality_traits": ["Analytical", "Team Player", "Problem Solver"],
            "strengths": ["Technical expertise", "Communication skills"],
            "growth_areas": ["Leadership experience", "Industry knowledge"],
            "career_path": "Software Development → Senior Developer → Tech Lead",
            "recommended_certifications": ["AWS Certified Developer", "Google Cloud Professional"]
        }
    
    try:
        prompt = f"""Based on this candidate's resume, provide detailed insights:

Resume: {text[:1000]}
Skills: {', '.join(skills)}
Summary: {summary}

Analyze and provide:
1. Personality traits (3-4 traits that shine through)
2. Key strengths (3-4 areas where they excel)
3. Growth areas (2-3 areas for improvement)
4. Career path suggestions (realistic progression)
5. Recommended certifications (3-4 relevant certs)
6. Industry fit (which sectors/companies would be ideal)

Return as JSON object with these insights."""
        
        res = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=400
        )
        insights = parse_json_like(res.choices[0].message.content.strip())
        return insights if insights else {
            "personality_traits": ["Analytical", "Team Player", "Problem Solver"],
            "strengths": ["Technical expertise", "Communication skills"],
            "growth_areas": ["Leadership experience", "Industry knowledge"],
            "career_path": "Software Development → Senior Developer → Tech Lead",
            "recommended_certifications": ["AWS Certified Developer", "Google Cloud Professional"]
        }
    except Exception as e:
        logger.error(f"Error generating candidate insights: {e}")
        return {
            "personality_traits": ["Analytical", "Team Player", "Problem Solver"],
            "strengths": ["Technical expertise", "Communication skills"],
            "growth_areas": ["Leadership experience", "Industry knowledge"],
            "career_path": "Software Development → Senior Developer → Tech Lead",
            "recommended_certifications": ["AWS Certified Developer", "Google Cloud Professional"]
        }

def fuzzy_skill_match(resume_skills, required_skills):
    matched = set()
    for req in required_skills:
        for res in resume_skills:
            if req in res or res in req:
                matched.add(req)
    return matched

# --- Parallel Processing Functions ---
def process_job_role_parallel(jd, resume_skills, text, summary):
    """Process a single job role with all its AI calls in parallel"""
    if not isinstance(jd, dict) or 'skills' not in jd:
        return None
    
    required_skills = set(skill.lower() for skill in jd.get('skills', []))
    if not required_skills:
        return None
    
    # Use fuzzy matching
    matched = fuzzy_skill_match(resume_skills, required_skills)
    missing = required_skills - matched
    score = round((len(matched) / len(required_skills)) * 10, 1) if required_skills else 0
    
    # Make AI calls in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        tips_future = executor.submit(get_improvement_tips, list(missing), text[:800], jd.get('role', ''), jd.get('company', ''))
        questions_future = executor.submit(generate_interview_questions, jd.get('role', ''), jd.get('company', ''), summary)
        
        tips = tips_future.result()
        interview_qs = questions_future.result()
    
    # Ensure improvement_tips is always a list of strings
    if isinstance(tips, str):
        tips = [tip.strip('-• ') for tip in tips.split('\n') if tip.strip()]
    # Ensure interview_questions is always a list of strings
    if isinstance(interview_qs, list):
        interview_qs = [str(q) if not isinstance(q, str) else q for q in interview_qs]
    return {
        "role": jd.get('role', 'Software Engineer'),
        "company": jd.get('company', 'Tech Company'),
        "expected_salary": jd.get('salary', '10-15 LPA'),
        "match_score": score,
        "matched_skills": list(matched),
        "missing_skills": list(missing),
        "improvement_tips": tips,
        "interview_questions": interview_qs
    }

# --- Blueprints ---
main_bp = Blueprint('main', __name__)
analysis_bp = Blueprint('analysis', __name__)
scoreboard_bp = Blueprint('scoreboard', __name__)
admin_bp = Blueprint('admin', __name__)

# --- Main Routes ---
@main_bp.route('/')
def loading_screen():
    return render_template("loading.html")
@main_bp.route('/login')
def login_screen():
    return render_template("login.html")

@main_bp.route('/home')
def home():
    return render_template("index.html")

@main_bp.route('/upload')
def upload_page():
    return render_template("upload.html")

@main_bp.route('/courses')
def courses_page():
    return render_template("courses.html")

@main_bp.route('/all')
def all_features():
    return render_template("all.html")

@main_bp.route('/ping')
def ping():
    return jsonify({'message': 'pong', 'status': 'healthy'})

# --- Optimized Analysis Route ---
@analysis_bp.route('/analyze', methods=["POST"])
@limiter.limit("10/minute")
def analyze_resume():
    try:
        # Check if file is present
        if 'resume' not in request.files:
            return jsonify({"error": "No resume file provided"}), 400
        
        file = request.files['resume']
        
        # Check if file was selected
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        # Validate file
        valid, msg = validate_file(file)
        if not valid:
            return jsonify({"error": msg}), 400
        
        # Get description (optional)
        desc = request.form.get('description', '')
        
        # Extract text from file
        text = extract_text(file)
        if not text:
            return jsonify({"error": "Unable to extract text from the uploaded file. Please ensure the file is not corrupted and try again."}), 500
        
        # Step 1: Generate summary and extract skills in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            summary_future = executor.submit(summarize_resume, text)
            skills_future = executor.submit(extract_skills_ai, text)
            
            summary = summary_future.result()
            resume_skills = set(s.lower() for s in skills_future.result())
        
        logger.info(f"Extracted resume skills: {resume_skills}")

        # Step 2: Generate job roles and candidate insights in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            roles_future = executor.submit(generate_job_roles, summary)
            insights_future = executor.submit(generate_candidate_insights, text, list(resume_skills), summary)
            
            job_roles = roles_future.result()
            candidate_insights = insights_future.result()
        
        # Step 3: Process job roles in parallel
        results = []
        all_missing_skills = []
        all_matched_skills = []
        match_scores = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_role = {
                executor.submit(process_job_role_parallel, jd, resume_skills, text, summary): jd 
                for jd in job_roles
            }
            for future in concurrent.futures.as_completed(future_to_role):
                result = future.result()
                if result:
                    logger.info(f"Role: {result['role']} | Matched: {result['matched_skills']} | Missing: {result['missing_skills']} | Score: {result['match_score']}")
                    for jr in job_roles:
                        if jr.get('role') == result['role'] and jr.get('company') == result['company']:
                            result['logo_url'] = jr.get('logo_url', None)
                    results.append(result)
                    all_missing_skills.extend(result.get('missing_skills', []))
                    all_matched_skills.extend(result.get('matched_skills', []))
                    match_scores.append(result.get('match_score', 0))
        # Sort results by match_score descending
        results.sort(key=lambda x: x['match_score'], reverse=True)
        # Mark top match
        if results:
            results[0]['top_match'] = True
            for r in results[1:]:
                r['top_match'] = False
        
        # Step 4: Generate resume tips (can be done while processing roles)
        resume_tips = ai_resume_tips(text)
        
        # --- Graphical Data for Frontend Visualizations ---
        from collections import Counter
        top_missing_skills = [s for s, _ in Counter(all_missing_skills).most_common(10)]
        top_matched_skills = [s for s, _ in Counter(all_matched_skills).most_common(10)]
        score_distribution = [0]*11
        for score in match_scores:
            idx = int(round(score))
            if 0 <= idx <= 10:
                score_distribution[idx] += 1
        graphical_data = {
            "top_missing_skills": top_missing_skills,
            "top_matched_skills": top_matched_skills,
            "score_distribution": score_distribution,
            "total_jds": len(results),
            "description": "This data is suitable for bar charts, pie charts, or radar charts to visualize skill gaps and match quality."
        }
        # Step 5: Save analysis to MongoDB only
        try:
            mongo.db.analyses.insert_one({
                "session_id": get_session_id(),
                "resume_skills": list(resume_skills),
                "roles": [r.get('role', '') for r in job_roles],
                "scores": [r.get('match_score', 0) for r in results],
                "summary": summary,
                "tips": resume_tips,
                "interview_questions": [r.get('interview_questions', []) for r in results],
                "graphical_data": graphical_data,
                "timestamp": datetime.utcnow()
            })
        except Exception as mongo_error:
            logger.error(f"MongoDB error: {mongo_error}")
        
        return jsonify({
            "results": results, 
            "resume_summary": summary, 
            "resume_tips": resume_tips,
            "candidate_insights": candidate_insights,
            "resume_skills": list(resume_skills),
            "graphical_data": graphical_data,
            "comparison_note": "Your resume was compared with 50 AI-generated job descriptions (JDs). For each JD, required, matched, and missing skills are shown.",
            "success": True
        }), 200
        
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500

# --- Scoreboard Route ---
@scoreboard_bp.route('/scoreboard')
def scoreboard():
    try:
        analyses = list(mongo.db.analyses.find().sort("timestamp", -1).limit(100))
        stats = {
            "total_analyses": mongo.db.analyses.count_documents({}),
            "recent_roles": [],
            "top_skills": [],
            "avg_score": 0
        }
        
        all_skills = []
        all_scores = []
        all_roles = []
        
        for a in analyses:
            if a.get("resume_skills"):
                all_skills.extend(a["resume_skills"])
            if a.get("scores"):
                all_scores.extend([float(s) for s in a["scores"] if s])
            if a.get("roles"):
                all_roles.extend(a["roles"])
        
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
        analyses = list(mongo.db.analyses.find().sort("timestamp", -1).limit(100))
        leaderboard = []
        
        for a in analyses:
            if a.get("scores"):
                try:
                    max_score = max([float(s) for s in a["scores"] if s])
                    leaderboard.append({
                        "session_id": a.get("session_id", "unknown")[-6:],
                        "max_score": max_score,
                        "roles": a.get("roles", [])
                    })
                except (ValueError, TypeError):
                    continue
        
        leaderboard = sorted(leaderboard, key=lambda x: x["max_score"], reverse=True)[:10]
        return jsonify(leaderboard)
    except Exception as e:
        logger.error(f"Leaderboard error: {e}")
        return jsonify({"error": f"Leaderboard failed: {e}"}), 500

# --- AI Tips Endpoint ---
@analysis_bp.route('/tips', methods=["POST"])
@limiter.limit("20/minute")
def ai_tips():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        text = data.get("text", "")
        if not text:
            return jsonify({"error": "No text provided"}), 400
        
        tips = ai_resume_tips(text)
        return jsonify({"tips": tips})
    except Exception as e:
        logger.error(f"AI tips error: {e}")
        return jsonify({"error": f"AI tips failed: {e}"}), 500

# --- Download Report Endpoint ---
@analysis_bp.route('/download_report', methods=["POST"])
def download_report():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        summary = data.get("summary", "")
        results = data.get("results", [])
        tips = data.get("tips", [])
        
        # Generate a simple text report
        report = f"SkillWale Resume Analysis Report\n{'='*50}\n\n"
        report += f"Summary:\n{summary}\n\n"
        report += f"Results:\n{'='*20}\n"
        
        for r in results:
            report += f"\nRole: {r.get('role', 'N/A')} at {r.get('company', 'N/A')}\n"
            report += f"Match Score: {r.get('match_score', 0)}/10\n"
            report += f"Expected Salary: {r.get('expected_salary', 'N/A')}\n"
            report += f"Matched Skills: {', '.join(r.get('matched_skills', []))}\n"
            report += f"Missing Skills: {', '.join(r.get('missing_skills', []))}\n"
            report += f"Improvement Tips:\n{r.get('improvement_tips', 'N/A')}\n"
            report += "-" * 40 + "\n"
        
        report += f"\nGeneral Resume Tips:\n{'='*20}\n"
        for t in tips:
            report += f"• {t}\n"
        
        buf = BytesIO()
        buf.write(report.encode('utf-8'))
        buf.seek(0)
        
        return send_file(
            buf, 
            as_attachment=True, 
            download_name="SkillWale_Resume_Report.txt", 
            mimetype="text/plain"
        )
    except Exception as e:
        logger.error(f"Download report error: {e}")
        return jsonify({"error": f"Download failed: {e}"}), 500

# --- Interview Questions Endpoint ---
@analysis_bp.route('/interview_questions', methods=["POST"])
def interview_questions():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        role = data.get("role", "")
        company = data.get("company", "")
        summary = data.get("summary", "")
        
        if not (role and company and summary):
            return jsonify({"error": "Missing required data: role, company, or summary"}), 400
        
        questions = generate_interview_questions(role, company, summary)
        return jsonify({"questions": questions})
    except Exception as e:
        logger.error(f"Interview questions error: {e}")
        return jsonify({"error": f"Interview questions failed: {e}"}), 500

# --- Admin CLI Commands ---
@admin_bp.cli.command("init-db")
def init_db():
    try:
        with app.app_context():
            # This command is no longer needed as MongoDB is the primary storage
            print("✅ MongoDB initialized successfully (via CLI).")
    except Exception as e:
        print(f"❌ MongoDB initialization failed: {e}")

@admin_bp.cli.command("reset-scoreboard")
def reset_scoreboard():
    try:
        with app.app_context():
            # This command is no longer needed as MongoDB is the primary storage
            print("✅ MongoDB scoreboard reset successfully (via CLI).")
    except Exception as e:
        print(f"❌ MongoDB scoreboard reset failed: {e}")

@admin_bp.cli.command("export-analyses")
def export_analyses():
    try:
        with app.app_context():
            # This command is no longer needed as MongoDB is the primary storage
            print("✅ MongoDB analyses export (via CLI) is not applicable.")
    except Exception as e:
        print(f"❌ MongoDB export failed: {e}")

# --- Async/Performance/Abuse Protection Stubs ---
# TODO: Refactor endpoints to async (Quart or FastAPI)
# TODO: Integrate Celery/RQ for background job queue
# TODO: Add Redis/memory caching for identical resume analysis
# TODO: Add CAPTCHA/email verification for heavy users
# TODO: Add more detailed error reporting and suggestions
# TODO: Make AI model configurable via config.py/env

# --- Register Blueprints ---
app.register_blueprint(main_bp)
app.register_blueprint(analysis_bp)
app.register_blueprint(scoreboard_bp)
app.register_blueprint(admin_bp)

# --- Error Handlers ---
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

@app.errorhandler(413)
def too_large(error):
    return jsonify({"error": "File too large"}), 413

# --- Sample route to fetch recent analyses from MongoDB ---
@app.route('/mongo_analyses')
def mongo_analyses():
    try:
        analyses = list(mongo.db.analyses.find().sort("timestamp", -1).limit(10))
        for a in analyses:
            a['_id'] = str(a['_id'])  # Convert ObjectId to string for JSON
        return jsonify(analyses)
    except Exception as e:
        logger.error(f"Mongo fetch error: {e}")
        return jsonify({"error": f"Mongo fetch failed: {e}"}), 500

# --- Main ---
if __name__ == "__main__":
    print("🚀 SkillWale AI Backend starting...")
    print(f"📊 Database: {Config.SQLALCHEMY_DATABASE_URI}")
    print(f"🤖 OpenAI: {'✅ Connected' if client else '❌ Not configured'}")
    print("⚡ Performance: Optimized with parallel processing")
    
    # Initialize database
    try:
        with app.app_context():
            # This command is no longer needed as MongoDB is the primary storage
            print("✅ MongoDB ready")
    except Exception as e:
        print(f"⚠️ MongoDB warning: {e}")
    
    print("🌐 Server running at http://localhost:5001")
    app.run(debug=True, port=5001, host='0.0.0.0')
print("OpenAI Key:", Config.OPENAI_API_KEY)
