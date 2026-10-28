import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

import config
from main import ResumeSession

app = FastAPI()
# Constant thread for local use
session = ResumeSession()


class ChatInput(BaseModel):
    message: str


class JobInput(BaseModel):
    text: str


PAGE = """
<!DOCTYPE html>
<html>
    <head>
        <meta charset="utf-8">
        <title>Resume AI</title>
        <style>
            body { font-family: sans-serif; max-width: 760px; margin: auto; padding: 20px; }
            #chat { height: 420px; overflow-y: auto; border: 1px solid #ccc; padding: 10px; margin-bottom: 10px; }
            #chat p { white-space: pre-wrap; margin: 6px 0; }
            textarea { width: 100%; height: 140px; }
            .row { display: flex; gap: 8px; margin: 8px 0; flex-wrap: wrap; }
            #msg { flex: 1; }
        </style>
    </head>
    <body>
        <div id="chat"></div>
        <div class="row">
            <input type="text" id="msg" placeholder="Answer the question, or type 'generate'">
            <button onclick="send()">Send</button>
        </div>
        <div class="row">
            <button onclick="post('/generate')">Generate resume</button>
            <a href="/resume.html" target="_blank">Preview HTML</a>
            <a href="/resume.pdf" target="_blank">Download PDF</a>
            <a href="/resume.md" target="_blank">Markdown</a>
            <button onclick="downloadTranscript()">Save conversation</button>
        </div>
        <h3>Target job (optional)</h3>
        <textarea id="job" placeholder="Paste a job description to check suitability and tailor the resume"></textarea>
        <div class="row">
            <button onclick="post('/job', {text: document.getElementById('job').value})">Analyze job</button>
            <button onclick="post('/match')">Re-check match</button>
        </div>
        <script>
            const transcript = [];
            function add(who, text) {
                const chat = document.getElementById('chat');
                const p = document.createElement('p');
                const b = document.createElement('b');
                b.textContent = who + ': ';
                p.appendChild(b);
                p.appendChild(document.createTextNode(text));
                chat.appendChild(p);
                chat.scrollTop = chat.scrollHeight;
                transcript.push(who + ': ' + text);
            }
            async function post(url, body) {
                const res = await fetch(url, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(body || {})
                });
                const data = await res.json();
                add('AI', data.response || data.detail || 'Something went wrong');
            }
            async function send() {
                const input = document.getElementById('msg');
                const text = input.value.trim();
                if (!text) return;
                add('You', text);
                input.value = '';
                await post('/chat', {message: text});
            }
            document.getElementById('msg').addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
            function downloadTranscript() {
                const blob = new Blob([transcript.join('\\n')], {type: 'text/plain'});
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = 'conversation.txt';
                a.click();
            }
        </script>
    </body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def get():
    return PAGE


@app.post("/chat")
def chat(input_data: ChatInput):
    return {"response": session.handle(input_data.message)}


@app.post("/job")
def job(input_data: JobInput):
    if not input_data.text.strip():
        raise HTTPException(status_code=400, detail="Paste a job description first.")
    return {"response": session.load_job(input_data.text)}


@app.post("/match")
def match():
    return {"response": session.match()}


@app.post("/generate")
def generate():
    return {"response": session.generate()}


@app.get("/facts")
def facts():
    return session.state().facts.model_dump(exclude_defaults=True)


def _file(path: str, media_type: str):
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="No resume generated yet. Click 'Generate resume' first.")
    return FileResponse(path, media_type=media_type)


@app.get("/resume.html")
def resume_html():
    return _file(config.RESUME_HTML_PATH, "text/html")


@app.get("/resume.pdf")
def resume_pdf():
    return _file(config.RESUME_PDF_PATH, "application/pdf")


@app.get("/resume.md")
def resume_md():
    return _file(config.RESUME_OUTPUT_PATH, "text/markdown")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
