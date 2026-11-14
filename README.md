# AI Resume Analyzer & Career Assistant

An AI-powered web application designed to help job seekers evaluate their resumes, improve their ATS compatibility, and explore relevant career opportunities.

## Overview

The AI Resume Analyzer & Career Assistant simplifies the resume evaluation process using Artificial Intelligence and Natural Language Processing.

Users can upload their resumes, receive an ATS compatibility score, identify skill gaps, obtain improvement suggestions, and explore relevant job opportunities through a single platform.

## Key Features

- **Resume Analysis:** Extracts and analyzes information from uploaded PDF resumes.
- **ATS Score:** Evaluates resume compatibility and provides an ATS-oriented score.
- **Skill Extraction:** Identifies technical and professional skills from resumes.
- **Resume Improvement:** Provides suggestions to improve resume quality.
- **Job Recommendations:** Helps users discover relevant job opportunities based on their profiles.
- **AI Career Assistant:** Provides interactive career-related guidance.
- **User Dashboard:** Allows users to access their profiles and resume analysis results.
- **Secure Authentication:** Supports user registration and login.
- **Reports & Analytics:** Presents resume evaluation results and insights.

## Technology Stack

| Category | Technologies |
|---|---|
| Programming Language | Python |
| Backend | Flask |
| Frontend | HTML, CSS, JavaScript |
| AI Integration | Google Gemini API |
| Database | SQLite |
| PDF Processing | PyPDF2, pdf2image |
| OCR | Tesseract |
| Data Processing | Python |

## Application Workflow

1. User registers or logs into the application.
2. User uploads a PDF resume.
3. The system extracts resume content.
4. AI-assisted analysis evaluates the extracted information.
5. The application generates an ATS score and improvement suggestions.
6. Users can explore job recommendations and career assistance.

## Getting Started

### Prerequisites

- Python 3.x
- pip
- Git
- Required API credentials for enabled integrations
- Tesseract OCR and Poppler for PDF processing where required

### Installation

**1. Clone the repository**

```bash
git clone YOUR_REPOSITORY_URL
cd AI_resume_project
```

**2. Create a virtual environment**

```bash
python -m venv venv
```

**3. Activate the environment**

Windows:

```bash
venv\Scripts\activate
```

**4. Install dependencies**

```bash
pip install -r requirements.txt
```

**5. Configure environment variables**

Create a `.env` file and add the API credentials required by the application.

Never publish API keys, passwords or other sensitive information.

**6. Run the application**

```bash
python app.py
```

Open the local application at:

`http://127.0.0.1:5000`

## Security & Privacy

- User authentication is supported.
- Sensitive configuration values should be stored in environment variables.
- Uploaded resumes and personal information should be handled securely.
- The repository excludes private configuration and local user data.

## Future Enhancements

- Advanced AI-powered resume recommendations.
- Improved job matching.
- Additional resume formats and analysis capabilities.
- Advertisement integration and premium subscription options.

## Project Status

**Development:** Academic / Personal Software Project

The application is being prepared for public deployment and further enhancements.

## Author

**AI Resume Analyzer & Career Assistant**

Developed as an AI-powered career assistance platform.
