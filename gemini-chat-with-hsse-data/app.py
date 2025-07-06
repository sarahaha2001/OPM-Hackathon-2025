from flask import Flask, render_template, request, jsonify, send_file
from dotenv import load_dotenv
import os
import json
import requests
from datetime import datetime

load_dotenv()

app = Flask(__name__)

# === Load HSSE JSON Data ===
with open("processed_articles_20250705_172810.json", "r", encoding="utf-8") as f:
    hsse_data = json.load(f)

dashboard_summary = hsse_data.get("dashboard_summary", "")
article_summaries = []

for i, article in enumerate(hsse_data.get("articles", [])):
    summary = article.get("gemini_summary", {})
    if isinstance(summary, dict):
        company = summary.get("company", "Unknown")
        incident_type = summary.get("type", "Unknown")
        summary_text = summary.get("summary", "")
        article_summaries.append(f"{i+1}. [{company}] ({incident_type}) - {summary_text}")

incident_summary_text = "\n".join(article_summaries)

# === Gemini API Setup ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
HEADERS = {
    "Content-Type": "application/json",
    "X-goog-api-key": GEMINI_API_KEY
}

def ask_gemini(user_prompt):
    prompt = f"""You are an HSSE incident analysis assistant. Only use the information provided below.

DASHBOARD SUMMARY:
{dashboard_summary.strip()}

INCIDENT SUMMARIES:
{incident_summary_text.strip()}

USER QUESTION:
{user_prompt}

Rules:
- Do NOT use outside knowledge.
- Only use this data to answer.
- If the question cannot be answered from the data, say so.
"""
    payload = {
        "contents": [
            {
                "parts": [
                    { "text": prompt }
                ]
            }
        ]
    }
    response = requests.post(GEMINI_URL, headers=HEADERS, json=payload)
    if response.status_code == 200:
        content = response.json().get("candidates", [{}])[0].get("content", {})
        parts = content.get("parts", [])
        return parts[0].get("text", "") if parts else "No answer found in data."
    return f"Error from Gemini: {response.status_code}"

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/ask', methods=['POST'])
def ask():
    user_input = request.json.get('message')
    response_text = ask_gemini(user_input)

    # Optional logic to include a file based on keywords
    file_info = None
    if any(kw in user_input.lower() for kw in ["summary", "report", "pdf"]):
        file_path = "static/sample_report.pdf"
        if os.path.exists(file_path):
            file_info = {
                "name": os.path.basename(file_path),
                "size": f"{os.path.getsize(file_path) // 1024} KB",
                "url": f"/static/{os.path.basename(file_path)}"
            }

    return jsonify({"response": response_text, "file": file_info})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True)
