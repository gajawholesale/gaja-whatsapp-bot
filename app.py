# app.py - GAJA WhatsApp Bot - MERGED (Warranty + Cashback + Fixed Flow)
import os
import sys
import logging
import json
import time
import re
import requests
from threading import Lock
from flask import Flask, request

print("GAJA BOT - MERGED: WARRANTY + CASHBACK + FIXED FLOW")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)
logger = logging.getLogger(__name__)
logger.info("GAJA BOT STARTING - MERGED BUILD")

# ==================== CONFIG ====================
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
PHONE_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "gaja-verify-123")
APPS_URL = os.getenv("APPS_SCRIPT_URL", "")
APPS_SECRET = os.getenv("APPS_SECRET", "")
GAJA_PHONE = os.getenv("GAJA_PHONE", "91444XXXXXX")
GAJA_SERVICE = "9791877654"  # Carpenter registration contact
CATALOG_URL = os.getenv("CATALOG_URL", "")
CATALOG_FILENAME = os.getenv("CATALOG_FILENAME", "GAJA-Catalogue.pdf")
PUMBLE_WEBHOOK = os.getenv("PUMBLE_WEBHOOK_URL", "")
SCHEME_IMAGES = [os.getenv(k) for k in ["SCHEME_IMG1","SCHEME_IMG2","SCHEME_IMG3","SCHEME_IMG4","SCHEME_IMG5"] if os.getenv(k)]

GRAPH = "https://graph.facebook.com/v20.0"
HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
SESSION_TIMEOUT = 180  # 3 minutes

# ==================== STORAGE ====================
sessions = {}
messages_seen = {}
lock = Lock()

def save_session(phone, data):
    with lock:
        sessions[phone] = {"data": data, "expires": time.time() + SESSION_TIMEOUT}

def get_session(phone):
    with lock:
        if phone in sessions and sessions[phone]["expires"] > time.time():
            return sessions[phone]["data"]
        # fresh default
        return {"lang": None, "state": "start"}

def already_seen(msg_id):
    if not msg_id:
        return False
    with lock:
        now = time.time()
        global messages_seen
        # cleanup entries older than 10 minutes
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
    if filename:
        doc["filename"] = filename
    payload = {"messaging_product": "whatsapp", "to": to, "type": "document", "document": doc}
    if caption:
        payload["document"]["caption"] = caption
    send(payload)

def send_image(to, url, caption=None):
    payload = {"messaging_product": "whatsapp", "to": to, "type": "image", "image": {"link": url}}
    if caption:
        payload["image"]["caption"] = caption
    send(payload)

# ==================== GENERIC APPS-SCRIPT API ====================
def api_call(action, params):
    """Generic API call to Apps Script / unified API"""
    if not APPS_URL:
        logger.error("APPS_URL is not configured.")
        return None
    try:
        params = dict(params)  # copy avoid side effects
        params["action"] = action
        if APPS_SECRET:
            params["secret"] = APPS_SECRET
        r = requests.get(APPS_URL, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"API CALL FAILED: {action} | {e}")
        return None

# ==================== WARRANTY HELPERS ====================
def verify_warranty_token(token):
    return api_call("verify_token", {"token": token})

def lookup_barcode(code):
    return api_call("lookup_barcode", {"code": code})

def register_warranty(token, barcode, phone):
    return api_call("register_warranty", {"token": token, "barcode": barcode, "phone": phone})

def get_care_instructions(category):
    return api_call("get_care_instructions", {"category": category})

def detect_warranty_token(text):
    """Detect token of form 'GAJA <8 chars>' (case-insensitive)"""
    if not text:
        return None
    match = re.match(r'^\s*GAJA\s+([A-Z0-9]{8})\s*$', text.upper())
    if match:
        return match.group(1)
    return None

def format_date(iso_date):
    """Format ISO date to readable format"""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
        return dt.strftime("%d %b %Y")
    except:
        return iso_date

def send_warranty_confirmation(to, lang, registration, product):
    """Send formatted warranty confirmation"""
    if lang == "en":
        msg = (
            "🎉 *WARRANTY REGISTERED SUCCESSFULLY!*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 *Product:* {product.get('sku_name', 'N/A')}\n"
            f"🏷️ *Category:* {product.get('category', 'N/A')}\n"
            f"🔢 *Product Code:* {product.get('internal_sku', 'N/A')}\n\n"
            f"⏰ *Warranty Period:* {registration.get('warranty_months', 0)} months\n"
            f"📅 *Valid Until:* {format_date(registration.get('expiry_date'))}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "*🛠️ CARE INSTRUCTIONS:*\n\n"
            f"{product.get('care_instructions', 'N/A')}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📞 *For Warranty Claims:*\n"
            f"Call: {GAJA_PHONE}\n\n"
            "✅ Your warranty is now active!\n"
            "Keep this message for future reference.\n\n"
            "Thank you for choosing GAJA! 🙏"
        )
    else:
        msg = (
            "🎉 *வாரன்டி வெற்றிகரமாக பதிவு செய்யப்பட்டது!*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 *பொருள்:* {product.get('sku_name', 'N/A')}\n"
            f"🏷️ *வகை:* {product.get('category', 'N/A')}\n"
            f"🔢 *பொருள் குறியீடு:* {product.get('internal_sku', 'N/A')}\n\n"
            f"⏰ *வாரன்டி காலம்:* {registration.get('warranty_months', 0)} மாதங்கள்\n"
            f"📅 *செல்லுபடியாகும் வரை:* {format_date(registration.get('expiry_date'))}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "*🛠️ பராமரிப்பு வழிமுறைகள்:*\n\n"
            f"{product.get('care_instructions', 'N/A')}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📞 *வாரன்டி கோரிக்கைக்கு:*\n"
            f"அழைக்கவும்: {GAJA_PHONE}\n\n"
            "✅ உங்கள் வாரன்டி இப்போது செயலில் உள்ளது!\n"
            "எதிர்கால குறிப்புக்காக இந்த செய்தியை வைத்திருங்கள்.\n\n"
            "GAJA-வை தேர்ந்தெடுத்ததற்கு நன்றி! 🙏"
        )
    send_text(to, msg)

def ask_for_barcode(frm, lang):
    msg = (
        "✅ Warranty token verified!\n\n"
        "📦 Next step: Enter the 6-digit code from your product's MRP sticker.\n\n"
        "Example: 528941\n\n"
        "Please type the 6-digit code:"
    ) if lang == "en" else (
        "✅ வாரன்டி டோக்கன் சரிபார்க்கப்பட்டது!\n\n"
        "📦 அடுத்த படி: உங்கள் பொருளின் MRP ஸ்டிக்கரில் உள்ள 6-இலக்க குறியீட்டை உள்ளிடவும்.\n\n"
        "உதாரணம்: 528941\n\n"
        "6-இலக்க குறியீட்டை தட்டச்சு செய்யவும்:"
    )
    send_text(frm, msg)

def handle_warranty_start(frm, session, token):
    logger.info(f"WARRANTY TOKEN DETECTED: {token} from {frm}")

    # set default language if missing
    if not session.get("lang"):
        session["lang"] = "en"

    status_msg = "⏳ Verifying your warranty token..." if session["lang"] == "en" else "⏳ உங்கள் வாரன்டி டோக்கனை சரிபார்க்கிறது..."
    send_text(frm, status_msg)

    result = verify_warranty_token(token)

    if not result:
        error = (
            f"❌ System error. Please try again later or call {GAJA_PHONE}"
        ) if session["lang"] == "en" else (
            f"❌ கணினி பிழை. பின்னர் முயற்சிக்கவும் அல்லது {GAJA_PHONE} அழைக்கவும்"
        )
        send_text(frm, error)
        with lock:
            if frm in sessions:
                del sessions[frm]
        return

    if not result.get("valid"):
        error = (
            "❌ Invalid warranty token!\n\n"
            "This token does not exist in our system.\n\n"
            f"Please check your warranty card or call {GAJA_PHONE}"
        ) if session["lang"] == "en" else (
            "❌ தவறான வாரன்டி டோக்கன்!\n\n"
            "இந்த டோக்கன் எங்கள் அமைப்பில் இல்லை.\n\n"
            f"உங்கள் வாரன்டி கார்டை சரிபார்க்கவும் அல்லது {GAJA_PHONE} அழைக்கவும்"
        )
        send_text(frm, error)
        with lock:
            if frm in sessions:
                del sessions[frm]
        return

    if not result.get("available"):
        error = (
            "❌ This warranty token is already registered!\n\n"
            "Each warranty card can only be used once.\n\n"
            f"For assistance, call {GAJA_PHONE}"
        ) if session["lang"] == "en" else (
            "❌ இந்த வாரன்டி டோக்கன் ஏற்கனவே பதிவு செய்யப்பட்டது!\n\n"
            "ஒவ்வொரு வாரன்டி கார்டும் ஒரு முறை மட்டுமே பயன்படுத்தப்படும்.\n\n"
            f"உதவிக்கு {GAJA_PHONE} அழைக்கவும்"
        )
        send_text(frm, error)
        with lock:
            if frm in sessions:
                del sessions[frm]
        return

    # token valid & available -> ask barcode
    session["warranty_token"] = token
    session["state"] = "awaiting_barcode"
    save_session(frm, session)
    ask_for_barcode(frm, session["lang"])

def handle_barcode_input(frm, session, raw_code):
    code = raw_code.strip()

    if not re.match(r'^\d{6}$', code):
        error = (
            "❌ Invalid code format!\n\n"
            "Please enter exactly 6 digits from your MRP sticker.\n\n"
            "Example: 528941"
        ) if session["lang"] == "en" else (
            "❌ தவறான குறியீடு வடிவம்!\n\n"
            "உங்கள் MRP ஸ்டிக்கரில் இருந்து சரியாக 6 இலக்கங்களை உள்ளிடவும்.\n\n"
            "உதாரணம்: 528941"
        )
        send_text(frm, error)
        ask_for_barcode(frm, session["lang"])
        return

    status_msg = "⏳ Looking up your product..." if session["lang"] == "en" else "⏳ உங்கள் பொருளைத் தேடுகிறது..."
    send_text(frm, status_msg)

    product = lookup_barcode(code)

    if not product or not product.get("found"):
        error = (
            f"❌ Product not found!\n\n"
            f"The code '{code}' is not in our system.\n\n"
            f"Please check the code and try again, or call {GAJA_PHONE}"
        ) if session["lang"] == "en" else (
            f"❌ பொருள் கிடைக்கவில்லை!\n\n"
            f"குறியீடு '{code}' எங்கள் அமைப்பில் இல்லை.\n\n"
            f"குறியீட்டை சரிபார்த்து மீண்டும் முயற்சிக்கவும், அல்லது {GAJA_PHONE} அழைக்கவும்"
        )
        send_text(frm, error)
        ask_for_barcode(frm, session["lang"])
        return

    status_msg = "⏳ Registering your warranty..." if session["lang"] == "en" else "⏳ உங்கள் வாரன்டியை பதிவு செய்கிறது..."
    send_text(frm, status_msg)

    result = register_warranty(session["warranty_token"], code, frm)

    if not result or not result.get("success"):
        error = (
            f"❌ Registration failed!\n\n"
            f"Please try again later or call {GAJA_PHONE}"
        ) if session["lang"] == "en" else (
            f"❌ பதிவு தோல்வியடைந்தது!\n\n"
            f"பின்னர் முயற்சிக்கவும் அல்லது {GAJA_PHONE} அழைக்கவும்"
        )
        send_text(frm, error)
        with lock:
            if frm in sessions:
                del sessions[frm]
        return

    # success -> send confirmation
    send_warranty_confirmation(frm, session["lang"], result, product)

    if PUMBLE_WEBHOOK:
        try:
            requests.post(PUMBLE_WEBHOOK, json={
                "text": f"WARRANTY | {frm} | Token: {session['warranty_token']} | Product: {product.get('sku_name')} | {result.get('warranty_months')}mo"
            }, timeout=5)
        except:
            pass

    with lock:
        if frm in sessions:
            del sessions[frm]

    logger.info(f"WARRANTY REGISTERED: {session.get('warranty_token')} | {frm} | {product.get('sku_name')}")

# ==================== CASHBACK FLOW (Carpenter) ====================
def fetch_months():
    try:
        params = {"action": "months", "latest": "3"}
        if APPS_SECRET: params["secret"] = APPS_SECRET
        r = requests.get(APPS_URL, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("months", [])[:3]
    except: 
        return None

def fetch_cashback(code, month):
    try:
        params = {"action": "cashback", "code": code, "month": month}
        if APPS_SECRET: params["secret"] = APPS_SECRET
        r = requests.get(APPS_URL, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except:
        return None

def ask_carpenter_code(to, lang):
    msg = "Please enter your Carpenter Code (e.g. ABC123)" if lang == "en" else "உங்கள் கார்பென்டர் கோடை உள்ளிடவும் (எ.கா. ABC123)"
    send_text(to, msg + "\n\nType 0 to go back")

def handle_carpenter_code(to, session, raw_code):
    code = raw_code.strip().upper()
    session["carpenter_code"] = code
    save_session(to, session)
    status_msg = "⏳ Checking available months..." if session["lang"]=="en" else "⏳ மாதங்கள் சரிபார்க்கப்படுகிறது..."
    send_text(to, status_msg)
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
    status_msg = "⏳ Fetching your cashback details..." if session["lang"]=="en" else "⏳ உங்கள் கேஷ்பேக் விவரங்கள் பெறப்படுகிறது..."
    send_text(to, status_msg)
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
            try:
                requests.post(PUMBLE_WEBHOOK, json={"text": f"CASHBACK | {to} | {session['carpenter_code']} | {month} | ₹{amt}"}, timeout=5)
            except:
                pass
    session.pop("months", None)
    session.pop("carpenter_code", None)
    session["state"] = "main"
    save_session(to, session)
    main_menu(to, session["lang"])

# ==================== MENUS ====================
def ask_language(to):
    send_buttons(to, "Welcome to GAJA!\n\nGAJA-விற்கு வரவேற்கிறோம்!\n\nPlease select your language / உங்கள் மொழியைத் தேர்ந்தெடுக்கவும்", [
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
def home(): 
    return "GAJA BOT LIVE - MERGED (WARRANTY + CASHBACK + FIXED FLOW)", 200

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
        entry = data.get("entry", [])
        if entry:
            changes = entry[0].get("changes", [])
            if changes:
                value = changes[0].get("value", {})
                messages = value.get("messages", [])
                if messages:
                    msg_id = messages[0].get("id")
    except Exception as e:
        logger.warning(f"Error extracting message ID: {e}")

    if msg_id and already_seen(msg_id):
        return "ok", 200

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if "messages" not in value:
                continue
            msg = value["messages"][0]
            frm = msg["from"]
            s = get_session(frm)
            logger.info(f"FROM {frm} | TYPE {msg['type']} | STATE {s.get('state')} | LANG {s.get('lang')}")

            # If no language set, force language selection (unless it's a language selection button)
            if s.get("lang") is None:
                # If this is a language selection button
                if msg["type"] == "interactive" and "button_reply" in msg["interactive"]:
                    btn = msg["interactive"]["button_reply"]["id"]
                    if btn.startswith("lang_"):
                        s["lang"] = "en" if btn == "lang_en" else "ta"
                        s["state"] = "main"
                        save_session(frm, s)
                        main_menu(frm, s["lang"])
                        return "ok", 200

                # If this is a WARRANTY TOKEN (GAJA + 8 chars)
                if msg["type"] == "text":
                    token = detect_warranty_token(msg["text"]["body"])
                    if token:
                        handle_warranty_start(frm, s, token)
                        return "ok", 200

                # Not language selection or warranty token -> show language menu
                ask_language(frm)
                return "ok", 200

            # Handle interactive button replies (after language set)
            if msg["type"] == "interactive" and "button_reply" in msg["interactive"]:
                btn = msg["interactive"]["button_reply"]["id"]

                if btn == "main_customer":
                    s["state"] = "main"
                    save_session(frm, s)
                    customer_menu(frm, s["lang"])

                elif btn == "main_carpenter":
                    s["state"] = "main"
                    save_session(frm, s)
                    carpenter_menu(frm, s["lang"])

                elif btn == "main_talk":
                    send_text(frm, "Thank you! We'll call you soon." if s["lang"]=="en" else "நன்றி! விரைவில் அழைக்கிறோம்.")
                    main_menu(frm, s["lang"])

                elif btn == "cust_catalog":
                    if CATALOG_URL:
                        status = "📄 Sending catalogue..." if s["lang"]=="en" else "📄 கேட்டலாக் அனுப்பப்படுகிறது..."
                        send_text(frm, status)
                        send_document(frm, CATALOG_URL, caption="Latest GAJA Catalogue", filename=CATALOG_FILENAME)
                        confirm = "✅ Catalogue sent successfully!" if s["lang"]=="en" else "✅ கேட்டலாக் வெற்றிகரமாக அனுப்பப்பட்டது!"
                        send_text(frm, confirm)
                    else:
                        error = f"❌ Catalogue temporarily unavailable.\nPlease call {GAJA_PHONE}" if s["lang"]=="en" else f"❌ கேட்டலாக் தற்காலிகமாக கிடைக்கவில்லை.\nதயவுசெய்து {GAJA_PHONE} அழைக்கவும்"
                        send_text(frm, error)
                    customer_menu(frm, s["lang"])

                elif btn in ["back_to_main", "cust_back"]:
                    s["state"] = "main"
                    save_session(frm, s)
                    main_menu(frm, s["lang"])

                elif btn == "carp_register":
                    reg_msg = (
                        f"📝 *Carpenter Registration*\n\n"
                        f"To register as a GAJA Carpenter, please contact:\n\n"
                        f"📞 GAJA Service: {GAJA_SERVICE}\n\n"
                        f"Our team will assist you with the registration process!"
                    ) if s["lang"]=="en" else (
                        f"📝 *கார்பென்டர் பதிவு*\n\n"
                        f"GAJA கார்பென்டராக பதிவு செய்ய, தொடர்பு கொள்ளவும்:\n\n"
                        f"📞 GAJA சேவை: {GAJA_SERVICE}\n\n"
                        f"எங்கள் குழு உங்களுக்கு பதிவு செயல்முறையில் உதவும்!"
                    )
                    send_text(frm, reg_msg)
                    carpenter_menu(frm, s["lang"])

                elif btn == "carp_cashback":
                    s["state"] = "awaiting_code"
                    save_session(frm, s)
                    ask_carpenter_code(frm, s["lang"])

                elif btn == "carp_scheme":
                    if SCHEME_IMAGES:
                        status = "📸 Sending scheme details..." if s["lang"]=="en" else "📸 ஸ்கீம் விவரங்கள் அனுப்பப்படுகிறது..."
                        send_text(frm, status)
                        for url in SCHEME_IMAGES[:5]:
                            send_image(frm, url)
                        confirm = "✅ Scheme details sent!" if s["lang"]=="en" else "✅ ஸ்கீம் விவரங்கள் அனுப்பப்பட்டது!"
                        send_text(frm, confirm)
                    else:
                        error = f"❌ Scheme images unavailable.\nPlease call {GAJA_PHONE}" if s["lang"]=="en" else f"❌ ஸ்கீம் படங்கள் கிடைக்கவில்லை.\nதயவுசெய்து {GAJA_PHONE} அழைக்கவும்"
                        send_text(frm, error)
                    carpenter_menu(frm, s["lang"])

                return "ok", 200

            # List reply (month selection)
            if msg["type"] == "interactive" and msg["interactive"].get("type") == "list_reply":
                list_id = msg["interactive"]["list_reply"]["id"]
                if s.get("state") == "awaiting_month":
                    handle_month_selection(frm, s, list_id)
                return "ok", 200

            # Text message handling
            if msg["type"] == "text":
                text_raw = msg["text"]["body"]
                text = text_raw.strip().lower()

                # If user sends GAJA token at any time (language already set)
                token = detect_warranty_token(text_raw)
                if token:
                    handle_warranty_start(frm, s, token)
                    return "ok", 200

                # Force end session commands
                if text in ["exit", "close", "quit", "bye", "stop"]:
                    with lock:
                        if frm in sessions:
                            del sessions[frm]
                    goodbye = (
                        "👋 Session ended. Thank you for contacting GAJA!\n\nType 'hi' anytime to restart."
                    ) if s.get("lang") == "en" else (
                        "👋 உரையாடல் முடிந்தது. GAJA-வை தொடர்பு கொண்டதற்கு நன்றி!\n\nமீண்டும் தொடங்க 'hi' என தட்டச்சு செய்யவும்."
                    )
                    send_text(frm, goodbye)
                    logger.info(f"SESSION ENDED by user: {frm}")
                    return "ok", 200

                # Reset / menu commands
                if text in ["0", "menu", "back", "main", "home"]:
                    s["state"] = "main"
                    save_session(frm, s)
                    main_menu(frm, s["lang"])
                    return "ok", 200

                # Fresh start commands
                if text in ["hi", "hello", "start"]:
                    s = {"lang": None, "state": "start"}
                    save_session(frm, s)
                    ask_language(frm)
                    return "ok", 200

                # Warranty barcode input flow
                if s.get("state") == "awaiting_barcode":
                    handle_barcode_input(frm, s, text_raw)
                    return "ok", 200

                # Carpenter code input flow
                if s.get("state") == "awaiting_code":
                    handle_carpenter_code(frm, s, text_raw)
                    return "ok", 200

                # Default fallback
                fallback = (
                    "I didn't understand that. 🤔\n\nHere's the main menu:"
                ) if s["lang"]=="en" else (
                    "புரியவில்லை. 🤔\n\nஇதோ முகப்பு மெனு:"
                )
                send_text(frm, fallback)
                main_menu(frm, s["lang"])
                return "ok", 200

    return "ok", 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
