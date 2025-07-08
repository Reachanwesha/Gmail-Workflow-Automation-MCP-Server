# 📬 Gmail LLM Workflow Automation

An AI-powered workflow automation server that reads emails, detects meeting intents or follow-up opportunities, and performs intelligent actions such as scheduling Google Calendar events or generating progressively urgent follow-up messages.

---

## 🚀 Features

- 📥 **Email Fetching** via Gmail API
- 🤖 **LLM-Based Classification** of emails (Meeting Request or Follow-up)
- 🕐 **Meeting Detection & Scheduling** using Google Calendar API
- ⏳ **Escalating Follow-up Messaging** using GPT-4 and predefined templates
- 🧠 **Context-Aware Agenda Generation** for meetings
- 🗃️ **SQLite Database Integration** for tracking follow-ups and scheduled meetings
- 🔌 **Socket Server Interface** for triggering email processing remotely

---

## 📦 Tech Stack

- Python 3
- Gmail API
- Google Calendar API
- OpenAI GPT-4 (ChatCompletion)
- SQLite3
- Socket (TCP) Server
- OAuth 2.0

---

## 🧰 Workflow Breakdown

### 1. Initialization
- Creates SQLite DB (`followups.db`) with:
  - `followups` table for tracking contact follow-ups
  - `meetings` table for storing scheduled meetings
- Authenticates with Gmail and Calendar APIs using `credentials.json`

### 2. Email Processing
- Fetches the 5 most recent emails from Gmail
- Extracts sender info, subject, and snippet for context

### 3. AI-Based Classification
- Uses GPT-4 to determine:
  - Does the email indicate a **meeting request**?
  - If yes: Extracts proposed time and generates agenda
  - If no: Generates a follow-up based on urgency level

### 4. Calendar Scheduling
- Creates a Google Calendar event for valid meeting requests
- Stores meeting details in DB
- Sends confirmation message (simulated)

### 5. Follow-up Automation
- Tracks previous attempts per contact
- Uses predefined tone templates:
  - Attempt 1: Polite
  - Attempt 2: Friendly Reminder
  - Attempt 3: More Direct
  - Attempt 4: Final Message
- Stores attempt counts and timestamps in the database

### 6. Communication Interface
- Listens on TCP port 8000
- Command: `get_emails` triggers entire workflow
- Responds with email summaries after classification + actions

---

## 🧪 How to Run

1. **Install dependencies**:
   ```bash
   pip install openai google-api-python-client google-auth google-auth-oauthlib

2. **Run the server**
   '''bash
   python main.py
