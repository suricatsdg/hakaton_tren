from email import policy
from email.parser import BytesParser
from bs4 import BeautifulSoup
from pathlib import Path
import yaml
import re
from datetime import datetime
import dateparser

# ---------- Классификация ----------
# Паттерны для поиска. Если паттерн сложный — используем регулярку.
CLASSIFICATION_RULES = {
    "отчёт": {
        "patterns": [
            r"отч[её]т", r"сводк[аи]", r"статистик[аи]", r"report",
            r"во вложении", r"направляю", r"данные за"
        ],
        "weight": 1.0
    },
    "запрос": {
        "patterns": [
            r"прошу", r"запрос", r"необходимо", r"требуется", r"request",
            r"подскажите", r"уточните", r"можете ли", r"согласуйте"
        ],
        "weight": 1.0
    },
    "реклама": {
        "patterns": [
            r"unsubscribe", r"отписаться", r"акци[яи]", r"скидк[аи]", 
            r"utm_", r"промо", r"вебинар", r"спецпредложение", r"распродажа"
        ],
        "weight": 1.5  # Рекламу ловим с большим весом, чтобы она не просачивалась в другие типы
    },
    "важное": {
        "patterns": [
            r"срочно", r"важно", r"critical", r"urgent", r"asap",
            r"внимание", r"немедленно", r"приоритет"
        ],
        "weight": 1.2
    }
}

import re

def classify(subject: str, body: str) -> dict:
    # Приводим к нижнему регистру
    subject_low = subject.lower()
    body_low = body.lower()
    
    scores = {}
    
    for email_type, rule_data in CLASSIFICATION_RULES.items():
        score = 0
        for pattern in rule_data["patterns"]:
            
            if re.search(pattern, subject_low):
                score += 2 * rule_data["weight"]
            
            if re.search(pattern, body_low):
                score += 1 * rule_data["weight"]
        
        scores[email_type] = score

    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]
    
    if best_score == 0:
        return {"type": "уведомление", "confidence": 0.5}

    total_score = sum(scores.values())
    confidence = round(best_score / total_score, 2)
    
    return {"type": best_type, "confidence": confidence}

# ---------- Извлечение тела (bs4) ----------
def extract_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_content()
                except Exception:
                    pass
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    soup = BeautifulSoup(part.get_content(), "html.parser")
                    for tag in soup(["script", "style"]):
                        tag.decompose()
                    return soup.get_text(separator=" ", strip=True)
                except Exception:
                    pass
    else:
        try:
            content = msg.get_content()
            if msg.get_content_type() == "text/html":
                soup = BeautifulSoup(content, "html.parser")
                for tag in soup(["script", "style"]):
                    tag.decompose()
                return soup.get_text(separator=" ", strip=True)
            return content
        except Exception:
            pass
    return ""

# ---------- Парсинг EML ----------
def parse_eml(raw: bytes) -> dict:
    msg = BytesParser(policy=policy.default).parsebytes(raw)

    recipients = []
    for h in ("To", "Cc"):
        val = msg.get(h)
        if val:
            recipients += [a.strip() for a in str(val).split(",") if a.strip()]

    subject = str(msg.get("Subject", ""))
    sender = str(msg.get("From", ""))

    attachments, sizes = [], []
    for part in msg.walk():
        if part.get_content_disposition() == "attachment":
            payload = part.get_payload(decode=True) or b""
            attachments.append(part.get_filename() or "unnamed")
            sizes.append(len(payload))

    body = extract_body(msg)
    deadline = extract_deadline(body + " " + subject)

    return {
        "subject": subject,
        "sender": sender,
        "recipients": recipients,
        "attachments": attachments,
        "attachments_total_size": sum(sizes),
        "classification": classify(subject, body),
        "deadline": deadline,
    }

# ---------- Правила ----------
RULES_PATH = Path(__file__).parent / "rules.yaml"

def load_rules() -> list:
    if not RULES_PATH.exists():
        return []
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("rules", [])

def apply_rules(email: dict, rules: list) -> list:
    fired = []
    for r in rules:
        c = r.get("condition", {})
        ok = True
        if "type" in c and c["type"] != email["classification"]["type"]:
            ok = False
        if "has_attachments" in c and bool(email["attachments"]) != c["has_attachments"]:
            ok = False
        if ok:
            fired.append(r["name"])
    return fired


import re
import dateparser

def extract_deadline(text: str):
    context_patterns = [
        # "до 25.12.2024" или "до 25.12.24"
        r'(?:до|к|дедлайн|срок|не позднее)\s+(\d{2}\.\d{2}\.\d{2,4})',
        # "до 2024-12-25"
        r'(?:до|к|дедлайн|срок|не позднее)\s+(\d{4}-\d{2}-\d{2})',
        # "до 25 декабря 2024" (или без года)
        r'(?:до|к|дедлайн|срок|не позднее)\s+(\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)(?:\s+\d{4})?)'
    ]
    
    for pattern in context_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)


    relative_patterns = [
        r'\b(сегодня|завтра|послезавтра)\b',
        r'\b(через\s+\d+\s+(?:день|дня|дней|недел[юи]))\b',
        r'\b(до конца (?:дня|недели|месяца))\b'
    ]
    
    for pattern in relative_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            phrase = match.group(1)
            parsed_date = dateparser.parse(phrase, languages=['ru'])
            if parsed_date:
                return parsed_date.strftime("%d.%m.%Y")
            return f"~ {phrase}"
            
    return None