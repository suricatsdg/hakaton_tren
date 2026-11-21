from email import policy
from email.parser import BytesParser
from bs4 import BeautifulSoup
from pathlib import Path
import yaml

# ---------- Классификация ----------
KEYWORDS = {
    "отчёт":   ["отчёт", "отчет", "report", "сводка за", "статистика за"],
    "запрос":  ["прошу", "запрос", "request", "нужно", "требуется", "подскажите"],
    "реклама": ["unsubscribe", "отписаться", "акция", "скидка", "utm_", "промо"],
    "важное":  ["срочно", "важно", "critical", "urgent", "asap"],
}

def classify(text: str) -> dict:
    low = text.lower()
    scores = {t: sum(kw in low for kw in kws) for t, kws in KEYWORDS.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return {"type": "уведомление", "confidence": 0.5}
    total = sum(scores.values())
    return {"type": best, "confidence": round(scores[best] / total, 2)}

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

    return {
        "subject": subject,
        "sender": sender,
        "recipients": recipients,
        "attachments": attachments,
        "attachments_total_size": sum(sizes),
        "classification": classify(subject + "\n" + body),
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