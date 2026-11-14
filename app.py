from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify
import sqlite3
from reportlab.pdfgen import canvas
import PyPDF2
import re
import pytesseract
from pdf2image import convert_from_path
from datetime import datetime, timezone
import os
import json
from urllib.request import Request, urlopen
from urllib.parse import urlencode, quote
from urllib.error import HTTPError, URLError
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from google import genai

load_dotenv()



# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY")


# =========================================================
# TESSERACT / POPPLER
# =========================================================

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

POPPLER_PATH = r"C:\poppler-26.02.0\Library\bin"


# =========================================================
# API CONFIGURATION
# =========================================================
#
# IMPORTANT:
# Never put real API keys directly inside this file.
#
# Set them as environment variables:
#
# ONET_API_KEY=your_real_key
# ADZUNA_APP_ID=your_real_id
# ADZUNA_APP_KEY=your_real_key
# ADZUNA_COUNTRY=in
# ADZUNA_LOCATION=Bengaluru
#
# =========================================================

ONET_API_KEY = os.environ.get(
    "ONET_API_KEY",
    ""
).strip()

ADZUNA_APP_ID = os.environ.get(
    "ADZUNA_APP_ID",
    ""
).strip()

ADZUNA_APP_KEY = os.environ.get(
    "ADZUNA_APP_KEY",
    ""
).strip()

ADZUNA_COUNTRY = os.environ.get(
    "ADZUNA_COUNTRY",
    "in"
).strip()

ADZUNA_LOCATION = os.environ.get(
    "ADZUNA_LOCATION",
    "Bengaluru"
).strip()

JOOBLE_API_KEY = os.environ.get(
    "JOOBLE_API_KEY",
    ""
).strip()

JOOBLE_BASE_URL = (
    "https://in.jooble.org/api"
)

GEMINI_API_KEY = os.environ.get(
    "GEMINI_API_KEY",
    ""
).strip()

GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
).strip()
# =========================================================
# API URLS
# =========================================================

ONET_BASE_URL = (
    "https://api-v2.onetcenter.org"
)

ADZUNA_BASE_URL = (
    "https://api.adzuna.com/v1/api"
)


# =========================================================
# DATABASE
# =========================================================

db = sqlite3.connect(
    "resume.db",
    check_same_thread=False
)

cursor = db.cursor()


# =========================================================
# USERS TABLE
# =========================================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT UNIQUE,
    password TEXT
)
""")


# =========================================================
# CANDIDATES TABLE
# =========================================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS candidates(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT,
    phone TEXT,
    education TEXT,
    skills TEXT,
    ats_score INTEGER,
    match_score INTEGER,
    status TEXT,
    github TEXT,
    linkedin TEXT,
    resume_file TEXT,
    upload_date TEXT
)
""")


# =========================================================
# ADD user_id TO OLD DATABASE
# =========================================================

cursor.execute(
    "PRAGMA table_info(candidates)"
)

candidate_columns = [
    row[1]
    for row in cursor.fetchall()
]

if "user_id" not in candidate_columns:

    cursor.execute("""
        ALTER TABLE candidates
        ADD COLUMN user_id INTEGER
    """)

    db.commit()


# =========================================================
# JOB MATCHING TABLE
# =========================================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS job_descriptions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    title TEXT,
    description TEXT,
    created_at TEXT
)
""")


cursor.execute("""
CREATE TABLE IF NOT EXISTS job_matches(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    candidate_id INTEGER,
    job_id INTEGER,
    match_score INTEGER,
    matching_skills TEXT,
    missing_skills TEXT,
    keywords TEXT,
    created_at TEXT
)
""")

# =========================================================
# AI CAREER CHATBOT
# OPEN-ENDED RESUME + CAREER ASSISTANT
# =========================================================


# =========================================================
# GEMINI CONFIGURATION
# =========================================================

GEMINI_API_KEY = os.environ.get(
    "GEMINI_API_KEY",
    ""
).strip()

GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
).strip()


# =========================================================
# GET LATEST RESUME FOR CURRENT USER
# =========================================================

def get_latest_candidate_for_chat(user_id):

    try:

        with sqlite3.connect(
            "resume.db"
        ) as conn:

            conn.row_factory = sqlite3.Row

            candidate = conn.execute(
                """
                SELECT *
                FROM candidates
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    user_id,
                )
            ).fetchone()

        return candidate

    except Exception as e:

        print(
            "Latest candidate error:",
            e
        )

        return None


# =========================================================
# BUILD CURRENT RESUME CONTEXT
# =========================================================

def build_chat_resume_context(candidate):

    if not candidate:

        return (
            "The user has not uploaded a resume yet."
        )


    resume_text = ""


    # -----------------------------------------------------
    # READ THE ACTUAL LATEST RESUME FILE
    # -----------------------------------------------------

    try:

        resume_file = candidate["resume_file"]


        if resume_file:

            upload_folder = app.config.get(
                "UPLOAD_FOLDER",
                "uploads"
            )


            filepath = os.path.join(
                upload_folder,
                resume_file
            )


            print(
                "CHATBOT RESUME FILE:",
                filepath
            )


            if os.path.exists(filepath):

                resume_text = extract_resume_text(
                    filepath
                )

            else:

                print(
                    "CHATBOT RESUME NOT FOUND:",
                    filepath
                )

    except Exception as e:

        print(
            "Chatbot resume extraction error:",
            e
        )


    # -----------------------------------------------------
    # DATABASE INFORMATION
    # -----------------------------------------------------

    def value_or_not_available(
        value
    ):

        if value is None:
            return "Not available"

        value = str(value).strip()

        if not value:
            return "Not available"

        return value


    name = value_or_not_available(
        candidate["name"]
    )

    email = value_or_not_available(
        candidate["email"]
    )

    phone = value_or_not_available(
        candidate["phone"]
    )

    education = value_or_not_available(
        candidate["education"]
    )

    skills = value_or_not_available(
        candidate["skills"]
    )

    github = value_or_not_available(
        candidate["github"]
    )

    linkedin = value_or_not_available(
        candidate["linkedin"]
    )

    ats_score = value_or_not_available(
        candidate["ats_score"]
    )


    # -----------------------------------------------------
    # COMPLETE CONTEXT
    # -----------------------------------------------------

    context = f"""
=========================================================
CURRENT USER RESUME
=========================================================

IMPORTANT:

This is the resume belonging to the CURRENT LOGGED-IN USER.

The resume text below is the PRIMARY SOURCE OF TRUTH for
questions about the user's resume.

Never invent resume facts.

Never invent:

- projects
- internships
- companies
- job titles
- degrees
- certifications
- skills
- achievements
- technologies
- experience
- dates
- responsibilities

If something is not present in the resume, say:

"That information is not present in your uploaded resume."

You may give general advice separately when useful.


=========================================================
DATABASE PROFILE
=========================================================

Name:
{name}

Email:
{email}

Phone:
{phone}

Education:
{education}

Detected skills:
{skills}

GitHub:
{github}

LinkedIn:
{linkedin}

ATS score:
{ats_score}%


=========================================================
FULL EXTRACTED RESUME TEXT
=========================================================

{resume_text[:30000]}


=========================================================
END OF CURRENT USER RESUME
=========================================================
"""

    return context


# =========================================================
# GEMINI CHATBOT
# GOOGLE GENAI SDK
# =========================================================

def ask_gemini_chatbot(
    user_question,
    resume_context,
    conversation=None
):

    conversation = conversation or []

    # -----------------------------------------------------
    # BUILD RECENT CONVERSATION
    # -----------------------------------------------------

    conversation_text = ""

    for item in conversation[-10:]:

        role = item.get(
            "role",
            ""
        )

        message = item.get(
            "message",
            ""
        )

        if role and message:

            conversation_text += (
                role.upper()
                + ": "
                + message
                + "\n\n"
            )

    if not conversation_text:

        conversation_text = (
            "No previous conversation."
        )

    # -----------------------------------------------------
    # PROMPT
    # -----------------------------------------------------

    prompt = f"""
You are an AI Career Assistant inside a Resume Analysis
and Career Assistant application.

Your job is to help the CURRENT USER with:

- Resume questions
- Projects
- Skills
- Education
- Internships
- Experience
- Certifications
- Career guidance
- Job preparation
- Interview preparation
- Skill improvement
- Learning roadmaps
- Resume improvement
- General career questions

=========================================================
IMPORTANT RESUME RULE
=========================================================

The resume context below belongs to the CURRENT USER.

Use the resume as the primary source whenever the user
asks about their own resume, projects, skills, education,
internships, experience, certifications or career profile.

Never invent resume information.

If something is not present in the resume, clearly say
that it is not mentioned in the resume.

=========================================================
ANSWER STYLE
=========================================================

Be:

- Professional
- Friendly
- Clear
- Practical
- Concise but useful

For simple questions, give a simple answer.

For detailed questions, give a properly structured answer.

Use bullet points or headings when useful.

Do not start every response with:
"According to your resume..."

Only mention the resume when relevant.

=========================================================
CONVERSATION MEMORY
=========================================================

Use the recent conversation to understand follow-up
questions.

For example:

USER:
What projects do I have?

ASSISTANT:
[projects]

USER:
Which one should I learn first?

Understand that "which one" refers to the projects
discussed immediately before.

=========================================================
SAFETY / ACCURACY
=========================================================

Do not guarantee:

- Employment
- Interview selection
- Salary
- Promotion
- Admission
- Job placement

Give realistic guidance instead.

Do not pretend to know information that is not provided.

=========================================================
CURRENT USER RESUME
=========================================================

{resume_context}

=========================================================
RECENT CONVERSATION
=========================================================

{conversation_text}

=========================================================
CURRENT USER QUESTION
=========================================================

{user_question}

=========================================================
FINAL INSTRUCTION
=========================================================

Answer the CURRENT USER QUESTION directly.

Do not unnecessarily repeat the resume.

Do not ask unnecessary clarification questions.

If the question is about the user's resume, use the
provided resume information.

If it is a general career question, answer it normally
using your career knowledge.
"""

    # -----------------------------------------------------
    # GEMINI CLIENT
    # -----------------------------------------------------

    try:

        if not GEMINI_API_KEY:

            print("=================================================")
            print("GEMINI ERROR")
            print("GEMINI_API_KEY is missing")
            print("=================================================")

            return None

        client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        models_to_try = [
            GEMINI_MODEL,
            "gemini-3.5-flash-lite"
        ]

        response = None
        last_error = None

        for model_name in models_to_try:

            try:

                print(
                    "Trying Gemini model:",
                    model_name
                )

                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )

                if response:
                    print(
                    "Gemini response received from:",
                    model_name
                )
                break

            except Exception as e:

                last_error = e

                print(
                    "Gemini model failed:",
                     model_name
                )

                print(
                    "Error:",
                    repr(e)
                )

                continue


        if response is None:

            print(
                "================================================="
            )

            print(
                "ALL GEMINI MODELS FAILED"
            )

            print(
                "LAST ERROR:",
                repr(last_error)
            )

            print(
                "================================================="
            )

            return None


        answer = getattr(
            response,
            "text",
            ""
        )

        if not answer:

            print("=================================================")
            print("GEMINI ERROR")
            print("Gemini returned an empty response")
            print("MODEL:", GEMINI_MODEL)
            print("=================================================")

            return None

        return answer.strip()

    except Exception as e:

        print("=================================================")
        print("GEMINI SDK ERROR")
        print("MODEL:", GEMINI_MODEL)
        print("ERROR:", repr(e))
        print("=================================================")

        return None


# =========================================================
# CHATBOT SERVICE ERROR
# =========================================================

def chatbot_service_error():

    if not GEMINI_API_KEY:

        return (
            "The AI chatbot is not configured yet. "
            "Please check GEMINI_API_KEY in your .env file."
        )


    return (
        "I couldn't connect to the AI service right now. "
        "Please try again in a moment. "
        "If the problem continues, check the Flask terminal "
        "for the Gemini API error."
    )


# =========================================================
# CHATBOT PAGE
# =========================================================

@app.route(
    "/chatbot",
    methods=["GET"]
)
def chatbot():

    if not login_required():

        return redirect(
            url_for("login")
        )


    user_id = session[
        "user_id"
    ]


    candidate = (
        get_latest_candidate_for_chat(
            user_id
        )
    )


    # IMPORTANT:
    # Do NOT load old chat history.
    #
    # The browser starts with a fresh conversation.
    #

    return render_template(
        "chatbot.html",
        candidate=candidate
    )


# =========================================================
# CHATBOT API
# =========================================================

@app.route(
    "/api/chat",
    methods=["POST"]
)
def chatbot_api():

    if not login_required():

        return jsonify({

            "success": False,

            "message":
                "Please login first."

        }), 401


    data = request.get_json(
        silent=True
    ) or {}


    user_question = str(
        data.get(
            "message",
            ""
        )
    ).strip()


    if not user_question:

        return jsonify({

            "success": False,

            "message":
                "Please enter a question."

        }), 400


    # -----------------------------------------------------
    # QUESTION SIZE LIMIT
    # -----------------------------------------------------

    if len(user_question) > 6000:

        return jsonify({

            "success": False,

            "message":
                "Please keep your question below "
                "6000 characters."

        }), 400


    # -----------------------------------------------------
    # CURRENT USER
    # -----------------------------------------------------

    user_id = session[
        "user_id"
    ]


    # -----------------------------------------------------
    # ALWAYS GET LATEST RESUME
    # -----------------------------------------------------

    candidate = (
        get_latest_candidate_for_chat(
            user_id
        )
    )


    # -----------------------------------------------------
    # GET BROWSER CONVERSATION
    #
    # IMPORTANT:
    # We DO NOT read old chat_history here.
    # -----------------------------------------------------

    conversation_data = (
        data.get(
            "conversation",
            []
        )
    )


    if not isinstance(
        conversation_data,
        list
    ):

        conversation_data = []


    conversation = []


    for item in conversation_data[-10:]:

        if not isinstance(
            item,
            dict
        ):
            continue


        role = str(
            item.get(
                "role",
                ""
            )
        ).strip()


        message = str(
            item.get(
                "message",
                ""
            )
        ).strip()


        if not message:
            continue


        if role not in {
            "user",
            "assistant"
        }:
            continue


        # Prevent huge conversation payloads.

        message = message[:4000]


        conversation.append({

            "role":
                role,

            "message":
                message

        })


    # -----------------------------------------------------
    # BUILD CURRENT RESUME CONTEXT
    # -----------------------------------------------------

    resume_context = (
        build_chat_resume_context(
            candidate
        )
    )


    # -----------------------------------------------------
    # ASK GEMINI
    # -----------------------------------------------------

    answer = (
        ask_gemini_chatbot(

            user_question,

            resume_context,

            conversation

        )
    )


    # -----------------------------------------------------
    # GEMINI FAILED
    # -----------------------------------------------------

    if not answer:

        return jsonify({

            "success": False,

            "message":
                chatbot_service_error()

        }), 503


    # -----------------------------------------------------
    # OPTIONAL DATABASE LOG
    #
    # We save messages for record keeping,
    # but NEVER use these records to build the
    # current chatbot conversation.
    # -----------------------------------------------------

    try:

        candidate_id = None


        if candidate:

            candidate_id = candidate[
                "id"
            ]


        now = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )


        with sqlite3.connect(
            "resume.db"
        ) as conn:

            conn.execute(
                """
                INSERT INTO chat_history
                (
                    user_id,
                    candidate_id,
                    role,
                    message,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    candidate_id,
                    "user",
                    user_question,
                    now
                )
            )


            conn.execute(
                """
                INSERT INTO chat_history
                (
                    user_id,
                    candidate_id,
                    role,
                    message,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    candidate_id,
                    "assistant",
                    answer,
                    now
                )
            )


            conn.commit()


    except Exception as e:

        print(
            "Chat history save error:",
            e
        )


    # -----------------------------------------------------
    # RETURN ANSWER
    # -----------------------------------------------------

    return jsonify({

        "success": True,

        "message": answer

    })


# =========================================================
# CLEAR CHAT HISTORY
# =========================================================

@app.route(
    "/api/chat/clear",
    methods=["POST"]
)
def clear_chat_history():

    if not login_required():

        return jsonify({

            "success": False,

            "message":
                "Please login first."

        }), 401


    user_id = session[
        "user_id"
    ]


    try:

        with sqlite3.connect(
            "resume.db"
        ) as conn:

            conn.execute(
                """
                DELETE FROM chat_history
                WHERE user_id = ?
                """,
                (
                    user_id,
                )
            )

            conn.commit()


        return jsonify({

            "success": True

        })


    except Exception as e:

        print(
            "Clear chat history error:",
            e
        )


        return jsonify({

            "success": False,

            "message":
                "Could not clear chat history."

        }), 500


# =========================================================
# AUTHENTICATION HELPER
# =========================================================

def login_required():

    return session.get("user_id") is not None


# =========================================================
# RESUME SKILL LIST
# =========================================================

SKILL_LIST = [

    # Programming Languages

    "python",
    "java",
    "c",
    "c++",
    "c#",
    "javascript",
    "typescript",
    "php",
    "go",
    "ruby",
    "swift",
    "kotlin",
    "rust",
    "matlab",
    "verilog",
    "systemverilog",
    "vhdl",
    "assembly",
    "embedded c",

    # Engineering / CAD / Automation
    "cad",
    "autocad",
    "solidworks",
    "catia",
    "creo",
    "ansys",
    "abaqus",
    "simulink",
    "plc",
    "scada",
    "control systems",
    "circuit design",
    "electrical design",
    "electronics",
    "power systems",
    "pcb design",
    "proteus",
    "multisim",
    "structural analysis",
    "finite element analysis",
    "revit",
    "staad pro",
    "etabs",
    "civil 3d",
    "surveying",
    "thermodynamics",
    "fluid mechanics",
    "manufacturing",
    "cnc",
    "3d printing",
    "cam",
    "quality assurance",
    "software testing",
    "selenium",
    "postman",
    "test automation",
    "networking",
    "tcp/ip",
    "dns",
    "computer networks",
    "data structures",
    "algorithms",
    "object oriented programming",
    "etl",
    "apache spark",
    "airflow",

    # Web Development

    "html",
    "css",
    "bootstrap",
    "tailwind",
    "react",
    "angular",
    "vue",
    "node.js",
    "express",
    "flask",
    "django",
    "fastapi",

    # Database

    "sql",
    "mysql",
    "postgresql",
    "sqlite",
    "mongodb",
    "oracle",
    "firebase",
    "redis",

    # AI / ML

    "machine learning",
    "deep learning",
    "artificial intelligence",
    "tensorflow",
    "keras",
    "pytorch",
    "scikit-learn",
    "opencv",
    "nlp",
    "computer vision",
    "cnn",
    "rnn",
    "transformer",
    "llm",
    "generative ai",
    "natural language processing",
    "reinforcement learning",

    # Data Science

    "numpy",
    "pandas",
    "matplotlib",
    "seaborn",
    "plotly",
    "power bi",
    "tableau",
    "excel",
    "statistics",
    "data analysis",
    "data visualization",

    # Cloud / DevOps

    "aws",
    "azure",
    "gcp",
    "docker",
    "kubernetes",
    "linux",
    "git",
    "github",
    "gitlab",
    "jenkins",
    "terraform",
    "ci/cd",

    # APIs

    "rest api",
    "graphql",
    "json",
    "xml",

    # Embedded / Electronics

    "microcontroller",
    "microcontrollers",
    "microprocessor",
    "arm",
    "arm cortex",
    "rtos",
    "freeRTOS",
    "uart",
    "spi",
    "i2c",
    "gpio",
    "can bus",
    "embedded linux",
    "firmware",
    "pcb",
    "fpga",
    "asic",
    "rtl",
    "digital logic",
    "vlsi",
    "system on chip",
    "soc",

        # SAP / ERP / Enterprise Systems

    "sap",
    "sap mm",
    "sap abap",
    "abap",
    "sap s/4hana",
    "sap ecc",
    "sap gui",
    "ddic",
    "alv",
    "ricef",
    "bdc",
    "smartforms",
    "function modules",
    "user exits",
    "bapis",
    "p2p",
    "procure-to-pay",
    "rfq",
    "migo",
    "miro",
    "special procurement",
    "outline agreements",
    "inventory management",
    "master data",
    "source lists",
    "source determination",
    "vendor management",
    "google sheets",
    "powerpoint",
    "word",
    "vs code",
    
    # Security

    "cybersecurity",
    "network security",
    "ethical hacking",
    "penetration testing",
    "cryptography",
    "firewall",
    "siem",

    # Robotics / IoT

    "robotics",
    "ros",
    "ros2",
    "iot",
    "internet of things",
    "sensors",
    "actuators",
    "arduino",
    "raspberry pi",

    # Soft Skills

    "communication",
    "leadership",
    "teamwork",
    "problem solving",
    "critical thinking",
    "time management",
    "adaptability"
]


# =========================================================
# ROLE KNOWLEDGE / ENGINEERING HINTS
# =========================================================
#
# This is NOT a fixed list of allowed jobs.
#
# These hints improve technical-role understanding.
# Unknown roles can still go through O*NET when the API
# key is available.
#
# =========================================================

ROLE_HINTS = {

    "ai/ml": [
        "python",
        "machine learning",
        "deep learning",
        "numpy",
        "pandas",
        "scikit-learn",
        "pytorch",
        "tensorflow",
        "sql",
        "statistics",
        "git"
    ],

    "ai engineer": [
        "python",
        "machine learning",
        "deep learning",
        "llm",
        "generative ai",
        "transformer",
        "pytorch",
        "tensorflow",
        "rest api",
        "git",
        "docker"
    ],

    "machine learning engineer": [
        "python",
        "machine learning",
        "deep learning",
        "scikit-learn",
        "pytorch",
        "tensorflow",
        "numpy",
        "pandas",
        "sql",
        "docker",
        "git"
    ],

    "data scientist": [
        "python",
        "statistics",
        "machine learning",
        "sql",
        "pandas",
        "numpy",
        "scikit-learn",
        "data analysis",
        "data visualization",
        "matplotlib",
        "power bi"
    ],

    "data engineer": [
        "python",
        "sql",
        "etl",
        "data pipelines",
        "spark",
        "pandas",
        "aws",
        "azure",
        "gcp",
        "docker",
        "airflow"
    ],

    "python developer": [
        "python",
        "flask",
        "django",
        "fastapi",
        "sql",
        "rest api",
        "git",
        "docker",
        "html",
        "css",
        "javascript"
    ],

    "software engineer": [
        "python",
        "java",
        "c++",
        "javascript",
        "data structures",
        "algorithms",
        "sql",
        "git",
        "rest api",
        "object oriented programming"
    ],

    "software developer": [
        "python",
        "java",
        "c++",
        "javascript",
        "data structures",
        "algorithms",
        "sql",
        "git",
        "rest api",
        "object oriented programming"
    ],

    "application developer": [
        "python",
        "java",
        "javascript",
        "sql",
        "rest api",
        "git",
        "object oriented programming"
    ],

    "full stack developer": [
        "html",
        "css",
        "javascript",
        "react",
        "node.js",
        "sql",
        "rest api",
        "git"
    ],

    "full-stack developer": [
        "html",
        "css",
        "javascript",
        "react",
        "node.js",
        "sql",
        "rest api",
        "git"
    ],

    "web developer": [
        "html",
        "css",
        "javascript",
        "sql",
        "rest api",
        "git"
    ],

    "frontend developer": [
        "html",
        "css",
        "javascript",
        "react",
        "typescript",
        "git"
    ],

    "backend developer": [
        "python",
        "java",
        "node.js",
        "flask",
        "django",
        "fastapi",
        "sql",
        "rest api",
        "git",
        "docker"
    ],

    "data analyst": [
        "python",
        "sql",
        "excel",
        "statistics",
        "data analysis",
        "data visualization",
        "pandas",
        "power bi",
        "tableau"
    ],

    "business analyst": [
        "sql",
        "excel",
        "data analysis",
        "data visualization",
        "statistics",
        "communication"
    ],

    "qa engineer": [
        "software testing",
        "test automation",
        "selenium",
        "postman",
        "python",
        "java",
        "sql",
        "git"
    ],

    "test engineer": [
        "software testing",
        "test automation",
        "selenium",
        "postman",
        "python",
        "java",
        "sql"
    ],

    "automation test engineer": [
        "software testing",
        "test automation",
        "selenium",
        "python",
        "java",
        "postman",
        "git"
    ],

    "network engineer": [
        "computer networks",
        "networking",
        "tcp/ip",
        "dns",
        "linux",
        "network security"
    ],

    "database administrator": [
        "sql",
        "mysql",
        "postgresql",
        "oracle",
        "mongodb",
        "linux",
        "backup",
        "database"
    ],

    "database engineer": [
        "sql",
        "mysql",
        "postgresql",
        "mongodb",
        "python",
        "data engineering",
        "etl"
    ],

    "systems engineer": [
        "linux",
        "python",
        "networking",
        "computer networks",
        "git",
        "sql"
    ],

    "cloud developer": [
        "python",
        "aws",
        "azure",
        "gcp",
        "docker",
        "rest api",
        "git"
    ],

    "site reliability engineer": [
        "linux",
        "docker",
        "kubernetes",
        "aws",
        "gcp",
        "azure",
        "python",
        "ci/cd",
        "git"
    ],

    "sre": [
        "linux",
        "docker",
        "kubernetes",
        "aws",
        "python",
        "ci/cd",
        "git"
    ],

    "electronics engineer": [
        "electronics",
        "circuit design",
        "pcb design",
        "microcontroller",
        "embedded c",
        "matlab",
        "verilog"
    ],

    "electrical engineer": [
        "electrical design",
        "power systems",
        "control systems",
        "matlab",
        "simulink",
        "plc",
        "scada"
    ],

    "mechanical engineer": [
        "cad",
        "autocad",
        "solidworks",
        "catia",
        "ansys",
        "thermodynamics",
        "manufacturing"
    ],

    "civil engineer": [
        "autocad",
        "revit",
        "staad pro",
        "etabs",
        "structural analysis",
        "civil 3d",
        "surveying"
    ],

    "structural engineer": [
        "autocad",
        "revit",
        "staad pro",
        "etabs",
        "structural analysis",
        "finite element analysis"
    ],

    "chemical engineer": [
        "thermodynamics",
        "fluid mechanics",
        "process engineering",
        "process control",
        "matlab"
    ],

    "biomedical engineer": [
        "matlab",
        "python",
        "electronics",
        "signal processing",
        "biomedical"
    ],

    "aerospace engineer": [
        "matlab",
        "simulink",
        "cad",
        "ansys",
        "fluid mechanics",
        "control systems"
    ],

    "automotive engineer": [
        "cad",
        "solidworks",
        "catia",
        "ansys",
        "automotive",
        "control systems",
        "embedded c"
    ],

    "mechatronics engineer": [
        "cad",
        "matlab",
        "simulink",
        "plc",
        "robotics",
        "control systems",
        "microcontroller"
    ],

    "industrial engineer": [
        "excel",
        "data analysis",
        "statistics",
        "manufacturing",
        "quality assurance",
        "problem solving"
    ],

    "manufacturing engineer": [
        "cad",
        "cam",
        "cnc",
        "manufacturing",
        "solidworks",
        "quality assurance"
    ],

    "computer vision": [
        "python",
        "opencv",
        "computer vision",
        "deep learning",
        "machine learning",
        "cnn",
        "pytorch",
        "tensorflow",
        "numpy",
        "image processing"
    ],

    "nlp": [
        "python",
        "nlp",
        "natural language processing",
        "transformer",
        "llm",
        "machine learning",
        "deep learning",
        "pytorch",
        "tensorflow"
    ],

    "embedded": [
        "c",
        "c++",
        "embedded c",
        "microcontroller",
        "arm",
        "rtos",
        "uart",
        "spi",
        "i2c",
        "gpio",
        "firmware",
        "embedded linux",
        "debugging"
    ],

    "embedded systems": [
        "c",
        "c++",
        "embedded c",
        "microcontroller",
        "arm",
        "rtos",
        "uart",
        "spi",
        "i2c",
        "gpio",
        "firmware",
        "embedded linux"
    ],

    "firmware": [
        "c",
        "c++",
        "embedded c",
        "microcontroller",
        "arm",
        "rtos",
        "uart",
        "spi",
        "i2c",
        "gpio",
        "firmware",
        "debugging"
    ],

    "vlsi": [
        "digital logic",
        "verilog",
        "systemverilog",
        "vhdl",
        "rtl",
        "asic",
        "fpga",
        "cmos",
        "static timing analysis",
        "sta",
        "uvm"
    ],

    "vlsi design": [
        "digital logic",
        "verilog",
        "systemverilog",
        "vhdl",
        "rtl",
        "asic",
        "fpga",
        "cmos",
        "static timing analysis",
        "sta"
    ],

    "verification engineer": [
        "verilog",
        "systemverilog",
        "uvm",
        "rtl",
        "digital logic",
        "fpga",
        "asic",
        "verification",
        "debugging"
    ],

    "robotics": [
        "python",
        "c++",
        "robotics",
        "ros",
        "ros2",
        "computer vision",
        "sensors",
        "actuators",
        "embedded systems",
        "control systems"
    ],

    "iot": [
        "python",
        "c",
        "c++",
        "iot",
        "microcontroller",
        "sensors",
        "mqtt",
        "embedded systems",
        "linux",
        "cloud"
    ],

    "cybersecurity": [
        "cybersecurity",
        "network security",
        "linux",
        "cryptography",
        "ethical hacking",
        "penetration testing",
        "firewall",
        "siem",
        "python"
    ],

    "cloud engineer": [
        "aws",
        "azure",
        "gcp",
        "linux",
        "docker",
        "kubernetes",
        "terraform",
        "ci/cd",
        "python",
        "git"
    ],

    "devops": [
        "linux",
        "docker",
        "kubernetes",
        "jenkins",
        "terraform",
        "aws",
        "azure",
        "gcp",
        "ci/cd",
        "git"
    ],

    "frontend": [
        "html",
        "css",
        "javascript",
        "react",
        "angular",
        "vue",
        "typescript",
        "git"
    ],

    "backend": [
        "python",
        "java",
        "node.js",
        "flask",
        "django",
        "fastapi",
        "sql",
        "rest api",
        "docker",
        "git"
    ]
    
    
}


# =========================================================
# SKILL ALIASES
# =========================================================
#
# Helps avoid simplistic exact-string matching.
#
# =========================================================

SKILL_ALIASES = {

    "machine learning": [
        "machine learning",
        "machine-learning",
        "ml"
    ],

    "deep learning": [
        "deep learning",
        "deep-learning"
    ],

    "computer vision": [
        "computer vision",
        "computer-vision",
        "cv"
    ],

    "natural language processing": [
        "natural language processing",
        "nlp"
    ],

    "python": [
        "python",
        "python3"
    ],

    "c++": [
        "c++",
        "cpp"
    ],

    "embedded c": [
        "embedded c",
        "embedded-c"
    ],

    "microcontroller": [
        "microcontroller",
        "microcontrollers",
        "mcu"
    ],

    "rtos": [
        "rtos",
        "real time operating system",
        "real-time operating system"
    ],

    "uart": [
        "uart",
        "universal asynchronous receiver transmitter"
    ],

    "spi": [
        "spi",
        "serial peripheral interface"
    ],

    "i2c": [
        "i2c",
        "i²c",
        "inter-integrated circuit"
    ],

    "gpio": [
        "gpio",
        "general purpose input output"
    ],

    "verilog": [
        "verilog"
    ],

    "systemverilog": [
        "systemverilog",
        "system verilog"
    ],

    "static timing analysis": [
        "static timing analysis",
        "sta"
    ],

    "rest api": [
        "rest api",
        "restful api",
        "rest"
    ],

    "generative ai": [
        "generative ai",
        "gen ai",
        "genai"
    ],

    "large language models": [
        "large language model",
        "large language models",
        "llm",
        "llms"
    ],

    "data structures": [
        "data structures",
        "data structure",
        "dsa"
    ],

    "algorithms": [
        "algorithms",
        "algorithm",
        "dsa"
    ],

    "object oriented programming": [
        "object oriented programming",
        "object-oriented programming",
        "oops",
        "oop"
    ],

    "software testing": [
        "software testing",
        "software test",
        "testing",
        "qa testing"
    ],

    "test automation": [
        "test automation",
        "automation testing",
        "automated testing"
    ],

    "apache spark": [
        "apache spark",
        "spark"
    ],

    "tcp/ip": [
        "tcp/ip",
        "tcp ip",
        "tcp",
        "ip"
    ]
}


# =========================================================
# GENERIC PROJECT TEMPLATES
# =========================================================

GENERIC_PROJECTS = [

    {
        "title": "Role-Focused Portfolio Project",
        "description": (
            "Build a practical project that directly demonstrates "
            "skills required for the target role."
        ),
        "focus": "Portfolio"
    },

    {
        "title": "End-to-End Application",
        "description": (
            "Build a complete project with a clear problem statement, "
            "implementation, testing and documentation."
        ),
        "focus": "Practical Development"
    },

    {
        "title": "Real-World Problem Project",
        "description": (
            "Choose a real-world problem related to the target role "
            "and demonstrate your technical approach and results."
        ),
        "focus": "Real-World Experience"
    }
]


# =========================================================
# GENERIC LEARNING
# =========================================================

GENERIC_LEARNING = [

    {
        "title": "Role-Specific Technical Skills",
        "description": (
            "Build the technical skills most relevant to the "
            "target occupation."
        )
    },

    {
        "title": "Practical Experience",
        "description": (
            "Build projects that demonstrate the skills employers "
            "commonly request."
        )
    },

    {
        "title": "Technical Communication",
        "description": (
            "Practice explaining technical decisions, projects "
            "and results clearly."
        )
    }
]


# =========================================================
# HTTP JSON HELPER
# =========================================================

def http_get_json(
    url,
    headers=None,
    timeout=12
):

    try:

        request = Request(
            url,
            headers=headers or {
                "Accept": "application/json"
            },
            method="GET"
        )

        with urlopen(
            request,
            timeout=timeout
        ) as response:

            raw = response.read().decode(
                "utf-8"
            )

            return json.loads(raw)

    except HTTPError as e:

        print(
            "API HTTP error:",
            e.code,
            url
        )

    except URLError as e:

        print(
            "API connection error:",
            e
        )

    except Exception as e:

        print(
            "API error:",
            e
        )

    return None


# =========================================================
# EXTRACT TEXT FROM PDF
# =========================================================

def extract_resume_text(filepath):

    text = ""

    try:

        with open(
            filepath,
            "rb"
        ) as pdf:

            reader = PyPDF2.PdfReader(
                pdf
            )

            for page in reader.pages:

                page_text = page.extract_text()

                if page_text:

                    text += page_text + "\n"

    except Exception as e:

        print(
            "PDF extraction error:",
            e
        )


    # -----------------------------------------------------
    # OCR FALLBACK
    # -----------------------------------------------------

    if text.strip() == "":

        try:

            images = convert_from_path(
                filepath,
                poppler_path=POPPLER_PATH
            )

            for image in images:

                text += pytesseract.image_to_string(
                    image
                )

        except Exception as e:

            print(
                "OCR error:",
                e
            )


    return text


# =========================================================
# NORMALIZE TEXT
# =========================================================

def normalize_text(text):

    text = text.lower()

    text = text.replace(
        "–",
        "-"
    )

    text = text.replace(
        "—",
        "-"
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# =========================================================
# CHECK WHETHER SKILL EXISTS IN TEXT
# =========================================================

def skill_in_text(
    skill,
    text
):

    normalized = normalize_text(
        text
    )

    skill_normalized = normalize_text(
        skill
    )

    aliases = SKILL_ALIASES.get(
        skill_normalized,
        [skill_normalized]
    )

    for alias in aliases:

        alias = normalize_text(
            alias
        )

        if not alias:

            continue

        if re.search(
            r"(?<!\w)"
            + re.escape(alias)
            + r"(?!\w)",
            normalized
        ):

            return True

    return False


# =========================================================
# EXTRACT RESUME SKILLS
# =========================================================

def extract_resume_skills(text):

    skills = []

    for skill in SKILL_LIST:

        if skill_in_text(
            skill,
            text
        ):

            skills.append(
                skill
            )

    return sorted(
        set(skills)
    )

# =========================================================
# FINAL GENERAL-PURPOSE RESUME ANALYZER
# =========================================================

def analyze_resume(
    text,
    name,
    email
):

    # =====================================================
    # BASIC TEXT CLEANING
    # =====================================================

    text = text or ""

    clean_text = text.replace(
        "\x00",
        " "
    )

    clean_text = clean_text.replace(
        "\r\n",
        "\n"
    )

    clean_text = clean_text.replace(
        "\r",
        "\n"
    )

    clean_text = re.sub(
        r"[ \t]+",
        " ",
        clean_text
    )

    clean_text = re.sub(
        r"\n{3,}",
        "\n\n",
        clean_text
    ).strip()

    lower_text = clean_text.lower()

    lines = [
        line.strip()
        for line in clean_text.splitlines()
        if line.strip()
    ]

    # =====================================================
    # SECTION ALIASES
    # =====================================================

    section_aliases = {

        "summary": [
            "summary",
            "professional summary",
            "profile",
            "professional profile",
            "career summary",
            "objective",
            "career objective",
            "about me",
            "about"
        ],

        "education": [
            "education",
            "educational qualification",
            "educational qualifications",
            "academic background",
            "academic qualifications",
            "academics"
        ],

        "skills": [
            "skills",
            "technical skills",
            "technical skill",
            "technical expertise",
            "core skills",
            "key skills",
            "skills & technologies",
            "technical skills & tools",
            "technologies",
            "tools & technologies"
        ],

        "projects": [
    "projects",
    "project",
    "academic projects",
    "academic project",
    "personal projects",
    "personal project",
    "key projects",
    "selected projects",
    "major projects",
    "sap projects",
    "technical projects",
    "professional projects"
],

        "experience": [
            "experience",
            "work experience",
            "professional experience",
            "employment",
            "employment history",
            "work history",
            "professional background"
        ],

        "internship": [
            "internship",
            "internships",
            "internship experience",
            "internship experiences"
        ],

        "certifications": [
            "certifications",
            "certification",
            "certificates",
            "certificate",
            "courses",
            "courses & certifications",
            "certifications & courses"
        ],

       "achievements": [
    "achievements",
    "achievement",
    "accomplishments",
    "accomplishment",
    "awards",
    "awards & achievements",
    "honors",
    "honours"
],

      "leadership": [
    "positions of responsibility",
    "position of responsibility",
    "leadership",
    "leadership experience",
    "leadership & responsibilities",
    "roles & responsibilities",
    "responsibilities"
],  
        
        "hackathons": [
            "hackathons",
            "hackathon"
        ],

        "extracurricular": [
            "extra curricular",
            "extra-curricular",
            "extracurricular",
            "extra curricular activities",
            "extra-curricular activities",
            "activities"
        ]
    }

    # =====================================================
    # HEADING NORMALIZATION
    # =====================================================

    def normalize_heading(line):

        value = str(
            line or ""
        ).strip()

        value = re.sub(
            r"^[•*▪●◦‣»›+]+",
            "",
            value
        ).strip()

        value = re.sub(
            r"^\d+\s*[.)-]\s*",
            "",
            value
        ).strip()

        value = re.sub(
            r"[:\-–—]+$",
            "",
            value
        ).strip()

        value = re.sub(
            r"\s+",
            " ",
            value
        )

        return value.lower()

    # =====================================================
    # SECTION NAME DETECTION
    # =====================================================

    all_heading_names = set()

    for values in section_aliases.values():

        for value in values:

            all_heading_names.add(
                normalize_heading(value)
            )

    def heading_matches_section(
        line,
        section_name
    ):

        normalized = normalize_heading(
            line
        )

        wanted = {
            normalize_heading(x)
            for x in section_aliases.get(
                section_name,
                []
            )
        }

        if normalized in wanted:
            return True

        # -------------------------------------------------
        # Combined certification headings
        # Example:
        # CERTIFICATIONS AND EXTRA-CURRICULARS
        # CERTIFICATES & EXTRA CURRICULAR ACTIVITIES
        # -------------------------------------------------

        if section_name == "certifications":

            if (
                "certification" in normalized
                or "certificate" in normalized
            ) and (
                "extra" in normalized
                or "curricular" in normalized
                or "course" in normalized
            ):

                return True

        # -------------------------------------------------
        # Combined achievement headings
        # -------------------------------------------------

        if section_name == "achievements":

            if (
                "achievement" in normalized
                or "award" in normalized
            ):

                return True

        return False

    def is_section_heading(line):

        normalized = normalize_heading(
            line
        )

        if normalized in all_heading_names:

            return True

        # Combined headings

        if (
            (
                "certification" in normalized
                or "certificate" in normalized
            )
            and (
                "extra" in normalized
                or "curricular" in normalized
            )
        ):

            return True

        return False

    # =====================================================
    # GET SECTION
    # =====================================================

    def get_section(
        section_name
    ):

        start_index = None

        for index, line in enumerate(lines):

            if heading_matches_section(
                line,
                section_name
            ):

                start_index = index + 1

                break

        if start_index is None:

            return []

        result = []

        for line in lines[start_index:]:

            if is_section_heading(line):

                break

            result.append(line)

        return result

    # =====================================================
    # BULLET HELPERS
    # =====================================================

    def is_bullet_line(line):

        return bool(
            re.match(
                r"^\s*(?:"
                r"[•*▪●◦‣»›+]"
                r"|\d+\s*[.)]"
                r")\s*",
                line
            )
        )

    def clean_item(line):

        value = str(
            line or ""
        ).strip()

        value = re.sub(
            r"^\s*(?:"
            r"[•*▪●◦‣»›+]"
            r"|\d+\s*[.)]"
            r")\s*",
            "",
            value
        )

        return value.strip()

    # =====================================================
    # DATE-ONLY LINE
    # =====================================================

    def is_date_only(line):

        value = str(
            line or ""
        ).strip().lower()

        patterns = [

            r"^\d{4}\s*[-–—]\s*\d{4}$",

            r"^[a-z]{3,12}\s+\d{4}\s*[-–—]\s*[a-z]{3,12}\s+\d{4}$",

            r"^\d{1,2}[/-]\d{1,2}[/-]\d{4}$",

            r"^\d{4}\s*[-–—]\s*(?:present|current)$",

            r"^[a-z]{3,12}\s+\d{4}\s*[-–—]\s*(?:present|current)$"
        ]

        for pattern in patterns:

            if re.fullmatch(
                pattern,
                value,
                re.IGNORECASE
            ):

                return True

        return False

    # =====================================================
    # INLINE BULLET EXPANSION
    #
    # PDF extraction can sometimes put:
    #
    # • Item 1 • Item 2
    #
    # on the same physical line.
    #
    # This converts them into separate logical lines.
    # =====================================================

    def expand_inline_bullets(
        section_lines
    ):

        expanded = []

        for original_line in section_lines:

            line = str(
                original_line or ""
            ).strip()

            if not line:
                continue

            if re.search(
                r"[•▪●◦‣»›]",
                line
            ):

                parts = re.split(
                    r"\s*[•▪●◦‣»›]\s*",
                    line
                )

                first_part = parts[0].strip()

                if first_part:
                    expanded.append(
                        first_part
                    )

                for part in parts[1:]:

                    part = part.strip()

                    if part:
                        expanded.append(
                            "• " + part
                        )

            else:

                expanded.append(
                    line
                )

        return expanded


    # =====================================================
    # GENERIC BULLET ITEM BUILDER
    # =====================================================

    def build_bullet_items(
        section_lines
    ):

        section_lines = expand_inline_bullets(
            section_lines
        )

        items = []

        current = ""

        for original_line in section_lines:

            line = original_line.strip()

            if not line:
                continue

            if is_date_only(line):
                continue

            starts_new = is_bullet_line(
                line
            )

            cleaned = clean_item(
                line
            )

            if not cleaned:
                continue

            if starts_new:

                if current:

                    items.append(
                        current.strip()
                    )

                current = cleaned

            elif current:

                current += " " + cleaned

            else:

                current = cleaned

        if current:

            items.append(
                current.strip()
            )

        cleaned_items = []

        for item in items:

            item = re.sub(
                r"\s+",
                " ",
                item
            ).strip()

            if len(item) < 3:
                continue

            if item.lower() in {
                "certificate",
                "certificates",
                "certification",
                "certifications",
                "course",
                "courses"
            }:
                continue

            cleaned_items.append(
                item
            )

        return list(
            dict.fromkeys(
                cleaned_items
            )
        )


    # =====================================================
    # ENTRY BUILDER
    #
    # Used for:
    # - Work Experience
    # - Internships
    #
    # One job/internship heading + all its bullets
    # becomes ONE item.
    # =====================================================

    def build_entry_items(
        section_lines
    ):

        section_lines = expand_inline_bullets(
            section_lines
        )

        items = []

        current_parts = []

        entry_keywords = re.compile(
            r"\b("
            r"intern|internship|"
            r"developer|engineer|"
            r"analyst|scientist|"
            r"trainee|manager|"
            r"consultant|associate|"
            r"specialist|"
            r"executive|architect|"
            r"designer|administrator|"
            r"lead"
            r")\b",
            re.IGNORECASE
        )

        for original_line in section_lines:

            line = original_line.strip()

            if not line:
                continue

            if is_date_only(line):
                continue

            starts_bullet = is_bullet_line(
                line
            )

            cleaned = clean_item(
                line
            )

            if not cleaned:
                continue

            # ---------------------------------------------
            # Non-bullet line
            # ---------------------------------------------

            if not starts_bullet:

                looks_like_new_entry = bool(
                    entry_keywords.search(
                        cleaned
                    )
                )

                if (
                    current_parts
                    and looks_like_new_entry
                ):

                    items.append(
                        " ".join(
                            current_parts
                        ).strip()
                    )

                    current_parts = [
                        cleaned
                    ]

                else:

                    current_parts.append(
                        cleaned
                    )

            # ---------------------------------------------
            # Bullet line
            # ---------------------------------------------

            else:

                current_parts.append(
                    cleaned
                )

        if current_parts:

            items.append(
                " ".join(
                    current_parts
                ).strip()
            )

        cleaned_items = []

        for item in items:

            item = re.sub(
                r"\s+",
                " ",
                item
            ).strip()

            if len(item) < 3:
                continue

            cleaned_items.append(
                item
            )

        return list(
            dict.fromkeys(
                cleaned_items
            )
        )[:10]


    # =====================================================
    # PROJECT BUILDER
    #
    # Correctly handles:
    #
    # • Project Title | Technology
    # Description...
    #
    # • Project Title | Technology
    # Description...
    #
    # The title bullet starts a NEW project.
    # Following description lines belong to that project.
    # =====================================================

    def build_project_items(
        section_lines
    ):

        section_lines = expand_inline_bullets(
            section_lines
        )

        projects = []

        current = ""

        for original_line in section_lines:

            line = original_line.strip()

            if not line:
                continue

            if is_date_only(line):
                continue

            starts_bullet = is_bullet_line(
                line
            )

            cleaned = clean_item(
                line
            )

            if not cleaned:
                continue

            # -------------------------------------------------
            # A project title usually contains:
            #
            # Project Name | Technology | Role
            #
            # This is the important rule for SAP-style resumes.
            # -------------------------------------------------

            project_title_signal = (

                starts_bullet

                and (

                    "|" in cleaned

                    or re.search(
                        r"\b("
                        r"project|"
                        r"implementation|"
                        r"configuration|"
                        r"simulation|"
                        r"report|"
                        r"application|"
                        r"system|"
                        r"development"
                        r")\b",
                        cleaned,
                        re.IGNORECASE
                    )
                )

            )

            if project_title_signal:

                if current:

                    projects.append(
                        current.strip()
                    )

                current = cleaned

                continue

            # -------------------------------------------------
            # Normal project description
            # -------------------------------------------------

            if current:

                current += " " + cleaned

            else:

                current = cleaned

        if current:

            projects.append(
                current.strip()
            )

        final_projects = []

        for project in projects:

            project = re.sub(
                r"\s+",
                " ",
                project
            ).strip()

            if len(project) < 3:
                continue

            if is_date_only(project):
                continue

            final_projects.append(
                project
            )

        return list(
            dict.fromkeys(
                final_projects
            )
        )[:10]
    # =====================================================
    # CONTACT INFORMATION
    # =====================================================

    phone_matches = re.findall(
        r"(?<!\d)"
        r"(?:\+91[\s-]?)?"
        r"[6-9]\d{9}"
        r"(?!\d)",
        clean_text
    )

    phone = (
        phone_matches[0]
        if phone_matches
        else ""
    )

    email_matches = re.findall(
        r"[A-Za-z0-9._%+-]+"
        r"@[A-Za-z0-9.-]+"
        r"\.[A-Za-z]{2,}",
        clean_text
    )

    resume_email = (
        email_matches[0]
        if email_matches
        else ""
    )

    if not email:

        email = resume_email

    has_email = bool(
        email_matches
        or (
            email
            and "@" in str(email)
        )
    )

    has_phone = bool(
        phone
    )

    # =====================================================
    # PROFESSIONAL LINKS
    # =====================================================

    profile_patterns = {

        "LinkedIn":
            r"(?:https?://)?"
            r"(?:www\.)?"
            r"linkedin\.com/"
            r"(?:in|pub)/"
            r"[A-Za-z0-9_.-]+",

        "GitHub":
            r"(?:https?://)?"
            r"(?:www\.)?"
            r"github\.com/"
            r"[A-Za-z0-9_.-]+",

        "GitLab":
            r"(?:https?://)?"
            r"(?:www\.)?"
            r"gitlab\.com/"
            r"[A-Za-z0-9_.-]+",

        "Kaggle":
            r"(?:https?://)?"
            r"(?:www\.)?"
            r"kaggle\.com/"
            r"[A-Za-z0-9_.-]+",

        "LeetCode":
            r"(?:https?://)?"
            r"(?:www\.)?"
            r"leetcode\.com/"
            r"[A-Za-z0-9_.-]+",

        "HackerRank":
            r"(?:https?://)?"
            r"(?:www\.)?"
            r"hackerrank\.com/"
            r"[A-Za-z0-9_.-]+",

        "Stack Overflow":
            r"(?:https?://)?"
            r"(?:www\.)?"
            r"stackoverflow\.com/users/"
            r"[A-Za-z0-9_/.-]+"
    }

    professional_links = {}

    for platform, pattern in profile_patterns.items():

        match = re.search(
            pattern,
            clean_text,
            re.IGNORECASE
        )

        if match:

            link = match.group(0)

            if not link.lower().startswith(
                "http"
            ):

                link = (
                    "https://"
                    + link
                )

            professional_links[
                platform
            ] = link

    # Generic portfolio detection.
    # Do not count known email providers.

    portfolio_match = re.search(
        r"(?:https?://)?"
        r"(?:www\.)?"
        r"[A-Za-z0-9_.-]+\."
        r"(?:dev|tech|me|io|site|online)"
        r"(?:/[A-Za-z0-9_./-]*)?",
        clean_text,
        re.IGNORECASE
    )

    if portfolio_match:

        portfolio_link = (
            portfolio_match.group(0)
        )

        blocked_domains = {
            "gmail.com",
            "outlook.com",
            "hotmail.com",
            "yahoo.com"
        }

        domain_match = re.search(
            r"([A-Za-z0-9_.-]+\."
            r"(?:dev|tech|me|io|site|online))",
            portfolio_link,
            re.IGNORECASE
        )

        domain = (
            domain_match.group(1).lower()
            if domain_match
            else ""
        )

        if domain not in blocked_domains:

            if not portfolio_link.lower().startswith(
                "http"
            ):

                portfolio_link = (
                    "https://"
                    + portfolio_link
                )

            professional_links[
                "Portfolio"
            ] = portfolio_link

    professional_presence_score = min(
        len(professional_links) * 20,
        100
    )

    # =====================================================
    # EDUCATION
    # =====================================================

    education_section = get_section(
        "education"
    )

    education_text = ""

    degree_patterns = [

        (
            r"\bb\.?\s*e\.?\b",
            "B.E."
        ),

        (
            r"\bb\.?\s*tech\.?\b",
            "B.Tech"
        ),

        (
            r"\bm\.?\s*e\.?\b",
            "M.E."
        ),

        (
            r"\bm\.?\s*tech\.?\b",
            "M.Tech"
        ),

        (
            r"\bbca\b",
            "BCA"
        ),

        (
            r"\bmca\b",
            "MCA"
        ),

        (
            r"\bb\.?\s*sc\.?\b",
            "B.Sc."
        ),

        (
            r"\bm\.?\s*sc\.?\b",
            "M.Sc."
        ),

        (
            r"\bph\.?\s*d\.?\b",
            "PhD"
        ),

        (
            r"\bdiploma\b",
            "Diploma"
        ),

        (
            r"\bbachelor\b",
            "Bachelor's"
        ),

        (
            r"\bmaster\b",
            "Master's"
        )
    ]

    detected_degrees = []

    education_source = (
        "\n".join(
            education_section
        )
        if education_section
        else clean_text
    )

    for pattern, label in degree_patterns:

        if re.search(
            pattern,
            education_source,
            re.IGNORECASE
        ):

            detected_degrees.append(
                label
            )

    detected_degrees = list(
        dict.fromkeys(
            detected_degrees
        )
    )

    # -----------------------------------------------------
    # Extract useful education lines.
    # -----------------------------------------------------

    education_lines = []

    for line in education_section:

        if is_date_only(line):

            continue

        cleaned = clean_item(
            line
        )

        if len(cleaned) < 3:

            continue

        education_lines.append(
            cleaned
        )

    # Keep only useful lines for UI.

    if education_lines:

        education_text = " | ".join(
            education_lines[:4]
        )

    elif detected_degrees:

        education_text = ", ".join(
            detected_degrees
        )

    else:

        education_text = ""

    has_education = bool(
        education_text
        or detected_degrees
    )

    # =====================================================
    # PROJECTS
    # =====================================================

    project_items = build_project_items(
        get_section(
            "projects"
        )
    )

    # -----------------------------------------------------
    # Fallback project detection
    # -----------------------------------------------------

    if not project_items:

        fallback_projects = []

        for index, line in enumerate(lines):

            if re.match(
                r"^\s*project\s*[:\-–—]",
                line,
                re.IGNORECASE
            ):

                cleaned = re.sub(
                    r"^\s*project\s*[:\-–—]\s*",
                    "",
                    line,
                    flags=re.IGNORECASE
                ).strip()

                if len(cleaned) >= 3:

                    fallback_projects.append(
                        cleaned
                    )

        project_items = fallback_projects

    project_items = list(
        dict.fromkeys(
            project_items
        )
    )[:10]

    has_projects = bool(
        project_items
    )

        # =====================================================
    # WORK EXPERIENCE
    # =====================================================

    experience_items = build_entry_items(
        get_section(
            "experience"
        )
    )

    experience_items = list(
        dict.fromkeys(
            experience_items
        )
    )[:10]

    has_experience = bool(
        experience_items
    )

        # =====================================================
    # INTERNSHIPS
    # =====================================================

    internship_items = build_entry_items(
        get_section(
            "internship"
        )
    )

    # -----------------------------------------------------
    # If there is no dedicated internship section,
    # inspect work-experience entries.
    # -----------------------------------------------------

    if not internship_items:

        for item in experience_items:

            if re.search(
                r"\b("
                r"intern|"
                r"internship|"
                r"interned|"
                r"trainee"
                r")\b",
                item,
                re.IGNORECASE
            ):

                internship_items.append(
                    item
                )

    internship_items = list(
        dict.fromkeys(
            internship_items
        )
    )[:10]

    # -----------------------------------------------------
    # Do not count:
    # Seeking internship
    # Looking for internship
    # Interested in internship
    # as completed experience.
    # -----------------------------------------------------

    completed_internship_items = []

    for item in internship_items:

        if re.search(
            r"\b("
            r"seeking|"
            r"looking\s+for|"
            r"interested\s+in|"
            r"want\s+to|"
            r"aspiring"
            r")\b",
            item,
            re.IGNORECASE
        ):

            continue

        completed_internship_items.append(
            item
        )

    internship_items = (
        completed_internship_items
    )

    has_internship = bool(
        internship_items
    )

        # =====================================================
    # CERTIFICATIONS
    # =====================================================

    certification_section = get_section(
        "certifications"
    )

    certification_items = []

    certification_lines = expand_inline_bullets(
        certification_section
    )

    for original in certification_lines:

        cleaned = clean_item(
            original
        )

        if not cleaned:
            continue

        if is_date_only(
            cleaned
        ):
            continue

        normalized = (
            cleaned
            .lower()
            .strip()
        )

        if normalized in {
            "certificate",
            "certificates",
            "certification",
            "certifications",
            "course",
            "courses"
        }:
            continue

        certification_items.append(
            cleaned
        )

    certification_items = list(
        dict.fromkeys(
            certification_items
        )
    )[:10]

    has_certification = bool(
        certification_items
    )

    # -----------------------------------------------------
    # Fallback certification detection
    # -----------------------------------------------------

    if not certification_items:

        certification_matches = re.findall(
            r"(?:"
            r"certified\s+in|"
            r"certification\s+in|"
            r"certificate\s+in|"
            r"certified|"
            r"certification"
            r")"
            r"\s*[:\-–—]?\s*"
            r"([A-Za-z0-9][^\n]{2,100})",
            clean_text,
            re.IGNORECASE
        )

        for item in certification_matches:

            cleaned = item.strip()

            if cleaned:

                normalized = cleaned.lower()

                if normalized not in {
                    "certificate",
                    "certificates",
                    "certification",
                    "certifications"
                }:

                    certification_items.append(
                        cleaned
                    )

    certification_items = list(
        dict.fromkeys(
            certification_items
        )
    )[:10]

    has_certification = bool(
        certification_items
    )

        # =====================================================
    # ACHIEVEMENTS
    # =====================================================

    achievement_items = build_bullet_items(
        get_section(
            "achievements"
        )
    )

    # =====================================================
    # HACKATHONS
    # =====================================================

    hackathon_items = build_bullet_items(
        get_section(
            "hackathons"
        )
    )

    # =====================================================
    # EXTRA-CURRICULAR
    # =====================================================

    extracurricular_items = build_bullet_items(
        get_section(
            "extracurricular"
        )
    )

    achievement_items = (
        achievement_items
        + hackathon_items
        + extracurricular_items
    )

    achievement_items = list(
        dict.fromkeys(
            achievement_items
        )
    )[:20]

    has_achievements = bool(
        achievement_items
    )

    # =====================================================
    # POSITIONS OF RESPONSIBILITY
    # =====================================================

    leadership_items = build_bullet_items(
        get_section(
            "leadership"
        )
    )

    leadership_items = list(
        dict.fromkeys(
            leadership_items
        )
    )[:20]

    has_leadership = bool(
        leadership_items
    )

    # =====================================================
    # TECHNICAL SKILLS
    #
    # IMPORTANT:
    #
    # First search the actual Skills section.
    #
    # This prevents random words from project descriptions
    # becoming technical skills.
    #
    # If no Skills section exists, use the complete resume
    # as a fallback.
    # =====================================================

    skills_section = get_section(
        "skills"
    )

    skills_source = (
        "\n".join(
            skills_section
        )
        if skills_section
        else clean_text
    )

    # -----------------------------------------------------
    # Soft skills that must NEVER appear as technical skills.
    # -----------------------------------------------------

    soft_skill_names = {

        "communication",
        "leadership",
        "teamwork",
        "team work",
        "problem solving",
        "problem-solving",
        "critical thinking",
        "time management",
        "adaptability",
        "negotiation",
        "negotiator",
        "strategic",
        "strategy",
        "quick learner",
        "quick learning",
        "interpersonal skills",
        "presentation skills",
        "organizational skills",
        "organization skills"
    }

    # -----------------------------------------------------
    # Extra aliases for common resume formatting.
    # -----------------------------------------------------

    local_skill_aliases = {

        "javascript": [
            "javascript",
            "java script",
            "java-script"
        ],

        "typescript": [
            "typescript",
            "type script"
        ],

        "node.js": [
            "node.js",
            "nodejs",
            "node js"
        ],

        "react": [
            "react",
            "reactjs",
            "react.js"
        ],

        "vue": [
            "vue",
            "vuejs",
            "vue.js"
        ],

        "angular": [
            "angular",
            "angularjs"
        ],

        "c++": [
            "c++",
            "cpp"
        ],

        "c#": [
            "c#",
            "c sharp"
        ],

        "machine learning": [
            "machine learning",
            "machine-learning",
            "ml"
        ],

        "deep learning": [
            "deep learning",
            "deep-learning",
            "dl"
        ],

        "artificial intelligence": [
            "artificial intelligence",
            "ai"
        ],

        "computer vision": [
            "computer vision",
            "computer-vision"
        ],

        "natural language processing": [
            "natural language processing",
            "nlp"
        ],

        "scikit-learn": [
            "scikit-learn",
            "sklearn"
        ],

        "power bi": [
            "power bi",
            "powerbi"
        ],

        "rest api": [
            "rest api",
            "restful api"
        ],

        "ci/cd": [
            "ci/cd",
            "ci cd"
        ],

        "github": [
            "github"
        ],

        "gitlab": [
            "gitlab"
        ],

        "microcontroller": [
            "microcontroller",
            "microcontrollers",
            "mcu"
        ],

        "embedded c": [
            "embedded c",
            "embedded-c"
        ],

        "systemverilog": [
            "systemverilog",
            "system verilog"
        ],

        "i2c": [
            "i2c",
            "i²c"
        ],

        "can bus": [
            "can bus",
            "can-bus"
        ],

        "raspberry pi": [
            "raspberry pi",
            "raspberry-pi"
        ]
    }

    def skill_is_present(
        canonical_skill,
        source
    ):

        canonical_lower = (
            canonical_skill
            .lower()
            .strip()
        )

        if canonical_lower in soft_skill_names:

            return False

        aliases = local_skill_aliases.get(
            canonical_lower
        )

        if aliases is None:

            aliases = SKILL_ALIASES.get(
                canonical_lower,
                [canonical_lower]
            )

        for alias in aliases:

            alias = str(
                alias
            ).lower().strip()

            if not alias:

                continue

            # Special handling for single-letter C.

            if alias == "c":

                if re.search(
                    r"(?<![\w+#])"
                    r"c"
                    r"(?![\w+#])",
                    source,
                    re.IGNORECASE
                ):

                    return True

                continue

            if re.search(
                r"(?<!\w)"
                + re.escape(alias)
                + r"(?!\w)",
                source,
                re.IGNORECASE
            ):

                return True

        return False

    skills = []

    # Existing SKILL_LIST contains the technical skills
    # maintained by your application.

    for skill in SKILL_LIST:

        skill_lower = str(
            skill
        ).lower().strip()

        if skill_lower in soft_skill_names:

            continue

        if skill_is_present(
            skill,
            skills_source
        ):

            skills.append(
                skill
            )

    # -----------------------------------------------------
    # Normalize common names.
    # -----------------------------------------------------

    normalized_skill_output = []

    for skill in skills:

        value = str(
            skill
        ).strip()

        lower_value = value.lower()

        if lower_value == "freeRTOS".lower():

            value = "FreeRTOS"

        elif lower_value == "node.js":

            value = "Node.js"

        elif lower_value == "javascript":

            value = "JavaScript"

        elif lower_value == "typescript":

            value = "TypeScript"

        elif lower_value == "c++":

            value = "C++"

        elif lower_value == "c#":

            value = "C#"

        elif lower_value == "html":

            value = "HTML"

        elif lower_value == "css":

            value = "CSS"

        normalized_skill_output.append(
            value
        )

    skills = list(
        dict.fromkeys(
            normalized_skill_output
        )
    )

    # C++ should not produce C as a second skill
    # unless standalone C is actually present.

    if "C++" in skills:

        skills = [
            skill
            for skill in skills
            if skill != "c"
        ]

    skills = sorted(
        skills,
        key=lambda x: x.lower()
    )

    # =====================================================
    # CAREER STAGE
    # =====================================================

    fresher_signal = bool(
        re.search(
            r"\b("
            r"fresher|"
            r"fresh graduate|"
            r"recent graduate|"
            r"student|"
            r"undergraduate|"
            r"final year|"
            r"third year|"
            r"second year|"
            r"first year"
            r")\b",
            lower_text
        )
    )

    internship_completed_signal = bool(
        internship_items
    )

    internship_word_signal = bool(
        re.search(
            r"\b("
            r"internship|"
            r"interned|"
            r"intern\b|"
            r"trainee"
            r")\b",
            lower_text
        )
    )

    experience_year_signal = bool(
        re.search(
            r"\b(?:"
            r"[1-9]|1[0-5]"
            r")\+?\s*"
            r"(?:years?|yrs?)"
            r"\s+(?:of\s+)?"
            r"(?:experience|work)\b",
            lower_text
        )
    )

    professional_title_signal = bool(
        re.search(
            r"\b("
            r"software engineer|"
            r"software developer|"
            r"data scientist|"
            r"data analyst|"
            r"machine learning engineer|"
            r"ml engineer|"
            r"ai engineer|"
            r"web developer|"
            r"backend developer|"
            r"frontend developer|"
            r"full stack developer|"
            r"full-stack developer|"
            r"devops engineer|"
            r"cloud engineer|"
            r"cybersecurity analyst|"
            r"project manager|"
            r"consultant|"
            r"senior|"
            r"lead|"
            r"manager"
            r")\b",
            lower_text
        )
    )

    if has_experience or experience_year_signal:

        career_stage = (
            "Experienced Professional"
        )

    elif internship_completed_signal:

        career_stage = (
            "Internship-focused"
        )

    elif (
        fresher_signal
        or (
            has_education
            and not has_experience
        )
    ):

        career_stage = (
            "Student / Fresher"
        )

    elif professional_title_signal:

        career_stage = (
            "Professional"
        )

    elif internship_word_signal:

        career_stage = (
            "Internship-focused"
        )

    else:

        career_stage = (
            "Early Career"
        )

    # =====================================================
    # CONTENT SIGNALS
    # =====================================================

    action_words = [

        "developed",
        "built",
        "created",
        "designed",
        "implemented",
        "optimized",
        "automated",
        "analyzed",
        "managed",
        "led",
        "improved",
        "engineered",
        "deployed",
        "tested",
        "integrated",
        "programmed",
        "configured",
        "delivered",
        "maintained",
        "solved"
    ]

    action_word_count = 0

    for word in action_words:

        action_word_count += len(
            re.findall(
                r"\b"
                + re.escape(word)
                + r"\b",
                lower_text
            )
        )

    # -----------------------------------------------------
    # MEASURABLE EVIDENCE
    #
    # Years such as 2024 / 2025 are NOT counted.
    # -----------------------------------------------------

    measurable_patterns = [

        r"\b\d+(?:\.\d+)?\s*%",

        r"\b\d+(?:\.\d+)?\s*percent\b",

        r"\b\d+(?:\.\d+)?\s*"
        r"(?:users?|records?|projects?|"
        r"months?|days?|hours?|"
        r"years?|datasets?|devices?|"
        r"customers?|transactions?|"
        r"requests?|students?|"
        r"models?|images?|samples?)\b",

        r"\b\d+(?:\.\d+)?\s*x\b",

        r"\b\d+(?:\.\d+)?\s*"
        r"(?:k|m)\b"
    ]

    quantified_count = 0

    for pattern in measurable_patterns:

        quantified_count += len(
            re.findall(
                pattern,
                lower_text,
                re.IGNORECASE
            )
        )

    word_count = len(
        re.findall(
            r"\b\w+\b",
            clean_text
        )
    )

    # =====================================================
    # SKILL STRENGTH
    # =====================================================

    skill_count = len(
        skills
    )

    if skill_count == 0:

        skill_strength = 0

    elif skill_count < 5:

        skill_strength = (
            50
            + skill_count * 6
        )

    elif skill_count < 10:

        skill_strength = (
            75
            + (
                skill_count - 5
            ) * 4
        )

    else:

        skill_strength = 95

    skill_strength = min(
        skill_strength,
        100
    )

    # =====================================================
    # CONTENT QUALITY
    # =====================================================

    content_quality = 0

    if 150 <= word_count <= 900:

        content_quality += 30

    elif word_count >= 100:

        content_quality += 20

    else:

        content_quality += 5

    if action_word_count >= 8:

        content_quality += 30

    elif action_word_count >= 4:

        content_quality += 20

    elif action_word_count >= 1:

        content_quality += 10

    if quantified_count >= 4:

        content_quality += 25

    elif quantified_count >= 2:

        content_quality += 18

    elif quantified_count >= 1:

        content_quality += 10

    if has_projects:

        content_quality += 10

    if has_experience or has_internship:

        content_quality += 10

    if has_achievements:

        content_quality += 5

    content_quality = min(
        content_quality,
        100
    )

    # =====================================================
    # CONTACT SCORE
    # =====================================================

    contact_score = (

        50
        if has_email
        else 0

    ) + (

        50
        if has_phone
        else 0
    )

    # =====================================================
    # STRUCTURE SCORE
    # =====================================================

    structure_parts = [

        has_education,

        bool(skills),

        has_projects
    ]

    if career_stage == "Student / Fresher":

        # Experience is not required for a fresher.

        structure_parts.append(
            True
        )

    elif career_stage == "Internship-focused":

        structure_parts.append(
            has_internship
            or has_experience
        )

    else:

        structure_parts.append(
            has_experience
        )

    structure_score = int(
        (
            sum(structure_parts)
            /
            len(structure_parts)
        )
        * 100
    )

    # =====================================================
    # RESUME HEALTH
    # =====================================================

    education_health = (
        100
        if has_education
        else 0
    )

    if skill_count >= 5:

        skills_health = 100

    elif skill_count > 0:

        skills_health = 70

    else:

        skills_health = 0

    projects_health = (
        100
        if has_projects
        else 0
    )

    if career_stage == "Student / Fresher":

        experience_health = 100

        experience_status = (
            "Not required for a fresher"
        )

    elif career_stage == "Internship-focused":

        if has_internship:

            experience_health = 100

            experience_status = (
                "Internship experience detected"
            )

        elif has_experience:

            experience_health = 100

            experience_status = (
                "Practical experience detected"
            )

        else:

            experience_health = 60

            experience_status = (
                "No internship or practical experience detected"
            )

    else:

        if has_experience:

            experience_health = 100

            experience_status = (
                "Work experience detected"
            )

        else:

            experience_health = 60

            experience_status = (
                "No work experience detected"
            )

    certification_health = (
        100
        if has_certification
        else 0
    )

    # Certifications are displayed separately.
    # They are optional and do not dominate completeness.

    health_values = [

        contact_score,

        education_health,

        skills_health,

        projects_health,

        experience_health
    ]

    completion_score = int(
        sum(health_values)
        /
        len(health_values)
    )

    # =====================================================
    # GENERAL KEYWORD COVERAGE
    # =====================================================

    keyword_match = min(

        100,

        min(
            skill_count * 8,
            60
        )

        + (
            15
            if has_projects
            else 0
        )

        + (
            15
            if (
                has_experience
                or has_internship
            )
            else 0
        )

        + (
            10
            if has_certification
            else 0
        )
    )

    # =====================================================
    # ATS COMPATIBILITY
    #
    # This is your application's resume-readiness score.
    # It is NOT an employer's actual ATS score.
    # =====================================================

    ats_score = int(

        contact_score * 0.20

        + structure_score * 0.25

        + skill_strength * 0.20

        + content_quality * 0.20

        + keyword_match * 0.15
    )

    ats_score = max(
        0,
        min(
            ats_score,
            100
        )
    )

    # =====================================================
    # OVERALL SCORE
    # =====================================================

    if career_stage == "Student / Fresher":

        overall_score = int(

            ats_score * 0.25

            + skill_strength * 0.25

            + content_quality * 0.20

            + completion_score * 0.15

            + (
                100
                if has_projects
                else 0
            ) * 0.10

            + professional_presence_score * 0.05
        )

    elif career_stage == "Internship-focused":

        overall_score = int(

            ats_score * 0.25

            + skill_strength * 0.20

            + content_quality * 0.20

            + completion_score * 0.10

            + (
                100
                if has_projects
                else 0
            ) * 0.10

            + (
                100
                if has_internship
                else 0
            ) * 0.10

            + professional_presence_score * 0.05
        )

    else:

        overall_score = int(

            ats_score * 0.25

            + skill_strength * 0.20

            + content_quality * 0.20

            + completion_score * 0.10

            + (
                100
                if has_experience
                else 0
            ) * 0.20

            + professional_presence_score * 0.05
        )

    overall_score = max(
        0,
        min(
            overall_score,
            100
        )
    )

    # =====================================================
    # LEGACY DATABASE MATCH SCORE
    #
    # Job Match has its own separate system.
    # This field is kept only so the existing database
    # continues working.
    # =====================================================

    match_score = ats_score

    # =====================================================
    # QUALITY STATUS
    # =====================================================

    if overall_score >= 80:

        quality_status = "Strong"

    elif overall_score >= 60:

        quality_status = "Good"

    elif overall_score >= 40:

        quality_status = "Needs Improvement"

    else:

        quality_status = (
            "Needs Major Improvement"
        )

    # =====================================================
    # LEGACY DATABASE STATUS
    #
    # IMPORTANT:
    # Keep these values because your existing admin /
    # database code expects Selected / Review / Rejected.
    # =====================================================

    if ats_score >= 70:

        status = "Selected"

    elif ats_score >= 50:

        status = "Review"

    else:

        status = "Rejected"

    # =====================================================
    # STRENGTHS
    # =====================================================

    strengths = []

    if has_email and has_phone:

        strengths.append(
            "Complete email and phone contact information is available."
        )

    elif has_email:

        strengths.append(
            "Email contact information is available."
        )

    elif has_phone:

        strengths.append(
            "Phone contact information is available."
        )

    if skill_count >= 5:

        strengths.append(
            f"Good technical skill coverage with "
            f"{skill_count} detected skills."
        )

    elif skills:

        strengths.append(
            f"{skill_count} technical skill(s) were detected."
        )

    if has_projects:

        strengths.append(
            f"{len(project_items)} project(s) were detected."
        )

    if has_experience:

        strengths.append(
            f"{len(experience_items)} work experience "
            f"item(s) were detected."
        )

    if has_internship:

        strengths.append(
            f"{len(internship_items)} internship "
            f"item(s) were detected."
        )

    if has_certification:

        strengths.append(
            f"{len(certification_items)} certification/course "
            f"item(s) were detected."
        )

    if has_achievements:

        strengths.append(
            f"{len(achievement_items)} achievement/hackathon "
            f"item(s) were detected."
        )

    if professional_links:

        strengths.append(
            "Professional profiles detected: "
            + ", ".join(
                professional_links.keys()
            )
            + "."
        )

    if action_word_count >= 4:

        strengths.append(
            "The resume uses action-oriented statements."
        )

    if quantified_count >= 2:

        strengths.append(
            "Measurable results or numeric details were detected."
        )

    if not strengths:

        strengths.append(
            "The resume was successfully parsed and analyzed."
        )

    # =====================================================
    # WEAKNESSES
    # =====================================================

    weaknesses = []

    if not has_email or not has_phone:

        weaknesses.append(
            "Complete contact information should include both email and phone."
        )

    if not has_education:

        weaknesses.append(
            "Education details were not clearly detected."
        )

    if not skills:

        weaknesses.append(
            "No recognized technical skills were detected."
        )

    if not has_projects:

        weaknesses.append(
            "No clearly identifiable project section or project item was detected."
        )

    if (
        career_stage == "Experienced Professional"
        and not has_experience
    ):

        weaknesses.append(
            "Professional work experience was not detected."
        )

    if (
        career_stage == "Internship-focused"
        and not has_internship
        and not has_experience
    ):

        weaknesses.append(
            "No internship or practical experience entry was detected."
        )

    if not professional_links:

        weaknesses.append(
            "No professional profile links were detected."
        )

    if action_word_count < 4:

        weaknesses.append(
            "The resume contains limited action-oriented statements."
        )

    if quantified_count == 0:

        weaknesses.append(
            "No measurable results or numeric achievements were detected."
        )

    if not weaknesses:

        weaknesses.append(
            "No major content gaps were detected."
        )

    # =====================================================
    # SUGGESTIONS
    # =====================================================

    suggestions = []

    if not has_projects:

        suggestions.append(
            "Add 2-3 relevant projects with technologies used, your contribution, and measurable results."
        )

    if career_stage == "Student / Fresher":

        if not has_internship:

            suggestions.append(
                "Internship experience can be added when you gain practical exposure."
            )

    elif career_stage == "Internship-focused":

        if (
            not has_internship
            and not has_experience
        ):

            suggestions.append(
                "Add internship, training, freelance, research, or practical experience when available."
            )

    else:

        if not has_experience:

            suggestions.append(
                "Add relevant work experience, internships, freelance work, or major practical responsibilities when available."
            )

    if not professional_links:

        suggestions.append(
            "Add relevant LinkedIn, GitHub, Kaggle, LeetCode, or portfolio links when applicable."
        )

    if quantified_count == 0:

        suggestions.append(
            "Add measurable evidence such as accuracy, users, performance improvement, dataset size, or time saved."
        )

    if action_word_count < 4:

        suggestions.append(
            "Use action verbs such as developed, implemented, designed, analyzed, optimized, or deployed."
        )

    if skill_count < 5:

        suggestions.append(
            "Add relevant technical skills that genuinely match your target career area."
        )

    if not has_certification:

        suggestions.append(
            "Certifications are optional; add relevant courses or certifications when they strengthen your target profile."
        )

    if not suggestions:

        suggestions.append(
            "Keep the resume updated with recent projects, skills, practical experience, and measurable achievements."
        )

    # =====================================================
    # AI SUMMARY
    # =====================================================

    if has_experience:

        experience_summary = (
            f"{len(experience_items)} work experience item(s) detected."
        )

    elif has_internship:

        experience_summary = (
            f"{len(internship_items)} internship item(s) detected."
        )

    else:

        experience_summary = (
            "No work experience or internship entry detected."
        )

    if has_certification:

        certification_summary = (
            f"{len(certification_items)} certification/course "
            f"item(s) detected."
        )

    else:

        certification_summary = (
            "No certification/course entry clearly detected."
        )

    if has_projects:

        project_summary = (
            f"{len(project_items)} project(s) detected."
        )

    else:

        project_summary = (
            "No clearly identifiable projects detected."
        )

    if professional_links:

        profile_summary = (
            "Professional profiles detected: "
            + ", ".join(
                professional_links.keys()
            )
            + "."
        )

    else:

        profile_summary = (
            "No professional profile links detected."
        )

    ai_summary = (

        f"Resume profile: {career_stage}. "

        f"The resume contains approximately "
        f"{word_count} words and "
        f"{skill_count} detected technical skills. "

        f"The overall resume score is "
        f"{overall_score}%, with ATS compatibility "
        f"at {ats_score}% and content quality "
        f"at {content_quality}%. "

        f"{project_summary} "

        f"{experience_summary} "

        f"{certification_summary} "

        f"{profile_summary}"
    )

    # =====================================================
    # RATING
    # =====================================================

    rating = max(

        1,

        min(

            round(
                overall_score / 20
            ),

            5
        )
    )

    # =====================================================
    # RESUME HEALTH
    # =====================================================

    resume_health = {

        "Contact": {

            "score":
                contact_score,

            "status": (

                "Complete"

                if contact_score == 100

                else
                "Partially available"

                if contact_score > 0

                else
                "Not detected"
            )
        },

        "Education": {

            "score":
                education_health,

            "status": (

                "Education detected"

                if has_education

                else
                "Not detected"
            )
        },

        "Skills": {

            "score":
                skills_health,

            "status": (

                f"{skill_count} technical skill(s) detected"

                if skills

                else
                "Not detected"
            )
        },

        "Projects": {

            "score":
                projects_health,

            "status": (

                f"{len(project_items)} project(s) detected"

                if has_projects

                else
                "Not detected"
            )
        },

        "Experience / Internship": {

            "score":
                experience_health,

            "status":
                experience_status
        },

        "Certifications": {

            "score":
                certification_health,

            "status": (

                f"{len(certification_items)} detected"

                if has_certification

                else
                "Optional - not detected"
            )
        }
    }

    # =====================================================
    # QUALITY SIGNALS
    # =====================================================

    content_signals = {

        "ATS Compatibility":
            ats_score,

        "Technical Skills":
            skill_strength,

        "Content Quality":
            content_quality,

        "Keyword Coverage":
            keyword_match,

        "Resume Completeness":
            completion_score,

        "Professional Presence":
            professional_presence_score
    }

    # =====================================================
    # DETECTED SECTIONS
    # =====================================================

    detected_sections = []

    if get_section("summary"):
        detected_sections.append(
            "Summary"
        )

    if has_education:
        detected_sections.append(
            "Education"
        )

    if skills:
        detected_sections.append(
            "Skills"
        )

    if has_projects:
        detected_sections.append(
            "Projects"
        )

    if has_experience:
        detected_sections.append(
            "Experience"
        )

    if has_internship:
        detected_sections.append(
            "Internship"
        )

    if has_certification:
        detected_sections.append(
            "Certifications"
        )

    if has_achievements:
        detected_sections.append(
            "Achievements"
        )

    if has_leadership:
        detected_sections.append(
            "Positions of Responsibility"
        )
    
    # =====================================================
    # RETURN
    # =====================================================

    return {

        "name":
            name or "",

        "email":
            email or "",

        "phone":
            phone,

        "education":
            education_text,

        "github":
            (
                "Yes"
                if "GitHub"
                in professional_links
                else "No"
            ),

        "linkedin":
            (
                "Yes"
                if "LinkedIn"
                in professional_links
                else "No"
            ),

        "professional_links":
            professional_links,

        "career_stage":
            career_stage,

        "detected_sections":
            detected_sections,

        "text":
            clean_text,

        "skills":
            skills,

        "project_items":
            project_items,

        "experience_items":
            experience_items,

        "internship_items":
            internship_items,

        "certification_items":
            certification_items,

        "achievement_items":
            achievement_items,
            
        "leadership_items":
            leadership_items,

        "ats_score":
            ats_score,

        "overall_score":
            overall_score,

        "match_score":
            match_score,

        "skill_strength":
            skill_strength,

        "keyword_match":
            keyword_match,

        "content_quality":
            content_quality,

        "professional_presence_score":
            professional_presence_score,

        # Used by existing database/admin logic.
        "status":
            status,

        # Used only for the new UI.
        "quality_status":
            quality_status,

        "strengths":
            strengths,

        "weaknesses":
            weaknesses,

        "suggestions":
            suggestions,

        "ai_summary":
            ai_summary,

        "completion_score":
            completion_score,

        "contact_score":
            contact_score,

        "structure_score":
            structure_score,

        "rating":
            rating,

        "word_count":
            word_count,

        "action_word_count":
            action_word_count,

        "quantified_count":
            quantified_count,

        "resume_health":
            resume_health,

        "content_signals":
            content_signals
    }


# =========================================================
# RENDER RESULT PAGE
# =========================================================

def render_resume_result(
    result,
    upload_date
):

    return render_template(

        "result.html",

        name=
            result["name"],

        email=
            result["email"],

        phone=
            result["phone"],

        education=
            result["education"],

        github=
            result["github"],

        linkedin=
            result["linkedin"],

        professional_links=
            result["professional_links"],

        career_stage=
            result["career_stage"],

        quality_status=
            result["quality_status"],

        detected_sections=
            result["detected_sections"],

        project_items=
            result["project_items"],

        experience_items=
            result["experience_items"],

        internship_items=
            result["internship_items"],

        certification_items=
            result["certification_items"],

        achievement_items=
            result["achievement_items"],
            
        leadership_items=
            result["leadership_items"],

        upload_date=
            upload_date,

        text=
            result["text"],

        skills=
            result["skills"],

        ats_score=
            result["ats_score"],

        overall_score=
            result["overall_score"],

        match_score=
            result["match_score"],

        skill_strength=
            result["skill_strength"],

        keyword_match=
            result["keyword_match"],

        content_quality=
            result["content_quality"],

        professional_presence_score=
            result["professional_presence_score"],

        status=
            result["status"],

        strengths=
            result["strengths"],

        weaknesses=
            result["weaknesses"],

        suggestions=
            result["suggestions"],

        ai_summary=
            result["ai_summary"],

        completion_score=
            result["completion_score"],

        contact_score=
            result["contact_score"],

        structure_score=
            result["structure_score"],

        rating=
            result["rating"],

        word_count=
            result["word_count"],

        action_word_count=
            result["action_word_count"],

        quantified_count=
            result["quantified_count"],

        resume_health=
            result["resume_health"],

        content_signals=
            result["content_signals"]
    )

# =========================================================
# O*NET SKILLS
# =========================================================

def get_onet_skills(
    occupation_code
):

    if not ONET_API_KEY:

        return []


    code = quote(
        occupation_code,
        safe=""
    )


    url = (
        ONET_BASE_URL
        + "/online/occupations/"
        + code
        + "/details/skills"
        + "?start=1&end=30&sort=importance"
    )


    data = http_get_json(
        url,
        headers={
            "Accept": "application/json",
            "X-API-Key": ONET_API_KEY
        }
    )


    if not data:

        return []


    elements = data.get(
        "element",
        []
    )


    skills = []

    for element in elements:

        name = element.get(
            "name"
        )

        if name:

            skills.append(
                name
            )


    return skills


# =========================================================
# O*NET TECHNOLOGY SKILLS
# =========================================================

def get_onet_technology_skills(
    occupation_code
):

    if not ONET_API_KEY:

        return []


    code = quote(
        occupation_code,
        safe=""
    )


    url = (
        ONET_BASE_URL
        + "/online/occupations/"
        + code
        + "/details/technology_skills"
        + "?start=1&end=30"
    )


    data = http_get_json(
        url,
        headers={
            "Accept": "application/json",
            "X-API-Key": ONET_API_KEY
        }
    )


    if not data:

        return []


    categories = data.get(
        "category",
        []
    )


    technologies = []


    for category in categories:

        title = category.get(
            "title"
        )

        if title:

            technologies.append(
                title
            )


        examples = category.get(
            "example",
            []
        )


        for example in examples:

            if isinstance(
                example,
                dict
            ):

                example_title = example.get(
                    "title"
                )

                if example_title:

                    technologies.append(
                        example_title
                    )


    return technologies


# =========================================================
# FIND BUILT-IN ROLE HINTS
# =========================================================

def get_role_hints(
    target_job
):

    target = normalize_text(
        target_job
    )


    found = []


    # Exact / phrase matches

    for role_key, skills in ROLE_HINTS.items():

        if role_key in target:

            found.extend(
                skills
            )


    # Word-based broad matching

    role_keywords = {

        "embedded": [
            "embedded"
        ],

        "firmware": [
            "firmware"
        ],

        "vlsi": [
            "vlsi"
        ],

        "fpga": [
            "fpga",
            "verilog",
            "systemverilog"
        ],

        "robotics": [
            "robotics"
        ],

        "robot": [
            "robotics"
        ],

        "iot": [
            "iot",
            "internet of things"
        ],

        "cyber": [
            "cybersecurity",
            "network security",
            "linux",
            "python"
        ],

        "security": [
            "cybersecurity",
            "network security",
            "linux"
        ],

        "cloud": [
            "aws",
            "azure",
            "gcp",
            "docker",
            "kubernetes",
            "linux"
        ],

        "devops": [
            "docker",
            "kubernetes",
            "jenkins",
            "terraform",
            "linux",
            "git"
        ],

        "frontend": [
            "html",
            "css",
            "javascript",
            "react"
        ],

        "backend": [
            "python",
            "java",
            "sql",
            "rest api",
            "git"
        ],

        "database": [
            "sql",
            "mysql",
            "postgresql",
            "mongodb"
        ],

        "developer": [
            "python",
            "java",
            "javascript",
            "sql",
            "git",
            "rest api"
        ],

        "software": [
            "python",
            "java",
            "c++",
            "javascript",
            "sql",
            "data structures",
            "algorithms",
            "git"
        ],

        "full stack": [
            "html",
            "css",
            "javascript",
            "react",
            "node.js",
            "sql",
            "rest api",
            "git"
        ],

        "data analyst": [
            "sql",
            "excel",
            "data analysis",
            "statistics",
            "pandas",
            "power bi"
        ],

        "qa": [
            "software testing",
            "test automation",
            "selenium",
            "postman",
            "sql"
        ],

        "test engineer": [
            "software testing",
            "test automation",
            "selenium",
            "postman"
        ],

        "network": [
            "computer networks",
            "networking",
            "tcp/ip",
            "dns",
            "linux"
        ],

        "electronics": [
            "electronics",
            "circuit design",
            "pcb design",
            "microcontroller",
            "embedded c"
        ],

        "electrical": [
            "electrical design",
            "power systems",
            "control systems",
            "matlab",
            "plc"
        ],

        "mechanical": [
            "cad",
            "autocad",
            "solidworks",
            "ansys",
            "manufacturing"
        ],

        "civil": [
            "autocad",
            "revit",
            "structural analysis",
            "staad pro",
            "etabs"
        ],

        "structural": [
            "autocad",
            "revit",
            "structural analysis",
            "staad pro",
            "etabs"
        ],

        "chemical": [
            "thermodynamics",
            "fluid mechanics",
            "process engineering",
            "process control"
        ],

        "aerospace": [
            "matlab",
            "simulink",
            "cad",
            "ansys",
            "fluid mechanics"
        ],

        "automotive": [
            "cad",
            "solidworks",
            "catia",
            "embedded c",
            "control systems"
        ],

        "mechatronics": [
            "cad",
            "matlab",
            "simulink",
            "plc",
            "robotics",
            "control systems"
        ]
    }


    for keyword, skills in role_keywords.items():

        if keyword in target:

            found.extend(
                skills
            )


    # Generic engineering fallback. This prevents a valid
    # engineering title from producing an empty requirement
    # set when O*NET is unavailable.
    if not found and (
        "engineer" in target
        or "developer" in target
        or "analyst" in target
    ):

        if "analyst" in target:
            found.extend([
                "sql",
                "excel",
                "data analysis",
                "statistics"
            ])

        else:
            found.extend([
                "problem solving",
                "communication",
                "git"
            ])

    return list(
        dict.fromkeys(
            found
        )
    )
# =========================================================
# O*NET ROLE SEARCH
# =========================================================

def search_onet_role(
    target_job
):

    if not ONET_API_KEY:
        return None

    params = urlencode({
        "keyword": target_job,
        "start": 1,
        "end": 5
    })

    url = (
        ONET_BASE_URL
        + "/online/search?"
        + params
    )

    data = http_get_json(
        url,
        headers={
            "Accept": "application/json",
            "X-API-Key": ONET_API_KEY
        }
    )

    if not data:
        return None

    occupations = data.get(
        "occupation",
        []
    )

    if not occupations:
        return None

    return occupations[0]


# =========================================================
# O*NET OCCUPATION DETAILS
# =========================================================

def get_onet_occupation_details(
    occupation_code
):

    if not ONET_API_KEY:
        return None

    code = quote(
        occupation_code,
        safe=""
    )

    url = (
        ONET_BASE_URL
        + "/online/occupations/"
        + code
        + "/"
    )

    return http_get_json(
        url,
        headers={
            "Accept": "application/json",
            "X-API-Key": ONET_API_KEY
        }
    )



# =========================================================
# BUILD ROLE REQUIREMENTS
# =========================================================

def build_role_requirements(
    target_job
):

    requirements = {

        "target_job": target_job,

        "matched_occupation": None,

        "occupation_code": None,

        "occupation_description": "",

        "required_skills": [],

        "technology_skills": [],

        "role_hints": [],

        "source": "Built-in role knowledge",

        "source_note": (
            "Role requirements are based on built-in "
            "engineering-role knowledge."
        )
    }


    # -----------------------------------------------------
    # Built-in hints
    # -----------------------------------------------------

    role_hints = get_role_hints(
        target_job
    )


    requirements["role_hints"] = role_hints


    # -----------------------------------------------------
    # O*NET
    # -----------------------------------------------------

    if ONET_API_KEY:

        occupation = search_onet_role(
            target_job
        )


        if occupation:

            code = occupation.get(
                "code"
            )

            title = occupation.get(
                "title"
            )


            requirements["matched_occupation"] = title

            requirements["occupation_code"] = code

            requirements["source"] = (
                "O*NET Web Services + built-in role knowledge"
            )

            requirements["source_note"] = (
                "Occupation information and skills are "
                "supplemented by O*NET Web Services."
            )


            if code:

                details = get_onet_occupation_details(
                    code
                )


                if details:

                    requirements[
                        "occupation_description"
                    ] = details.get(
                        "description",
                        ""
                    )


                requirements[
                    "required_skills"
                ] = get_onet_skills(
                    code
                )


                requirements[
                    "technology_skills"
                ] = get_onet_technology_skills(
                    code
                )


    # -----------------------------------------------------
    # Combine skills
    # -----------------------------------------------------

    all_skills = []

    all_skills.extend(
        role_hints
    )

    all_skills.extend(
        requirements["required_skills"]
    )

    all_skills.extend(
        requirements["technology_skills"]
    )


    # Clean and deduplicate

    cleaned = []


    for skill in all_skills:

        if not skill:

            continue


        skill = str(
            skill
        ).strip()


        if len(skill) < 2:

            continue


        if skill.lower() not in [
            x.lower()
            for x in cleaned
        ]:

            cleaned.append(
                skill
            )


    # Keep a reasonable number for UI

    requirements[
        "required_skills"
    ] = cleaned[:40]


    return requirements


# =========================================================
# CREATE ROLE-SPECIFIC PROJECTS
# =========================================================

def generate_role_projects(
    target_job,
    missing_skills
):

    target = normalize_text(
        target_job
    )


    projects = []


    # Embedded

    if (
        "embedded" in target
        or "firmware" in target
    ):

        projects.extend([

            {
                "title": "Embedded Sensor Monitoring System",
                "description": (
                    "Build a microcontroller-based system that "
                    "reads sensors, communicates over a hardware "
                    "interface and records useful measurements."
                ),
                "focus": "Embedded Systems"
            },

            {
                "title": "RTOS-Based Device Controller",
                "description": (
                    "Build a small embedded application using "
                    "tasks, scheduling, synchronization and "
                    "hardware peripherals."
                ),
                "focus": "RTOS / Firmware"
            },

            {
                "title": "Embedded Communication Project",
                "description": (
                    "Build a device demonstrating UART, SPI or "
                    "I2C communication and document the debugging process."
                ),
                "focus": "Embedded Communication"
            }

        ])


    # VLSI

    elif (
        "vlsi" in target
        or "verification" in target
        or "rtl" in target
        or "fpga" in target
    ):

        projects.extend([

            {
                "title": "RTL Digital Design Project",
                "description": (
                    "Design and verify a practical digital module "
                    "using Verilog or SystemVerilog."
                ),
                "focus": "RTL Design"
            },

            {
                "title": "SystemVerilog Verification Project",
                "description": (
                    "Create a verification environment for an RTL "
                    "design and demonstrate functional verification."
                ),
                "focus": "Verification"
            },

            {
                "title": "FPGA-Based Hardware Project",
                "description": (
                    "Implement a useful digital system on an FPGA "
                    "and document synthesis, testing and results."
                ),
                "focus": "FPGA"
            }

        ])


    # Robotics

    elif "robot" in target:

        projects.extend([

            {
                "title": "Autonomous Robot Prototype",
                "description": (
                    "Build a robot that senses its environment "
                    "and performs navigation or obstacle avoidance."
                ),
                "focus": "Robotics"
            },

            {
                "title": "ROS-Based Robot System",
                "description": (
                    "Build a ROS/ROS2 application with sensors, "
                    "nodes and robot-control logic."
                ),
                "focus": "ROS"
            },

            {
                "title": "Vision-Based Robot",
                "description": (
                    "Combine computer vision with robot control "
                    "to solve a practical perception problem."
                ),
                "focus": "Robotics + Computer Vision"
            }

        ])


    # Cybersecurity

    elif (
        "cyber" in target
        or "security" in target
    ):

        projects.extend([

            {
                "title": "Network Security Monitoring System",
                "description": (
                    "Build a controlled lab project that monitors "
                    "network activity and identifies suspicious patterns."
                ),
                "focus": "Cybersecurity"
            },

            {
                "title": "Secure Web Application",
                "description": (
                    "Build a web application and demonstrate "
                    "secure authentication, authorization and input validation."
                ),
                "focus": "Application Security"
            },

            {
                "title": "Security Log Analysis",
                "description": (
                    "Create a system that processes security logs "
                    "and highlights suspicious events."
                ),
                "focus": "Security Analytics"
            }

        ])


    # AI / ML

    elif (
        "machine learning" in target
        or "ml" in target
        or "ai" in target
        or "artificial intelligence" in target
    ):

        projects.extend([

            {
                "title": "End-to-End ML Prediction System",
                "description": (
                    "Build a complete machine-learning application "
                    "from data preprocessing through evaluation and deployment."
                ),
                "focus": "Machine Learning"
            },

            {
                "title": "RAG-Based AI Assistant",
                "description": (
                    "Build a retrieval-augmented application that "
                    "retrieves relevant documents and generates grounded answers."
                ),
                "focus": "Generative AI"
            },

            {
                "title": "Computer Vision Application",
                "description": (
                    "Build a practical computer-vision system "
                    "using image processing and a deep-learning model."
                ),
                "focus": "Computer Vision"
            }

        ])


    # Data

    elif (
        "data scientist" in target
        or "data science" in target
    ):

        projects.extend([

            {
                "title": "End-to-End Data Science Project",
                "description": (
                    "Perform data cleaning, exploratory analysis, "
                    "feature engineering, modelling and evaluation."
                ),
                "focus": "Data Science"
            },

            {
                "title": "Predictive Analytics Project",
                "description": (
                    "Build a predictive model using a real dataset "
                    "and explain model evaluation and limitations."
                ),
                "focus": "Predictive Analytics"
            },

            {
                "title": "Business Analytics Dashboard",
                "description": (
                    "Create an interactive dashboard that converts "
                    "real data into useful insights."
                ),
                "focus": "Analytics"
            }

        ])


    # Generic

    else:

        projects.extend(
            GENERIC_PROJECTS
        )


    # Add gap-driven project

    if missing_skills:

        skills_text = ", ".join(
            missing_skills[:4]
        )


        projects.append({

            "title": "Skill-Gap Demonstration Project",

            "description": (
                f"Build a project for {target_job} that "
                f"demonstrates some of these missing skills: "
                f"{skills_text}."
            ),

            "focus": "Skill Gap"

        })


    # Maximum useful number

    return projects[:5]


# =========================================================
# CREATE LEARNING PLAN
# =========================================================

def generate_learning_plan(
    target_job,
    missing_skills
):

    learning = []


    for skill in missing_skills[:8]:

        learning.append({

            "title": f"Learn {skill}",

            "description": (
                f"Study the fundamentals of {skill}, "
                f"then apply it in a small practical project "
                f"related to {target_job}."
            )

        })


    if not learning:

        learning = list(
            GENERIC_LEARNING
        )


    return learning[:8]


# =========================================================
# CREATE ROADMAP
# =========================================================

def generate_roadmap(
    target_job,
    missing_skills
):

    first_gaps = ", ".join(
        missing_skills[:5]
    )


    if not first_gaps:

        first_gaps = (
            "the most relevant skills "
            "identified for the role"
        )


    return [

        {
            "title": "1. Assess",
            "description": (
                f"Compare your current resume with "
                f"{target_job} requirements."
            )
        },

        {
            "title": "2. Learn",
            "description": (
                f"Build knowledge in your priority gaps: "
                f"{first_gaps}."
            )
        },

        {
            "title": "3. Build",
            "description": (
                "Create practical projects that provide "
                "evidence of the skills you learned."
            )
        },

        {
            "title": "4. Improve",
            "description": (
                "Update your resume so skills are connected "
                "to real projects, coursework or experience."
            )
        },

        {
            "title": "5. Apply",
            "description": (
                "Use the target job description to tailor "
                "each application."
            )
        }

    ]


# =========================================================
# ANALYZE JOB TARGET
# =========================================================

def analyze_job_target(
    resume_text,
    target_job,
    stored_skills=None
):

    requirements = build_role_requirements(
        target_job
    )


    resume_lower = normalize_text(
        resume_text
    )


    # -----------------------------------------------------
    # REQUIRED SKILLS
    # -----------------------------------------------------

    required_skills = requirements[
        "required_skills"
    ]


    matching_skills = []

    missing_skills = []

    # Use the freshly extracted resume text first.
    # Also use the skills saved during upload as a
    # fallback. This makes Job Match more robust when
    # PDF text extraction behaves slightly differently
    # across devices/browsers.

    stored_skill_text = ""

    if stored_skills:
        if isinstance(stored_skills, (list, tuple, set)):
            stored_skill_text = ", ".join(
                str(x) for x in stored_skills if str(x).strip()
            )
        else:
            stored_skill_text = str(stored_skills)

    combined_resume_text = (
        resume_lower
        + " "
        + normalize_text(stored_skill_text)
    ).strip()


    for skill in required_skills:

        if skill_in_text(
            skill,
            combined_resume_text
        ):

            matching_skills.append(
                skill
            )

        else:

            missing_skills.append(
                skill
            )


    # -----------------------------------------------------
    # READINESS
    # -----------------------------------------------------

    total_skills = len(
        required_skills
    )


    if total_skills:

        readiness = int(
            (
                len(matching_skills)
                /
                total_skills
            )
            * 100
        )

    else:

        readiness = 0


    readiness = max(
        0,
        min(
            readiness,
            100
        )
    )


    # -----------------------------------------------------
    # RESUME IMPROVEMENTS
    # -----------------------------------------------------

    resume_improvements = []


    resume_improvements.append({

        "title": "Strengthen your professional summary",

        "description": (
            f"Make your summary clearly describe the "
            f"type of work you want to do as a "
            f"{target_job} and highlight your strongest "
            f"relevant skills."
        )

    })


    if missing_skills:

        resume_improvements.append({

            "title": "Address important skill gaps",

            "description": (
                "These skills were not detected in the "
                "uploaded resume: "
                + ", ".join(
                    missing_skills[:8]
                )
                + ". "
                "Do not add a skill as completed unless "
                "you genuinely have that skill."
            )

        })


    resume_improvements.append({

        "title": "Make projects outcome-focused",

        "description": (
            "For each relevant project, explain the "
            "problem, technologies used, your contribution "
            "and measurable results where available."
        )

    })


    resume_improvements.append({

        "title": "Connect skills to evidence",

        "description": (
            "Important technical skills should be supported "
            "by projects, internships, coursework or "
            "practical experience."
        )

    })


    # -----------------------------------------------------
    # NEXT STEPS
    # -----------------------------------------------------

    next_steps = []


    if missing_skills:

        next_steps.append({

            "title": "Work on your priority skill gaps",

            "description": (
                "Start with: "
                + ", ".join(
                    missing_skills[:5]
                )
                + "."
            )

        })


    next_steps.append({

        "title": "Build one target-role project",

        "description": (
            f"Create one strong project that demonstrates "
            f"skills expected from a {target_job}."
        )

    })


    next_steps.append({

        "title": "Improve resume evidence",

        "description": (
            "Update your summary, skills and project "
            "descriptions so your preparation is clearly visible."
        )

    })


    next_steps.append({

        "title": "Tailor applications",

        "description": (
            "Compare your resume with each actual job "
            "description before applying."
        )

    })


    # -----------------------------------------------------
    # ROLE-SPECIFIC PROJECTS
    # -----------------------------------------------------

    projects = generate_role_projects(
        target_job,
        missing_skills
    )


    # -----------------------------------------------------
    # LEARNING
    # -----------------------------------------------------

    learning = generate_learning_plan(
        target_job,
        missing_skills
    )


    # -----------------------------------------------------
    # ROADMAP
    # -----------------------------------------------------

    roadmap = generate_roadmap(
        target_job,
        missing_skills
    )


    # -----------------------------------------------------
    # RETURN
    # -----------------------------------------------------

    return {

        "target_job": target_job,

        "readiness": readiness,

        "matching_skills": matching_skills,

        "missing_skills": missing_skills,

        "required_skills": required_skills,

        "technology_skills": requirements[
            "technology_skills"
        ],

        "matched_occupation": requirements[
            "matched_occupation"
        ],

        "occupation_code": requirements[
            "occupation_code"
        ],

        "occupation_description": requirements[
            "occupation_description"
        ],

        "source": requirements[
            "source"
        ],

        "source_note": requirements[
            "source_note"
        ],

        "resume_improvements": resume_improvements,

        "projects": projects,

        "learning": learning,

        "roadmap": roadmap,

        "next_steps": next_steps

    }


# =========================================================
# ADZUNA JOB SEARCH
# =========================================================

def search_adzuna_jobs(
    target_job,
    results_per_page=20,
    page=1,
    location=None
):
    """
    Search real jobs from Adzuna.

    The search is intentionally broad so that the system can
    handle:
        - AI / ML
        - Data
        - Software
        - Python
        - Full Stack
        - Cloud
        - Cybersecurity
        - Embedded
        - Electronics
        - VLSI
        - Robotics
        - IoT
        - DevOps
        - Mechanical
        - Civil
        - internships
        - fresher jobs
        - experienced jobs
        - and other user-entered roles
    """

    if not ADZUNA_APP_ID:
        return None

    if not ADZUNA_APP_KEY:
        return None

    target_job = str(
        target_job or ""
    ).strip()

    if not target_job:
        return None

    country = quote(
        ADZUNA_COUNTRY,
        safe=""
    )

    try:
        results_per_page = int(
            results_per_page
        )
    except Exception:
        results_per_page = 20

    results_per_page = max(
        1,
        min(
            results_per_page,
            20
        )
    )

    try:
        page = int(page)
    except Exception:
        page = 1

    page = max(
        1,
        page
    )

    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,

        "results_per_page": results_per_page,

        "what": target_job,

        "where": (
            location
            or ADZUNA_LOCATION
        ),
        

        "content-type": "application/json"
    }

    url = (
        ADZUNA_BASE_URL
        + "/jobs/"
        + country
        + "/search/"
        + str(page)
        + "?"
        + urlencode(params)
    )

    return http_get_json(
        url,
        headers={
            "Accept": "application/json"
        }
    )

# =========================================================
# JOOBLE JOB SEARCH
# =========================================================

def search_jooble_jobs(
    target_job,
    location,
    results_per_page=10
):
    """
    Search real jobs from Jooble India.

    Jooble is optional. If no API key is configured,
    the function simply returns no results and Adzuna
    continues working normally.
    """

    if not JOOBLE_API_KEY:
        return None

    target_job = str(
        target_job or ""
    ).strip()

    location = str(
        location or ""
    ).strip()

    if not target_job or not location:
        return None

    try:

        results_per_page = int(
            results_per_page
        )

    except Exception:

        results_per_page = 10

    results_per_page = max(
        1,
        min(
            results_per_page,
            10
        )
    )

    url = (
        JOOBLE_BASE_URL
        + "/"
        + JOOBLE_API_KEY
    )

    payload = {
        "keywords": target_job,
        "location": location,
        "page": 1,
        "ResultOnPage": results_per_page,
        "SearchMode": 0,
        "companysearch": False
    }

    try:

        request_object = Request(
            url,
            data=json.dumps(
                payload
            ).encode("utf-8"),
            headers={
                "Content-Type": (
                    "application/json"
                ),
                "Accept": (
                    "application/json"
                )
            },
            method="POST"
        )

        with urlopen(
            request_object,
            timeout=15
        ) as response:

            response_data = (
                response.read()
                .decode("utf-8")
            )

            return json.loads(
                response_data
            )

    except HTTPError as e:

        print(
            "Jooble HTTP error:",
            e.code
        )

        return None

    except URLError as e:

        print(
            "Jooble connection error:",
            e
        )

        return None

    except Exception as e:

        print(
            "Jooble error:",
            e
        )

        return None

# =========================================================
# ADZUNA TOP COMPANIES
# =========================================================

def search_adzuna_top_companies(
    target_job
):

    if not ADZUNA_APP_ID:

        return []

    if not ADZUNA_APP_KEY:

        return []


    country = quote(
        ADZUNA_COUNTRY,
        safe=""
    )


    params = {

        "app_id": ADZUNA_APP_ID,

        "app_key": ADZUNA_APP_KEY,

        "what": target_job,

        "where": ADZUNA_LOCATION,

        "content-type": "application/json"

    }


    url = (

        ADZUNA_BASE_URL
        + "/jobs/"
        + country
        + "/top_companies?"
        + urlencode(params)

    )


    data = http_get_json(
        url,
        headers={
            "Accept": "application/json"
        }
    )


    if not data:

        return []


    return data.get(
        "leaderboard",
        []
    )

# =========================================================
# JOB OPPORTUNITY CATEGORY
# =========================================================

def classify_job_opportunity(job):

    title = str(
        job.get("title", "")
        or ""
    ).strip().lower()

    description = str(
        job.get("description", "")
        or ""
    ).strip().lower()

    text = title + " " + description

    # =====================================================
    # 1. INTERNSHIP
    # =====================================================

    internship_words = [
        "intern",
        "internship",
        "summer intern",
        "winter intern",
        "engineering intern",
        "software intern",
        "developer intern",
        "data science intern",
        "machine learning intern",
        "ai intern",
        "ai/ml intern"
    ]

    if any(
        word in title
        for word in internship_words
    ):
        return "internship"

    # =====================================================
    # EXPERIENCED SAFETY CHECK
    # =====================================================

    experienced_title_words = [
        "senior",
        "sr.",
        "sr ",
        "principal",
        "lead",
        "staff engineer",
        "staff software",
        "manager",
        "engineering manager",
        "technical manager",
        "architect",
        "director",
        "head of",
        "vice president",
        "vp ",
        "chief "
    ]

    experienced_patterns = [
        "3+ years",
        "4+ years",
        "5+ years",
        "6+ years",
        "7+ years",
        "8+ years",
        "10+ years",
        "3 years of experience",
        "4 years of experience",
        "5 years of experience",
        "6 years of experience",
        "7 years of experience",
        "8 years of experience"
    ]

    # =====================================================
    # 2. FRESHER / ENTRY LEVEL
    # =====================================================

    fresher_words = [
        "fresher",
        "freshers",
        "entry level",
        "entry-level",
        "graduate",
        "recent graduate",
        "new graduate",
        "junior",
        "jr.",
        "jr ",
        "associate software engineer",
        "associate developer",
        "graduate trainee",
        "graduate engineer trainee"
    ]

    fresher_patterns = [
        "freshers welcome",
        "open to freshers",
        "suitable for freshers",
        "recent graduates",
        "entry level candidates",
        "entry-level candidates",
        "0-1 years",
        "0–1 years",
        "0 to 1 years",
        "0-2 years",
        "0–2 years",
        "0 to 2 years",
        "no experience required",
        "no prior experience"
    ]

    # Senior/Principal/etc. must NOT become fresher
    if any(
        word in title
        for word in experienced_title_words
    ):
        return "experienced"

    if any(
        word in title
        for word in fresher_words
    ):
        return "fresher"

    if any(
        pattern in text
        for pattern in fresher_patterns
    ):
        return "fresher"

    # =====================================================
    # 3. EXPERIENCED
    # =====================================================

    if any(
        word in title
        for word in experienced_title_words
    ):
        return "experienced"

    if any(
        pattern in text
        for pattern in experienced_patterns
    ):
        return "experienced"

    # =====================================================
    # 4. GENERAL
    # =====================================================

    return "general"

# =========================================================
# RELATED JOB SEARCH QUERIES
# =========================================================
#
# The user can enter any role. For common engineering roles,
# we also search a small number of closely related titles so
# the Job Opportunities section is not limited to one exact
# title. The original target-role search remains unchanged.
#
# =========================================================

RELATED_JOB_QUERIES = {

    "software developer": [
        "software engineer",
        "application developer"
    ],

    "software engineer": [
        "software developer",
        "application developer"
    ],

    "ai/ml engineer": [
        "machine learning engineer",
        "ai engineer"
    ],

    "machine learning engineer": [
        "ai engineer",
        "data scientist"
    ],

    "ai engineer": [
        "machine learning engineer",
        "generative ai engineer"
    ],

    "data scientist": [
        "machine learning engineer",
        "data analyst"
    ],

    "data analyst": [
        "business analyst",
        "data scientist"
    ],

    "python developer": [
        "backend developer",
        "software developer"
    ],

    "full stack developer": [
        "software developer",
        "web developer"
    ],

    "frontend developer": [
        "web developer",
        "ui developer"
    ],

    "backend developer": [
        "python developer",
        "software developer"
    ],

    "cloud engineer": [
        "devops engineer",
        "site reliability engineer"
    ],

    "devops engineer": [
        "cloud engineer",
        "site reliability engineer"
    ],

    "cybersecurity engineer": [
        "security analyst",
        "network security engineer"
    ],

    "embedded systems engineer": [
        "firmware engineer",
        "iot engineer"
    ],

    "firmware engineer": [
        "embedded systems engineer",
        "iot engineer"
    ],

    "iot engineer": [
        "embedded systems engineer",
        "firmware engineer"
    ],

    "robotics engineer": [
        "robotics engineer",
        "automation engineer"
    ],

    "vlsi design engineer": [
        "rtl design engineer",
        "verification engineer"
    ],

    "verification engineer": [
        "rtl design engineer",
        "vlsi design engineer"
    ],

    "electronics engineer": [
        "embedded systems engineer",
        "electrical engineer"
    ],

    "electrical engineer": [
        "electronics engineer",
        "control systems engineer"
    ],

    "mechanical engineer": [
        "mechanical design engineer",
        "manufacturing engineer"
    ],

    "civil engineer": [
        "structural engineer",
        "site engineer"
    ],

    "structural engineer": [
        "civil engineer",
        "structural design engineer"
    ],

    "automotive engineer": [
        "mechanical engineer",
        "embedded systems engineer"
    ],

    "mechatronics engineer": [
        "automation engineer",
        "robotics engineer"
    ]
}


def get_related_job_queries(
    target_job
):

    target = normalize_text(
        target_job
    )

    related = []

    # Exact common-role match.
    for role, queries in RELATED_JOB_QUERIES.items():

        if target == normalize_text(role):

            related.extend(queries)

    # Broader role matching for natural variations.
    if not related:

        if "software" in target and (
            "developer" in target
            or "engineer" in target
        ):
            related.extend([
                "software developer",
                "software engineer"
            ])

        elif "machine learning" in target:
            related.extend([
                "machine learning engineer",
                "ai engineer"
            ])

        elif "data" in target and "analyst" in target:
            related.extend([
                "data analyst",
                "business analyst"
            ])

        elif "data" in target and "scientist" in target:
            related.extend([
                "data scientist",
                "machine learning engineer"
            ])

        elif "embedded" in target or "firmware" in target:
            related.extend([
                "embedded systems engineer",
                "firmware engineer"
            ])

        elif "vlsi" in target or "verification" in target:
            related.extend([
                "vlsi design engineer",
                "verification engineer"
            ])

        elif "mechanical" in target:
            related.extend([
                "mechanical engineer",
                "manufacturing engineer"
            ])

        elif "civil" in target:
            related.extend([
                "civil engineer",
                "structural engineer"
            ])

        elif "electrical" in target or "electronics" in target:
            related.extend([
                "electrical engineer",
                "electronics engineer"
            ])

    # Remove the exact target and duplicates.
    result = []
    target_norm = normalize_text(target_job)

    for query in related:

        query_norm = normalize_text(query)

        if not query_norm:
            continue

        if query_norm == target_norm:
            continue

        if query_norm not in [
            normalize_text(x) for x in result
        ]:
            result.append(query)

    return result[:2]


# =========================================================
# BUILD MARKET DATA
# =========================================================

def get_job_market_data(
    target_job,
    locations=None
):

    checked_at = datetime.now().strftime(
        "%d-%m-%Y %H:%M"
    )

    # -----------------------------------------------------
    # LOCATIONS
    # -----------------------------------------------------

    if not locations:
        locations = [
            ADZUNA_LOCATION
        ]

    cleaned_locations = []

    for location in locations:

        location = str(
            location or ""
        ).strip()

        if location and location not in cleaned_locations:
            cleaned_locations.append(
                location
            )

    locations = cleaned_locations[:4]

    if not locations:
        locations = [
            ADZUNA_LOCATION
        ]

    # -----------------------------------------------------
    # API AVAILABILITY
    # -----------------------------------------------------

    adzuna_available = bool(
        ADZUNA_APP_ID
        and ADZUNA_APP_KEY
    )

    jooble_available = bool(
        JOOBLE_API_KEY
    )

    if not adzuna_available and not jooble_available:

        return {
            "available": False,
            "source": "Adzuna + Jooble",
            "checked_at": checked_at,
            "location": ", ".join(locations),
            "locations": locations,
            "message": (
                "Live job-market APIs are not connected."
            ),
            "jobs": [],
            "internships": [],
            "fresher_jobs": [],
            "experienced_jobs": [],
            "general_jobs": [],
            "top_companies": [],
            "total_jobs": 0,
            "recent_jobs": 0,
            "salary_min": None,
            "salary_max": None,
            "salary_average": None,
            "source_counts": {},
            "sources": [],
            "date": checked_at
        }

    # -----------------------------------------------------
    # STORAGE
    # -----------------------------------------------------

    all_jobs = []

    total_jobs_count = 0

    source_counts = {
        "Adzuna": 0,
        "Jooble": 0
    }

    salary_values = []

    # -----------------------------------------------------
    # SAFE DATE
    # -----------------------------------------------------

    def safe_job_datetime(value):

        if not value:
            return datetime.min.replace(
                tzinfo=timezone.utc
            )

        try:

            dt = datetime.fromisoformat(
                str(value).replace(
                    "Z",
                    "+00:00"
                )
            )

            if dt.tzinfo is None:

                dt = dt.replace(
                    tzinfo=timezone.utc
                )

            return dt.astimezone(
                timezone.utc
            )

        except Exception:

            return datetime.min.replace(
                tzinfo=timezone.utc
            )

    # -----------------------------------------------------
    # NORMALIZE ADZUNA JOB
    # -----------------------------------------------------

    def normalize_adzuna_job(
        job,
        fallback_location
    ):

        location_data = job.get(
            "location",
            {}
        )

        if isinstance(
            location_data,
            dict
        ):

            job_location = location_data.get(
                "display_name",
                fallback_location
            )

        else:

            job_location = str(
                location_data
                or fallback_location
            )

        company_data = job.get(
            "company",
            {}
        )

        if isinstance(
            company_data,
            dict
        ):

            company = company_data.get(
                "display_name",
                "Company not specified"
            )

        else:

            company = str(
                company_data
                or "Company not specified"
            )

        created = job.get(
            "created",
            ""
        )

        return {
            "id": str(
                job.get(
                    "id",
                    ""
                )
            ),

            "title": str(
                job.get(
                    "title",
                    "Job Opportunity"
                )
            ).strip(),

            "company": company.strip(),

            "location": str(
                job_location
                or fallback_location
            ).strip(),

            "description": str(
                job.get(
                    "description",
                    ""
                )
                or ""
            ).strip(),

            "created": created,

            "created_datetime": created,

            "contract_time": str(
                job.get(
                    "contract_time",
                    ""
                )
                or ""
            ),

            "contract_type": str(
                job.get(
                    "contract_type",
                    ""
                )
                or ""
            ),

            "salary_min": job.get(
                "salary_min"
            ),

            "salary_max": job.get(
                "salary_max"
            ),

            "redirect_url": str(
                job.get(
                    "redirect_url",
                    ""
                )
                or ""
            ),

            "source": "Adzuna"
        }

    # -----------------------------------------------------
    # NORMALIZE JOOBLE JOB
    # -----------------------------------------------------

    def normalize_jooble_job(
        job,
        fallback_location
    ):

        updated = job.get(
            "updated",
            ""
        )

        return {
            "id": str(
                job.get(
                    "id",
                    ""
                )
            ),

            "title": str(
                job.get(
                    "title",
                    "Job Opportunity"
                )
            ).strip(),

            "company": str(
                job.get(
                    "company",
                    "Company not specified"
                )
                or "Company not specified"
            ).strip(),

            "location": str(
                job.get(
                    "location",
                    fallback_location
                )
                or fallback_location
            ).strip(),

            "description": str(
                job.get(
                    "snippet",
                    ""
                )
                or ""
            ).strip(),

            "created": updated,

            "created_datetime": updated,

            "contract_time": str(
                job.get(
                    "type",
                    ""
                )
                or ""
            ),

            "contract_type": "",

            "salary_min": None,

            "salary_max": None,

            "redirect_url": str(
                job.get(
                    "link",
                    ""
                )
                or ""
            ),

            "source": "Jooble"
        }

    # =====================================================
    # SEARCH EACH SELECTED LOCATION
    # =====================================================

    for location in locations:

        # -------------------------------------------------
        # ADZUNA - NORMAL JOB SEARCH
        # -------------------------------------------------

        if adzuna_available:

            try:

                broad_data = search_adzuna_jobs(
                    target_job,
                    results_per_page=20,
                    page=1,
                    location=location
                )

                if broad_data:

                    total_jobs_count += int(
                        broad_data.get(
                            "count",
                            0
                        )
                        or 0
                    )

                    broad_results = broad_data.get(
                        "results",
                        []
                    )

                    source_counts["Adzuna"] += len(
                        broad_results
                    )

                    for raw_job in broad_results:

                        clean_job = normalize_adzuna_job(
                            raw_job,
                            location
                        )

                        clean_job["search_role"] = target_job

                        all_jobs.append(
                            clean_job
                        )

                        if raw_job.get(
                            "salary_min"
                        ) is not None:

                            salary_values.append(
                                raw_job.get(
                                    "salary_min"
                                )
                            )

                        if raw_job.get(
                            "salary_max"
                        ) is not None:

                            salary_values.append(
                                raw_job.get(
                                    "salary_max"
                                )
                            )

            except Exception as e:

                print(
                    "Adzuna normal search error:",
                    e
                )

        # -------------------------------------------------
        # ADZUNA - RELATED ROLE SEARCH
        # -------------------------------------------------

        if adzuna_available:

            related_queries = get_related_job_queries(
                target_job
            )

            for related_query in related_queries:

                try:

                    related_data = search_adzuna_jobs(
                        related_query,
                        results_per_page=8,
                        page=1,
                        location=location
                    )

                    if related_data:

                        related_results = related_data.get(
                            "results",
                            []
                        )

                        source_counts["Adzuna"] += len(
                            related_results
                        )

                        for raw_job in related_results:

                            clean_job = normalize_adzuna_job(
                                raw_job,
                                location
                            )

                            clean_job["search_role"] = related_query
                            clean_job["related_to"] = target_job

                            all_jobs.append(
                                clean_job
                            )

                            if raw_job.get(
                                "salary_min"
                            ) is not None:

                                salary_values.append(
                                    raw_job.get(
                                        "salary_min"
                                    )
                                )

                            if raw_job.get(
                                "salary_max"
                            ) is not None:

                                salary_values.append(
                                    raw_job.get(
                                        "salary_max"
                                    )
                                )

                except Exception as e:

                    print(
                        "Adzuna related-role search error:",
                        related_query,
                        e
                    )

        # -------------------------------------------------
        # ADZUNA - INTERNSHIP SEARCH
        # -------------------------------------------------

        if adzuna_available:

            try:

                internship_query = (
                    target_job
                    + " internship"
                )

                internship_data = search_adzuna_jobs(
                    internship_query,
                    results_per_page=10,
                    page=1,
                    location=location
                )

                if internship_data:

                    internship_results = (
                        internship_data.get(
                            "results",
                            []
                        )
                    )

                    source_counts["Adzuna"] += len(
                        internship_results
                    )

                    for raw_job in internship_results:

                        clean_job = normalize_adzuna_job(
                            raw_job,
                            location
                        )

                        all_jobs.append(
                            clean_job
                        )

            except Exception as e:

                print(
                    "Adzuna internship search error:",
                    e
                )

        # -------------------------------------------------
        # ADZUNA - FRESHER SEARCH
        # -------------------------------------------------

        if adzuna_available:

            try:

                fresher_query = (
                    target_job
                    + " fresher graduate junior entry level"
                )

                fresher_data = search_adzuna_jobs(
                    fresher_query,
                    results_per_page=10,
                    page=1,
                    location=location
                )

                if fresher_data:

                    fresher_results = (
                        fresher_data.get(
                            "results",
                            []
                        )
                    )

                    source_counts["Adzuna"] += len(
                        fresher_results
                    )

                    for raw_job in fresher_results:

                        clean_job = normalize_adzuna_job(
                            raw_job,
                            location
                        )

                        all_jobs.append(
                            clean_job
                        )

            except Exception as e:

                print(
                    "Adzuna fresher search error:",
                    e
                )

        # -------------------------------------------------
        # JOOBLE - NORMAL SEARCH
        # -------------------------------------------------

        if jooble_available:

            try:

                jooble_data = search_jooble_jobs(
                    target_job,
                    location,
                    results_per_page=10
                )

                if jooble_data:

                    jooble_results = (
                        jooble_data.get(
                            "jobs",
                            []
                        )
                    )

                    source_counts["Jooble"] += len(
                        jooble_results
                    )

                    for raw_job in jooble_results:

                        clean_job = normalize_jooble_job(
                            raw_job,
                            location
                        )

                        all_jobs.append(
                            clean_job
                        )

            except Exception as e:

                print(
                    "Jooble search error:",
                    e
                )

    # =====================================================
    # REMOVE DUPLICATES
    # =====================================================

    unique_jobs = []

    seen = set()

    for job in all_jobs:

        url = str(
            job.get(
                "redirect_url",
                ""
            )
            or ""
        ).strip().lower()

        title = str(
            job.get(
                "title",
                ""
            )
            or ""
        ).strip().lower()

        company = str(
            job.get(
                "company",
                ""
            )
            or ""
        ).strip().lower()

        location = str(
            job.get(
                "location",
                ""
            )
            or ""
        ).strip().lower()

        if url:

            key = (
                "url",
                url
            )

        else:

            key = (
                "job",
                title,
                company,
                location
            )

        if key in seen:
            continue

        seen.add(key)

        unique_jobs.append(
            job
        )

    # =====================================================
    # SORT NEWEST FIRST
    # =====================================================

    unique_jobs = sorted(
        unique_jobs,
        key=lambda job: safe_job_datetime(
            job.get(
                "created_datetime"
            )
        ),
        reverse=True
    )

    # =====================================================
    # CLASSIFY
    #
    # Priority shown in UI:
    # Internship
    # Fresher
    # Experienced
    # General
    # =====================================================

    internships = []

    fresher_jobs = []

    experienced_jobs = []

    general_jobs = []

    for job in unique_jobs:

        category = classify_job_opportunity(
            job
        )

        job["category"] = category

        if category == "internship":

            internships.append(
                job
            )

        elif category == "fresher":

            fresher_jobs.append(
                job
            )

        elif category == "experienced":

            experienced_jobs.append(
                job
            )

        else:

            general_jobs.append(
                job
            )

    # =====================================================
    # TOP COMPANIES
    # =====================================================

    top_companies = []

    if adzuna_available:

        try:

            top_companies = (
                search_adzuna_top_companies(
                    target_job
                )
                or []
            )

        except Exception as e:

            print(
                "Top companies error:",
                e
            )

    # =====================================================
    # SALARY
    # =====================================================

    salary_min = None

    salary_max = None

    salary_average = None

    valid_salaries = []

    for value in salary_values:

        try:

            number = float(
                value
            )

            if number > 0:

                valid_salaries.append(
                    number
                )

        except Exception:

            pass

    if valid_salaries:

        salary_min = min(
            valid_salaries
        )

        salary_max = max(
            valid_salaries
        )

        salary_average = (
            sum(valid_salaries)
            / len(valid_salaries)
        )

    # =====================================================
    # SOURCES
    # =====================================================

    sources = []

    if source_counts.get(
        "Adzuna",
        0
    ) > 0:

        sources.append(
            "Adzuna"
        )

    if source_counts.get(
        "Jooble",
        0
    ) > 0:

        sources.append(
            "Jooble"
        )

    # =====================================================
    # FINAL RESPONSE
    # =====================================================

    return {
        "available": bool(
            unique_jobs
        ),

        "source": (
            " + ".join(sources)
            if sources
            else "Adzuna + Jooble"
        ),

        "sources": sources,

        "source_counts": source_counts,

        "checked_at": checked_at,

        "date": checked_at,

        "location": ", ".join(
            locations
        ),

        "locations": locations,

        "jobs": unique_jobs,

        "internships": internships,

        "fresher_jobs": fresher_jobs,

        "experienced_jobs": experienced_jobs,

        "general_jobs": general_jobs,

        "top_companies": top_companies,

        "related_queries": get_related_job_queries(
            target_job
        ),

        "internship_count": len(
            internships
        ),

        "fresher_count": len(
            fresher_jobs
        ),

        "experienced_count": len(
            experienced_jobs
        ),

        "general_count": len(
            general_jobs
        ),

        "total_jobs": (
            total_jobs_count
            if total_jobs_count > 0
            else len(unique_jobs)
        ),

        "recent_jobs": len(
            unique_jobs
        ),

        "salary_min": salary_min,

        "salary_max": salary_max,

        "salary_average": salary_average,

        "message": (
            "Live job listings retrieved "
            "from the configured job sources."
        )
    }




# =========================================================
# JOB MATCH
# =========================================================

@app.route(
    "/job-match",
    methods=["GET", "POST"]
)
def job_match():

    if not login_required():

        return redirect(
            url_for("login")
        )


    user_id = session["user_id"]


    candidate = None


    with sqlite3.connect(
        "resume.db"
    ) as conn:

        conn.row_factory = sqlite3.Row

        candidate = conn.execute(
            """
            SELECT *
            FROM candidates
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,)
        ).fetchone()


    if not candidate:

        return render_template(

            "job_match.html",

            error="Please upload your resume first.",

            target_job="",

            analysis=None,

            market_data={
                "available": False
            }

        )


    target_job = ""


    if request.method == "POST":

        target_job = request.form.get(
            "target_job",
            ""
        ).strip()

        locations = request.form.getlist(
            "locations"
        )

        if not locations:

            locations = [
                ADZUNA_LOCATION
            ]

        # Maximum 4 locations per search
        locations = locations[:4]

        if not target_job:

            return render_template(

                "job_match.html",

                error="Please enter the job you want.",

                target_job="",

                analysis=None,

                market_data={
                    "available": False
                }

            )


        resume_file = candidate["resume_file"]


        if not resume_file:

            return render_template(

                "job_match.html",

                error=(
                    "Your uploaded resume could not be found. "
                    "Please upload your resume again."
                ),

                target_job=target_job,

                analysis=None,

                market_data={
                    "available": False
                }

            )


        filepath = os.path.join(

            app.config.get(
                "UPLOAD_FOLDER",
                "uploads"
            ),

            resume_file

        )


        if not os.path.exists(
            filepath
        ):

            return render_template(

                "job_match.html",

                error=(
                    "Your resume file is no longer available. "
                    "Please upload your resume again."
                ),

                target_job=target_job,

                analysis=None,

                market_data={
                    "available": False
                }

            )


        try:

            resume_text = extract_resume_text(
                filepath
            )

        except Exception as e:

            print(
                "Job Match resume read error:",
                e
            )

            resume_text = ""


        if not resume_text.strip():

            return render_template(

                "job_match.html",

                error=(
                    "The resume text could not be read. "
                    "Please upload a readable PDF."
                ),

                target_job=target_job,

                analysis=None,

                market_data={
                    "available": False
                }

            )


        # -------------------------------------------------
        # STEP 1-6:
        # Role understanding + resume gap analysis
        # -------------------------------------------------

        analysis = analyze_job_target(

            resume_text,

            target_job,

            candidate["skills"] or ""

        )


        # -------------------------------------------------
        # STEP 7-8:
        # Real job market data
        # -------------------------------------------------

        market_data = get_job_market_data(
            target_job,
            locations
        )

        # -------------------------------------------------
        # SAVE JOB MATCH HISTORY
        # -------------------------------------------------

        try:

            matching_text = ", ".join(
                analysis[
                    "matching_skills"
                ]
            )

            missing_text = ", ".join(
                analysis[
                    "missing_skills"
                ]
            )

            keywords_text = ", ".join(
                analysis[
                    "required_skills"
                ][:20]
            )


            with sqlite3.connect(
                "resume.db"
            ) as conn:

                conn.execute(
                    """
                    INSERT INTO job_matches
                    (
                        user_id,
                        candidate_id,
                        job_id,
                        match_score,
                        matching_skills,
                        missing_skills,
                        keywords,
                        created_at
                    )
                    VALUES(
                        ?,?,?,?,?,?,?,?
                    )
                    """,
                    (
                        user_id,
                        candidate["id"],
                        None,
                        analysis["readiness"],
                        matching_text,
                        missing_text,
                        keywords_text,
                        datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                    )
                )

                conn.commit()

        except Exception as e:

            print(
                "Job match history error:",
                e
            )


        return render_template(

            "job_match.html",

            target_job=target_job,

            analysis=analysis,

            market_data=market_data,

            error=None

        )


    # -----------------------------------------------------
    # GET
    # -----------------------------------------------------

    return render_template(

        "job_match.html",

        target_job="",

        analysis=None,

        market_data={
            "available": False
        },

        error=None

    )


# =========================================================
# HOME PAGE
# =========================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# =========================================================
# REGISTER
# =========================================================


# =========================================================
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        if not name or not email or not password:
            return "Please fill all fields."

        if len(password) < 8:
            return "Password must be at least 8 characters long."

        # Securely hash the password
        hashed_password = generate_password_hash(password)

        try:

            cursor.execute(
                """
                INSERT INTO users(
                    name,
                    email,
                    password
                )
                VALUES(?,?,?)
                """,
                (
                    name,
                    email,
                    hashed_password
                )
            )

            db.commit()

        except sqlite3.IntegrityError:

            return "Email already registered."

        return redirect(
            url_for("login")
        )

    return render_template(
        "register.html"
    )


# =========================================================
# LOGIN
# =========================================================


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        cursor.execute(
            """
            SELECT id, name, email, password
            FROM users
            WHERE LOWER(email)=?
            """,
            (email,)
        )

        user = cursor.fetchone()

        if user:

            stored_password = user[3]

            # Check hashed password first
            password_valid = check_password_hash(
                stored_password,
                password
            )

            # Support old accounts with plain-text passwords
            if not password_valid and stored_password == password:

                password_valid = True

                # Upgrade old password to a secure hash
                new_hash = generate_password_hash(password)

                cursor.execute(
                    """
                    UPDATE users
                    SET password=?
                    WHERE id=?
                    """,
                    (
                        new_hash,
                        user[0]
                    )
                )

                db.commit()

            if password_valid:

                session.clear()

                session["user_id"] = user[0]
                session["user_name"] = user[1]
                session["user_email"] = user[2]

                return redirect(
                    url_for("dashboard")
                )

        return "Invalid Email or Password."

    return render_template(
        "login.html"
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("home")
    )


# =========================================================
# PUBLIC USER DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if not login_required():

        return redirect(
            url_for("login")
        )


    user_id = session["user_id"]


    cursor.execute(
        """
        SELECT *
        FROM candidates
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            user_id,
        )
    )


    latest_resume = cursor.fetchone()


    return render_template(
        "dashboard.html",
        latest_resume=latest_resume
    )


# =========================================================
# UPLOAD / RESUME ANALYSIS
# =========================================================

@app.route(
    "/upload",
    methods=["GET", "POST"]
)
def upload():

    if not login_required():

        return redirect(
            url_for("login")
        )


    # -----------------------------------------------------
    # GET
    # -----------------------------------------------------

    if request.method == "GET":

        return render_template(
            "upload.html"
        )


    # -----------------------------------------------------
    # FILE
    # -----------------------------------------------------

    file = request.files.get(
        "resume"
    )


    if not file or file.filename == "":

        return "Please select a resume PDF."


    if not file.filename.lower().endswith(
        ".pdf"
    ):

        return "Only PDF resumes are supported."


    # -----------------------------------------------------
    # SAVE FILE
    # -----------------------------------------------------

    os.makedirs(
        "uploads",
        exist_ok=True
    )


    filename = secure_filename(
        file.filename
    )


    if not filename:

        return "Invalid file name."


    user_id = session.get(
        "user_id"
    )


    unique_filename = (

        f"user_{user_id}_"

        f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_"

        f"{filename}"

    )


    filepath = os.path.join(
        "uploads",
        unique_filename
    )


    file.save(
        filepath
    )


    # -----------------------------------------------------
    # FORM DATA
    # -----------------------------------------------------

    name = request.form.get(
        "name",
        ""
    ).strip()


    email = request.form.get(
        "email",
        ""
    ).strip()


    # -----------------------------------------------------
    # EXTRACT TEXT
    # -----------------------------------------------------

    text = extract_resume_text(
        filepath
    )


    if not text.strip():

        return (
            "Could not extract text from the resume. "
            "Please upload a readable PDF."
        )


    # -----------------------------------------------------
    # ANALYZE
    # -----------------------------------------------------

    result = analyze_resume(
        text,
        name,
        email
    )


    # -----------------------------------------------------
    # DATE
    # -----------------------------------------------------

    upload_date = datetime.now().strftime(
        "%d-%m-%Y %H:%M"
    )


    # -----------------------------------------------------
    # DATABASE INSERT
    # -----------------------------------------------------

    skills_text = ", ".join(
        result["skills"]
    )


    cursor.execute(
        """
        INSERT INTO candidates
        (
            user_id,
            name,
            email,
            phone,
            education,
            skills,
            ats_score,
            match_score,
            status,
            github,
            linkedin,
            resume_file,
            upload_date
        )
        VALUES(
            ?,?,?,?,?,?,?,?,?,?,?,?,?
        )
        """,
        (
            user_id,
            result["name"],
            result["email"],
            result["phone"],
            result["education"],
            skills_text,
            result["ats_score"],
            result["match_score"],
            result["status"],
            result["github"],
            result["linkedin"],
            unique_filename,
            upload_date
        )
    )


    db.commit()


    # -----------------------------------------------------
    # RESULT PAGE
    # -----------------------------------------------------

    return render_resume_result(
        result,
        upload_date
    )


# =========================================================
# MY RESUME
# =========================================================

@app.route("/my-resume")
def my_resume():

    if not login_required():

        return redirect(
            url_for("login")
        )


    user_id = session["user_id"]


    cursor.execute(
        """
        SELECT
            id,
            name,
            email,
            phone,
            education,
            skills,
            ats_score,
            match_score,
            status,
            github,
            linkedin,
            resume_file,
            upload_date
        FROM candidates
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            user_id,
        )
    )


    candidate = cursor.fetchone()


    if not candidate:

        return redirect(
            url_for("upload")
        )


    resume_file = candidate[11]


    filepath = os.path.join(
        "uploads",
        resume_file
    )


    if not os.path.exists(
        filepath
    ):

        return (
            "Your saved resume file could not be found."
        )


    # -----------------------------------------------------
    # READ SAVED RESUME
    # -----------------------------------------------------

    text = extract_resume_text(
        filepath
    )


    if not text.strip():

        return (
            "Could not read your saved resume."
        )


    # -----------------------------------------------------
    # ANALYZE SAME RESUME
    # -----------------------------------------------------

    result = analyze_resume(
        text,
        candidate[1] or "",
        candidate[2] or ""
    )


    # -----------------------------------------------------
    # SHOW SAME RESULT PAGE
    # -----------------------------------------------------

    return render_resume_result(
        result,
        candidate[12] or ""
    )


# =========================================================
# SETTINGS
# =========================================================

@app.route("/settings")
def settings():

    if not login_required():

        return redirect(
            url_for("login")
        )


    return render_template(
        "settings.html"
    )


# =========================================================
# DOWNLOAD PERSONAL RESUME REPORT
# =========================================================

@app.route("/download-report")
def download_report():

    if not login_required():

        return redirect(
            url_for("login")
        )


    user_id = session["user_id"]


    cursor.execute(
        """
        SELECT
            name,
            email,
            phone,
            education,
            skills,
            ats_score,
            match_score,
            status,
            github,
            linkedin,
            upload_date
        FROM candidates
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            user_id,
        )
    )


    report = cursor.fetchone()


    if not report:

        return "No resume report available."


    # -----------------------------------------------------
    # REPORT FOLDER
    # -----------------------------------------------------

    os.makedirs(
        "reports",
        exist_ok=True
    )


    report_path = os.path.join(
        "reports",
        f"Resume_Report_{user_id}.pdf"
    )


    # -----------------------------------------------------
    # CREATE PDF
    # -----------------------------------------------------

    pdf = canvas.Canvas(
        report_path
    )


    y = 800


    pdf.setFont(
        "Helvetica-Bold",
        20
    )


    pdf.drawString(
        50,
        y,
        "AI Resume Analyzer - Resume Report"
    )


    y -= 40


    pdf.setFont(
        "Helvetica",
        11
    )


    name = report[0] or ""

    email = report[1] or ""

    phone = report[2] or ""

    education = report[3] or ""

    skills = report[4] or ""

    ats_score = report[5] or 0

    match_score = report[6] or 0

    status = report[7] or ""

    github = report[8] or ""

    linkedin = report[9] or ""

    upload_date = report[10] or ""


    lines = [

        f"Name: {name}",

        f"Email: {email}",

        f"Phone: {phone}",

        f"Education: {education}",

        f"Skills: {skills}",

        f"ATS Score: {ats_score}%",

        f"Resume Match: {match_score}%",

        f"Status: {status}",

        f"GitHub: {github}",

        f"LinkedIn: {linkedin}",

        f"Uploaded: {upload_date}"

    ]


    for line in lines:

        if y < 60:

            pdf.showPage()

            y = 800

            pdf.setFont(
                "Helvetica",
                11
            )


        if len(line) > 100:

            line = (
                line[:97]
                + "..."
            )


        pdf.drawString(
            50,
            y,
            line
        )


        y -= 20


    pdf.save()


    return send_file(
        report_path,
        as_attachment=True,
        download_name="Resume_Report.pdf"
    )


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(debug=False)