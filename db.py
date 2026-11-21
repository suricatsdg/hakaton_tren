import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "emails.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                subject TEXT,
                sender TEXT,
                recipients TEXT,
                email_type TEXT,
                confidence REAL,
                has_attachments INTEGER,
                attachments_size INTEGER,
                rules_fired TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

def save_email(email: dict):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO emails
            (filename, subject, sender, recipients, email_type, confidence,
             has_attachments, attachments_size, rules_fired)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            email.get("filename", ""),
            email.get("subject", ""),
            email.get("sender", ""),
            ", ".join(email.get("recipients", [])),
            email["classification"]["type"],
            email["classification"]["confidence"],
            int(bool(email.get("attachments"))),
            email.get("attachments_total_size", 0),
            ", ".join(email.get("rules_fired", [])),
        ))

def get_all_emails():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM emails ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [dict(r) for r in rows]

def get_digest():
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
        by_type = {
            r[0]: r[1] for r in conn.execute(
                "SELECT email_type, COUNT(*) FROM emails GROUP BY email_type"
            ).fetchall()
        }
        with_att = conn.execute(
            "SELECT COUNT(*) FROM emails WHERE has_attachments = 1"
        ).fetchone()[0]
        rules = conn.execute(
            "SELECT COUNT(*) FROM emails WHERE rules_fired != ''"
        ).fetchone()[0]
    return {
        "total": total,
        "by_type": by_type,
        "with_attachments": with_att,
        "rules_fired_total": rules,
    }

def clear_db():
    with get_conn() as conn:
        conn.execute("DELETE FROM emails")