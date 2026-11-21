from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import json


from db import init_db, save_email, get_all_emails, get_digest, clear_db
from parser import parse_eml, apply_rules, load_rules

app = FastAPI(title="Email MVP")
BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))

init_db()
RULES = load_rules()  


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    rows = get_all_emails()
    digest = get_digest() if rows else None
    return templates.TemplateResponse("index.html", {
        "request": request, "rows": rows, "digest": digest,
    })


@app.post("/", response_class=HTMLResponse)
async def process(request: Request, files: list[UploadFile] = File(default=[])):
    for f in files:
        if not f.filename:
            continue
        try:
            raw = await f.read()
            if f.filename.lower().endswith(".eml"):
                email = parse_eml(raw)
            else:
                email = json.loads(raw)
            email["filename"] = f.filename
            email["rules_fired"] = apply_rules(email, RULES)
            save_email(email)
        except Exception as e:
            save_email({
                "filename": f.filename,
                "subject": "",
                "sender": "",
                "recipients": [],
                "classification": {"type": "ошибка", "confidence": 0},
                "attachments": [],
                "attachments_total_size": 0,
                "rules_fired": [f"PARSE_ERROR: {e}"],
            })
    return RedirectResponse("/", status_code=303)


@app.post("/clear")
async def clear():
    clear_db()
    return RedirectResponse("/", status_code=303)

