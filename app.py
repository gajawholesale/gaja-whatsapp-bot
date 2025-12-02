# app.py - GAJA WhatsApp Bot - FINAL POLISHED VERSION (Dec 2025)
import os
import sys
import logging
import json
import time
import requests
from threading import Lock
from flask import Flask, request

print("GAJA BOT - FINAL POLISHED BUILD")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)
logger = logging.getLogger(__name__)
logger.info("GAJA BOT STARTING - NO DUPLICATES + BACK TO MENU")

# ==================== CONFIG ====================
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
PHONE_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "gaja-verify-123")
APPS_URL = os.getenv("APPS_SCRIPT_URL")
APPS_SECRET = os.getenv("APPS_SECRET", "")
GAJA_PHONE = os.getenv("GAJA_PHONE", "91444XXXXXX")
CATALOG_URL = os.getenv("CATALOG_URL", "")
CATALOG_FILENAME = os.getenv("CATALOG_FILENAME", "GAJA-Catalogue.pdf")
PUMBLE_WEBHOOK = os.getenv("PUMBLE_WEBHOOK_URL", "")
SCHEME_IMAGES = [os.getenv(k) for k in ["SCHEME_IMG1","SCHEME_IMG2","SCHEME_IMG3","SCHEME_IMG4","SCHEME_IMG5"] if os.getenv(k)]

GRAPH = "https://graph.facebook.com/v20.0"
HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}

# ==================== STORAGE ====================
sessions = {}
messages_seen = {}
lock = Lock()

def save_session(phone, data):
    with lock:
        sessions[phone] = {"data": data, "expires": time.time() + 1800}

def get_session(phone):
    with lock:
        if phone in sessions and sessions[phone]["expires"] > time.time():
            return sessions[phone]["data"]
        return {"lang": "en", "state": "start"}

def already_seen(msg_id):
    if not msg_id:
        return False
    with lock:
        now = time.time()
        # Auto cleanup old entries
        global messages_seen
        messages_seen = {k: v for k, v in messages_seen.items() if now - v < 600}
        if msg_id in messages_seen:
            logger.info(f"DUPLICATE IGNORED: {msg_id}")
            return True
        messages_seen[msg_id] = now
        return False

# ==================== SEND HELPERS ====================
def send(payload):
    url = f"{GRAPH}/{PHONE_ID}/messages"
    try:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=15)
        if r.status_code == 200:
            logger.info(f"SENT to {payload.get('to')} | {payload.get('type','text')}")
        else:
            logger.error(f"SEND FAILED {r.status_code} → {r.text[:500]}")
        return r.json()
    except Exception as e:
        logger.error(f"SEND EXCEPTION: {e}")
        return {"error": str(e)}

def send_text(to, body):
    send({"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}})

def send_buttons(to, body, buttons):
    send({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {"buttons": [{"type": "reply", "reply": {"id": b["id"], "title": b["title"]}} for b in buttons[:3]]}
        }
    })

def send_list(to, body, button_text, rows):
    send({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body},
            "action": {"button": button_text, "sections": [{"rows": rows}]}
        }
    })

def send_document(to, url, caption=None, filename=None):
    doc = {"link": url}
    if filename: doc["filename"] = filename
    payload = {"messaging_product": "whatsapp", "to": to, "type": "document", "document": doc}
    if caption: payload["document"]["caption"] = caption
    send(payload)

# ==================== CASHBACK FLOW ====================
def fetch_months():
    try:
        params = {"action": "months", "latest": "3"}
        if APPS_SECRET: params["secret"] = APPS_SECRET
        r = requests.get(APPS_URL, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("months", [])[:3]
    except: return None

def fetch_cashback(code, month):
    try:
        params = {"action": "cashback", "code": code, "month": month}
        if APPS_SECRET: params["secret"] = APPS_SECRET
        r = requests.get(APPS_URL, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except: return None

def ask_carpenter_code(to, lang):
    msg = "Please enter your Carpenter Code (e.g. ABC123)" if lang == "en" else "உங்கள் கார்பென்டர் கோடை உள்ளிடவும் (எ.கா. ABC123)"
    send_text(to, msg + "\n\nType 0 to go back")

def handle_carpenter_code(to, session, raw_code):
    code = raw_code.strip().upper()
    session["carpenter_code"] = code
    save_session(to, session)

    months = fetch_months()
    if not months:
        msg = f"Temporary issue. Please try later or call {GAJA_PHONE}" if session["lang"]=="en" else f"தற்காலிக பிரச்சனை. பின்னர் முயற்சிக்கவும் அல்லது {GAJA_PHONE} அழைக்கவும்"
        send_text(to, msg)
        return

    session["months"] = months
    session["state"] = "awaiting_month"
    save_session(to, session)

    title = f"Code: {code}\nSelect month:" if session["lang"]=="en" else f"கோடு: {code}\nமாதம் தேர்வு:"
    button = "Choose Month" if session["lang"]=="en" else "மாதம் தேர்வு"
    rows = [{"id": f"month_{i}", "title": m, "description": "Tap to check"} for i, m in enumerate(months)]
    send_list(to, title, button, rows)

def handle_month_selection(to, session, list_id):
    try:
        idx = int(list_id.split("_")[1])
        month = session["months"][idx]
    except:
        send_text(to, "Invalid selection.")
        return

    data = fetch_cashback(session["carpenter_code"], month)
    if not data:
        msg = f"Server down. Try later or call {GAJA_PHONE}" if session["lang"]=="en" else f"சர்வர் பழுது. பின்னர் முயற்சி அல்லது {GAJA_PHONE} அழைக்கவும்"
        send_text(to, msg)
    elif not data.get("found"):
        msg = f"Code: {session['carpenter_code']}\nMonth: {month}\n\nNo cashback recorded." if session["lang"]=="en" else f"கோடு: {session['carpenter_code']}\nமாதம்: {month}\n\nகேஷ்பேக் இல்லை."
        send_text(to, msg)
    else:
        name = data.get("name", "Carpenter")
        amt = data.get("cashback_amount", 0)
        msg = f"Hello {name}!\n\nCashback for {month}: ₹{amt}\n\nTransferred by month end.\nCall {GAJA_PHONE} for queries." if session["lang"]=="en" else f"வணக்கம் {name}!\n\n{month} கேஷ்பேக்: ₹{amt}\n\nமாத இறுதிக்குள் வரவு வைக்கப்படும்.\n{GAJA_PHONE} அழைக்கவும்."
        send_text(to, msg)
        if PUMBLE_WEBHOOK:
            requests.post(PUMBLE_WEBHOOK, json={"text": f"CASHBACK | {to} | {session['carpenter_code']} | {month} | ₹{amt}"}, timeout=5)

    session.pop("months", None)
    session.pop("carpenter_code", None)
    session["state"] = "main"
    save_session(to, session)
    main_menu(to, session["lang"])

# ==================== MENUS ====================
def ask_language(to):
    send_buttons(to, "Welcome to GAJA!\n\nGAJA-விற்கு வரவேற்கிறோம்! உங்கள் மொழியைத் தேர்ந்தெடுக்கவும்.", [
        {"id": "lang_en", "title": "English"},
        {"id": "lang_ta", "title": "தமிழ்"}
    ])

def main_menu(to, lang):
    body = "Welcome! How can we help you today?" if lang == "en" else "வணக்கம்! எப்படி உதவலாம்?"
    send_buttons(to, body, [
        {"id": "main_customer", "title": "Customer" if lang=="en" else "வாடிக்கையாளர்"},
        {"id": "main_carpenter", "title": "Carpenter" if lang=="en" else "கார்பென்டர்"},
        {"id": "main_talk", "title": "Talk to Us" if lang=="en" else "பேச வேண்டுமா?"}
    ])

def customer_menu(to, lang):
    send_buttons(to, "Customer Menu" if lang=="en" else "வாடிக்கையாளர் மெனு", [
        {"id": "cust_catalog", "title": "View Catalogue" if lang=="en" else "கேட்டலாக் பார்க்க"},
        {"id": "back_to_main", "title": "Back to Main" if lang=="en" else "முகப்புக்கு"}
    ])

def carpenter_menu(to, lang):
    footer = "\n\nType 0 or 'menu' anytime to go back" if lang=="en" else "\n\nஎப்போது வேண்டுமானாலும் 0 அல்லது 'menu' என தட்டச்சு செய்து முகப்புக்கு செல்லலாம்"
    send_buttons(to, ("Carpenter Menu" if lang=="en" else "கார்பென்டர் மெனு") + footer, [
        {"id": "carp_register", "title": "Register" if lang=="en" else "பதிவு"},
        {"id": "carp_scheme", "title": "Scheme Info" if lang=="en" else "ஸ்கீம்"},
        {"id": "carp_cashback", "title": "Check Cashback" if lang=="en" else "கேஷ்பேக்"}
    ])

# ==================== FLASK APP ====================
app = Flask(__name__)

@app.get("/")
def home(): return "GAJA BOT LIVE - NO DUPLICATES + BACK MENU", 200

@app.get("/webhook")
def verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "Forbidden", 403

@app.post("/webhook")
def webhook():
    data = request.get_json() or {}
    
    # Early duplicate detection
    msg_id = None
    try:
        msg_id = data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("messages", [{}])[0].get("id")
    except: pass
    if msg_id and already_seen(msg_id):
        return "ok", 200

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if "messages" not in value: continue
            msg = value["messages"][0]
            frm = msg["from"]

            s = get_session(frm)
            logger.info(f"FROM {frm} | TYPE {msg['type']} | STATE {s['state']} | LANG {s['lang']}")

            # Button reply
            if msg["type"] == "interactive" and "button_reply" in msg["interactive"]:
                btn = msg["interactive"]["button_reply"]["id"]

                if btn.startswith("lang_"):
                    s["lang"] = "en" if btn == "lang_en" else "ta"
                    s["state"] = "main"
                    save_session(frm, s)
                    main_menu(frm, s["lang"])

                elif btn == "main_customer":
                    s["state"] = "main"
                    save_session(frm, s)
                    customer_menu(frm, s["lang"])

                elif btn == "main_carpenter":
                    s["state"] = "main"
                    save_session(frm, s)
                    carpenter_menu(frm, s["lang"])

                elif btn == "main_talk":
                    send_text(frm, "Thank you! We’ll call you soon." if s["lang"]=="en" else "நன்றி! விரைவில் அழைக்கிறோம்.")
                    main_menu(frm, s["lang"])

                elif btn == "cust_catalog" and CATALOG_URL:
                    send_document(frm, CATALOG_URL, caption="Latest GAJA Catalogue", filename=CATALOG_FILENAME)
                    customer_menu(frm, s["lang"])

                elif btn in ["back_to_main", "cust_back"]:
                    s["state"] = "main"
                    save_session(frm, s)
                    main_menu(frm, s["lang"])

                elif btn == "carp_cashback":
                    s["state"] = "awaiting_code"
                    save_session(frm, s)
                    ask_carpenter_code(frm, s["lang"])

                elif btn == "carp_scheme" and SCHEME_IMAGES:
                    for url in SCHEME_IMAGES[:5]:
                        send({"messaging_product": "whatsapp", "to": frm, "type": "image", "image": {"link": url}})
                    carpenter_menu(frm, s["lang"])

                return "ok", 200

            # List reply (month selection)
            if msg["type"] == "interactive" and msg["interactive"]["type"] == "list_reply":
                list_id = msg["interactive"]["list_reply"]["id"]
                if s["state"] == "awaiting_month":
                    handle_month_selection(frm, s, list_id)
                return "ok", 200

            # Text message
            if msg["type"] == "text":
                text = msg["text"]["body"].strip().lower()

                if text in ["0", "menu", "back", "main", "home", "hi", "hello", "start"]:
                    s["state"] = "main"
                    save_session(frm, s)
                    if text in ["hi", "hello", "start"]:
                        ask_language(frm)
                    else:
                        main_menu(frm, s["lang"])
                    return "ok", 200

                if s["state"] == "awaiting_code":
                    handle_carpenter_code(frm, s, msg["text"]["body"])
                    return "ok", 200

                # Default fallback
                main_menu(frm, s["lang"])
                return "ok", 200

    return "ok", 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
