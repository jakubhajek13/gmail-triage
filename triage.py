#!/usr/bin/env python3
"""
Email Triage, Draft Generation, and Digest Builder using Anthropic Claude & Gmail API.
"""

import base64
import html
import json
import os
import sys
from datetime import date
from email.mime.text import MIMEText
from email.utils import parseaddr
from urllib.parse import quote

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import anthropic

import config

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
CREDENTIALS_FILE = "credentials.json"

anthropic_client = anthropic.Anthropic()


def _text_from(resp):
    """Extract text from model response, handling thinking blocks if present."""
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            return block.text
    for block in resp.content:
        if hasattr(block, "text"):
            return block.text
    return ""


def get_service(token_file):
    """Authenticate with Gmail API; opens local browser on first run."""
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def ensure_labels(service):
    """Ensure all required labels exist in Gmail. Returns name -> id map."""
    existing = {}
    resp = service.users().labels().list(userId="me").execute()
    for lbl in resp.get("labels", []):
        existing[lbl["name"]] = lbl["id"]

    wanted = [config.PROCESSED_LABEL] + [
        config.LABEL_PREFIX + name for name in config.CATEGORIES
    ]
    for name in wanted:
        if name not in existing:
            created = (
                service.users()
                .labels()
                .create(
                    userId="me",
                    body={
                        "name": name,
                        "labelListVisibility": "labelShow",
                        "messageListVisibility": "show",
                    },
                )
                .execute()
            )
            existing[name] = created["id"]
    return existing


def fetch_new_messages(service):
    """Return IDs of unprocessed inbox messages within lookback days."""
    query = f'in:inbox -label:"{config.PROCESSED_LABEL}" newer_than:{config.LOOKBACK_DAYS}d'
    ids = []
    page_token = None
    while len(ids) < config.MAX_PER_ACCOUNT:
        resp = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=min(100, config.MAX_PER_ACCOUNT - len(ids)),
                pageToken=page_token,
            )
            .execute()
        )
        ids.extend(m["id"] for m in resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return ids


def _decode_body(payload):
    """Recursively extract plain text from email payload."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        raw = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "ignore")
        return raw
    for part in payload.get("parts", []) or []:
        text = _decode_body(part)
        if text:
            return text
    return ""


def get_message_details(service, msg_id):
    """Fetch message headers, snippet, and body snippet."""
    msg = (
        service.users()
        .messages()
        .get(userId="me", id=msg_id, format="full")
        .execute()
    )
    headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
    body = _decode_body(msg["payload"])[:2500]
    return {
        "id": msg_id,
        "thread_id": msg["threadId"],
        "subject": headers.get("subject", "(bez předmětu)"),
        "from": headers.get("from", ""),
        "message_id": headers.get("message-id", ""),
        "snippet": msg.get("snippet", ""),
        "body": body,
    }


def apply_labels(service, msg_id, add_ids, remove_ids=None):
    body = {"addLabelIds": add_ids}
    if remove_ids:
        body["removeLabelIds"] = remove_ids
    service.users().messages().modify(userId="me", id=msg_id, body=body).execute()


def create_reply_draft(service, mail, reply_text):
    """Create a draft reply in the same thread."""
    to_addr = parseaddr(mail["from"])[1]
    if "@" not in to_addr:
        raise ValueError(f"neplatná adresa odesílatele: {mail['from']!r}")
    mime = MIMEText(reply_text, _charset="utf-8")
    mime["To"] = to_addr
    subject = mail["subject"]
    mime["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if mail["message_id"]:
        mime["In-Reply-To"] = mail["message_id"]
        mime["References"] = mail["message_id"]
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    service.users().drafts().create(
        userId="me",
        body={"message": {"raw": raw, "threadId": mail["thread_id"]}},
    ).execute()


# ----------------------------------------------------------------------------
# Model – klasifikace a psaní konceptu
# ----------------------------------------------------------------------------
def classify(mail):
    """Classify email category, determine if reply is needed, and summarize."""
    cat_list = "\n".join(
        f'- "{name}": {c["popis"]}' for name, c in config.CATEGORIES.items()
    )
    prompt = (
        "Jsi asistent pro třídění firemní pošty. Zařaď e-mail do PRÁVĚ JEDNÉ kategorie "
        "a rozhodni, zda volá po odpovědi.\n\n"
        f"Kategorie:\n{cat_list}\n\n"
        f"Od: {mail['from']}\n"
        f"Předmět: {mail['subject']}\n"
        f"Text:\n{mail['body']}\n\n"
        "Odpověz POUZE ve formátu JSON bez dalšího textu:\n"
        '{"category": "<název kategorie>", "needs_reply": true/false, '
        '"summary": "<jednou větou česky, o co jde>"}'
    )
    resp = anthropic_client.messages.create(
        model=config.MODEL_CLASSIFY,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    text = _text_from(resp).strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
    data = json.loads(text)
    if data.get("category") not in config.CATEGORIES:
        data["category"] = "Ostatni"
    return data


def write_draft(mail, category):
    template = config.CATEGORIES[category].get("sablona")
    if not template:
        return None
    prompt = (
        "Napiš KONCEPT odpovědi na tento e-mail. Odpověď bude kontrolovat člověk, "
        "než ji odešle.\n\n"
        "STYL – piš jako reálný člověk z menší české technické firmy, NE jako "
        "korporátní šablona nebo AI:\n"
        "- Krátce a k věci, ideálně 2–5 vět. Žádná vata ani zdvořilostní balast.\n"
        "- Přirozená, jednoduchá čeština. Vyhni se květnatým frázím jako "
        "'samozřejmě jsme Vám plně k dispozici', 'nesmírně si vážíme', "
        "'dovolujeme si Vás informovat'.\n"
        "- Normální věty, žádné odrážky s pomlčkami ani přehnané strukturování.\n"
        "- Radši stručně a věcně než uhlazeně. Má to znít lidsky.\n"
        "- Ceny, termíny a čísla, která neznáš, nevymýšlej – napiš [doplnit].\n\n"
        f"Zaměření pro tuto kategorii: {template}\n\n"
        f"Od: {mail['from']}\n"
        f"Předmět: {mail['subject']}\n"
        f"Text:\n{mail['body']}\n\n"
        "Vrať POUZE text odpovědi (bez předmětu). Podpis nech jako [Jméno]."
    )
    resp = anthropic_client.messages.create(
        model=config.MODEL_DRAFT,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return _text_from(resp).strip()

def _mail_link(it, mailbox):
    base = "https://mail.google.com/mail/"
    if mailbox:
        base += "?authuser=" + quote(mailbox)
    return base + "#all/" + it.get("thread_id", "")


def _dedupe_by_thread(items):
    best = {}
    for it in items:
        tid = it.get("thread_id")
        score = (2 if it.get("drafted") else 0) + (1 if it.get("needs_reply") else 0)
        if tid not in best or score > best[tid][0]:
            best[tid] = (score, it)
    return [v[1] for v in best.values()]


def _render_item_html(it, mailbox):
    link = _mail_link(it, mailbox)
    cat = html.escape(it.get("category", ""))
    subj = html.escape(it.get("subject", "(bez předmětu)"))
    frm = html.escape(it.get("from", ""))
    summ = html.escape(it.get("summary", ""))
    koncept = (
        ' &nbsp;<b style="color:#137333">📝 koncept připraven</b>'
        if it.get("drafted") else ""
    )
    return (
        '<li style="margin:0 0 12px 0">'
        f'<b>[{cat}]</b> <a href="{link}" style="color:#1a73e8;text-decoration:none">{subj}</a>'
        f' — <span style="color:#666">{frm}</span>{koncept}'
        f'<br><span style="color:#555;font-size:13px">{summ}</span>'
        "</li>"
    )


def build_digest(account_name, items, mailbox=""):
    items = _dedupe_by_thread(items)
    today = date.today().isoformat()
    action = [it for it in items if it.get("needs_reply")]
    info = [it for it in items if not it.get("needs_reply")]

    p = ['<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#222;max-width:640px">']
    p.append(f'<h2 style="margin:0 0 2px">Souhrn pošty – {today}</h2>')
    p.append(f'<p style="color:#888;margin:0 0 18px">Zpracováno vláken: {len(items)}</p>')

    if action:
        p.append(f'<h3 style="margin:0 0 8px;color:#b06000">⚡ Vyžaduje akci ({len(action)})</h3>')
        p.append('<ul style="padding-left:18px;margin:0 0 20px">')
        p += [_render_item_html(it, mailbox) for it in action]
        p.append("</ul>")

    if info:
        p.append(f'<h3 style="margin:0 0 8px;color:#555">📋 K přehledu ({len(info)})</h3>')
        p.append('<ul style="padding-left:18px;margin:0">')
        p += [_render_item_html(it, mailbox) for it in info]
        p.append("</ul>")

    p.append("</div>")
    return "\n".join(p)

def deliver_digest(service, recipient, digest_md, account_name):
    if config.DIGEST_MODE == "file":
        safe = recipient.split("@")[0]
        fname = f"digest_{account_name}_{safe}_{date.today().isoformat()}.html"
        with open(fname, "w") as f:
            f.write(digest_md)
        print(f"  Digest for {recipient} saved to {fname}")
        return
    mime = MIMEText(digest_md, "html", "utf-8")
    mime["To"] = recipient
    mime["Subject"] = f"Email Digest – {date.today().isoformat()}"
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    if config.DIGEST_MODE == "send":
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        print(f"  Digest for {recipient} sent.")
    else:  # "draft"
        service.users().drafts().create(
            userId="me", body={"message": {"raw": raw}}
        ).execute()
        print(f"  Digest for {recipient} prepared as draft.")


def process_account(account):
    print(f"\n=== Mailbox: {account['name']} ===")
    service = get_service(account["token_file"])
    mailbox = service.users().getProfile(userId="me").execute().get("emailAddress", "")
    labels = ensure_labels(service)
    msg_ids = fetch_new_messages(service)
    print(f"  New emails: {len(msg_ids)}")

    items = []
    for msg_id in msg_ids:
        try:
            mail = get_message_details(service, msg_id)
            result = classify(mail)
            category = result["category"]

            chosen = labels[config.LABEL_PREFIX + category]
            label_ids = [chosen, labels[config.PROCESSED_LABEL]]
            remove_ids = [
                labels[config.LABEL_PREFIX + c]
                for c in config.CATEGORIES
                if labels[config.LABEL_PREFIX + c] != chosen
            ]
            if category in config.ARCHIVE_CATEGORIES:
                remove_ids.append("INBOX")
            apply_labels(service, msg_id, label_ids, remove_ids)

            drafted = False
            if result.get("needs_reply"):
                try:
                    draft_text = write_draft(mail, category)
                    if draft_text:
                        create_reply_draft(service, mail, draft_text)
                        drafted = True
                except Exception as e:
                    print(f"  ! Failed to create draft for {msg_id}: {e}", file=sys.stderr)

            items.append(
                {
                    "subject": mail["subject"],
                    "from": mail["from"],
                    "category": category,
                    "owner": config.CATEGORIES[category].get("owner"),
                    "summary": result.get("summary", ""),
                    "drafted": drafted,
                    "needs_reply": bool(result.get("needs_reply")),
                    "thread_id": mail["thread_id"],
                    "rfc_id": mail["message_id"],
                }
            )
            print(f"  [{category}] {mail['subject'][:60]}"
                  + ("  +draft" if drafted else ""))
        except Exception as e:
            print(f"Error processing message {msg_id}: {e}", file=sys.stderr)

    by_owner = {}
    for it in items:
        owner = it.get("owner")
        if not owner:
            continue
        by_owner.setdefault(owner, []).append(it)

    if not by_owner:
        print("  No emails for digest (all without owner / noise).")
    for owner, owner_items in by_owner.items():
        digest = build_digest(account["name"], owner_items, mailbox)
        deliver_digest(service, owner, digest, account["name"])

def main():
    for account in config.ACCOUNTS:
        try:
            process_account(account)
        except Exception as e:
            print(f"Failed to process account {account['name']}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()