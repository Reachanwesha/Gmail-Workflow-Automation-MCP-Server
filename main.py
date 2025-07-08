import socket
import threading
import json
import os.path
import time
import sqlite3
from datetime import datetime, timedelta

import openai
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/calendar'
]
openai.api_key = "open-ai-api-key"
MAX_ATTEMPTS = 4

TEMPLATES = [
    "Hi {name},\n\nJust checking in on my previous message. {context}",
    "Hi {name},\n\nFollowing up again. I’d appreciate a quick update. {context}",
    "Hi {name},\n\nThis is my third email — is this still something you're considering? {context}",
    "Hi {name},\n\nIf I don’t hear back by end of day, I’ll assume this opportunity is closed. {context}"
]

def init_db():
    print("DB Creation")
    conn = sqlite3.connect('followups.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            name TEXT,
            content TEXT,
            meeting_time TEXT,
            scheduled INTEGER DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS followups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            name TEXT,
            context TEXT,
            attempt INTEGER DEFAULT 1,
            last_sent TEXT
        )
    ''')
    conn.commit()
    conn.close()

def authenticate_google_services():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=3000)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    gmail_service = build('gmail', 'v1', credentials=creds)
    calendar_service = build('calendar', 'v3', credentials=creds)
    return gmail_service, calendar_service

def fetch_recent_emails(max_results=5):
    gmail_service, _ = authenticate_google_services()
    results = gmail_service.users().messages().list(userId='me', maxResults=max_results, labelIds=['INBOX']).execute()
    messages = results.get('messages', [])
    emails = []

    for msg in messages:
        msg_data = gmail_service.users().messages().get(userId='me', id=msg['id']).execute()
        headers = msg_data['payload'].get('headers', [])
        snippet = msg_data.get('snippet', '')

        email_info = {'From': '', 'Subject': '', 'Snippet': snippet}
        for h in headers:
            if h['name'] == 'From':
                email_info['From'] = h['value']
            elif h['name'] == 'Subject':
                email_info['Subject'] = h['value']
        emails.append(email_info)
    return emails

def is_meeting_request(email_text):
    prompt = f"Does this email indicate the sender wants to schedule a meeting? Respond only 'Yes' or 'No'.\n\n{email_text}"
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=5
    )
    return response.choices[0].message.content.strip().lower() == "yes"

def extract_meeting_time(email_text):
    prompt = f"Extract the proposed meeting time and date from the following email. Return it in this format: 'YYYY-MM-DD HH:MM' or say 'none' if not found.\n\n{email_text}"
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=20
    )
    time_str = response.choices[0].message.content.strip()
    if time_str.lower() == 'none':
        return (datetime.now() + timedelta(days=1)).replace(hour=11, minute=0)
    return datetime.strptime(time_str, '%Y-%m-%d %H:%M')

def generate_meeting_agenda(original_email):
    prompt = f"Create a brief meeting agenda based on the following email:\n\n{original_email}"
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=100
    )
    return response.choices[0].message.content.strip()

def send_confirmation_email(calendar_service, to_email, subject, body):
    print(f"[Email Sent] To: {to_email}\nSubject: {subject}\nBody: {body}")

def schedule_google_calendar_meeting(email, name, content):
    _, calendar_service = authenticate_google_services()
    meeting_time = extract_meeting_time(content)
    agenda = generate_meeting_agenda(content)

    event = {
        'summary': f'Meeting with {name}',
        'description': agenda,
        'start': {
            'dateTime': meeting_time.isoformat(),
            'timeZone': 'Asia/Kolkata',
        },
        'end': {
            'dateTime': (meeting_time + timedelta(minutes=30)).isoformat(),
            'timeZone': 'Asia/Kolkata',
        },
        'attendees': [
            {'email': email},
        ],
    }

    calendar_service.events().insert(calendarId='primary', body=event).execute()

    conn = sqlite3.connect('followups.db')
    c = conn.cursor()
    c.execute("INSERT INTO meetings (email, name, content, meeting_time, scheduled) VALUES (?, ?, ?, ?, ?)",
              (email, name, content, meeting_time.isoformat(), 1))
    conn.commit()
    conn.close()

    subject = "Meeting Scheduled"
    body = f"Hi {name},\n\nYour meeting has been scheduled on {meeting_time.strftime('%Y-%m-%d %H:%M')}.\n\nAgenda: {agenda}\n\nThanks"
    send_confirmation_email(calendar_service, email, subject, body)

def generate_followup_message(name, context, attempt):
    template_index = min(attempt - 1, len(TEMPLATES) - 1)
    return TEMPLATES[template_index].format(name=name, context=context)

def schedule_followup(email, name, context):
    conn = sqlite3.connect('followups.db')
    c = conn.cursor()
    c.execute("SELECT id, attempt FROM followups WHERE email = ?", (email,))
    row = c.fetchone()
    if row:
        followup_id, attempt = row
        if attempt < MAX_ATTEMPTS:
            attempt += 1
            c.execute("UPDATE followups SET attempt = ?, last_sent = ? WHERE id = ?", (attempt, datetime.now().isoformat(), followup_id))
    else:
        c.execute("INSERT INTO followups (email, name, context, attempt, last_sent) VALUES (?, ?, ?, ?, ?)",
                  (email, name, context, 1, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    message = generate_followup_message(name, context, attempt if row else 1)
    print(f"[Follow-up Message for {name}]\n{message}\n")

def summarize_emails(emails):
    summary = []
    for i, email in enumerate(emails, 1):
        brief = f"Email {i}:\nFrom: {email['From']}\nSubject: {email['Subject']}\nSnippet: {email['Snippet']}\n"
        summary.append(brief)
    return "\n".join(summary)

def handle_client(client_socket, address):
    print(f"[+] Connection from {address}")
    try:
        while True:
            message = client_socket.recv(1024).decode('utf-8').strip()
            if not message:
                break
            print(f"[>] Received: {message}")

            if message.lower() == "get_emails":
                try:
                    emails = fetch_recent_emails()
                    for email in emails:
                        sender = email['From'].split('<')[-1].replace('>', '').strip()
                        name = email['From'].split('<')[0].strip() if '<' in email['From'] else sender
                        if is_meeting_request(email['Snippet']):
                            schedule_google_calendar_meeting(sender, name, email['Snippet'])
                        else:
                            schedule_followup(sender, name, email['Snippet'])
                    summary = summarize_emails(emails)
                    client_socket.sendall(summary.encode('utf-8'))
                except Exception as e:
                    client_socket.sendall(f"Error: {str(e)}".encode('utf-8'))
            else:
                client_socket.sendall(b"Unknown command. Try 'get_emails'.")
    finally:
        print(f"[-] Closing connection with {address}")
        client_socket.close()

def start_server(host='127.0.0.1', port=8000):
    init_db()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen(5)
    print(f"[Email Meeting Server] Listening on {host}:{port}")
    while True:
        client_sock, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(client_sock, addr))
        thread.start()

if __name__ == "__main__":
    start_server()
