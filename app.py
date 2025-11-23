import os
import sys
import logging

# Setup logging FIRST
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

logger.info("=" * 50)
logger.info("STARTING GAJA BOT")
logger.info("=" * 50)

try:
    import requests
    logger.info("✓ requests imported")
except Exception as e:
    logger.error(f"✗ Failed to import requests: {e}")
    sys.exit(1)

try:
    import json
    logger.info("✓ json imported")
except Exception as e:
    logger.error(f"✗ Failed to import json: {e}")
    sys.exit(1)

try:
    from flask import Flask, request
    logger.info("✓ Flask imported")
except Exception as e:
    logger.error(f"✗ Failed to import Flask: {e}")
    sys.exit(1)

try:
    from datetime import datetime
    import time
    from threading import Lock
    logger.info("✓ datetime, time, threading imported")
except Exception as e:
    logger.error(f"✗ Failed to import standard libraries: {e}")
    sys.exit(1)

# ========= ENV =========
logger.info("Loading environment variables...")
ACCESS_TOKEN    = os.getenv("ACCESS_TOKEN")
PHONE_ID        = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN    = os.getenv("VERIFY_TOKEN", "gaja-verify-123")
APPS_URL        = os.getenv("APPS_SCRIPT_URL")
APPS_SECRET     = os.getenv("APPS_SECRET", "")
GAJA_PHONE      = os.getenv("GAJA_PHONE", "+91-XXXXXXXXXX")
CATALOG_URL     = os.getenv("CATALOG_URL", "")
CATALOG_FILENAME= os.getenv("CATALOG_FILENAME", "GAJA-Catalogue.pdf")
PUMBLE_WEBHOOK  = os.getenv("PUMBLE_WEBHOOK_URL", "")

logger.info(f"ACCESS_TOKEN: {'SET' if ACCESS_TOKEN else 'NOT SET'}")
logger.info(f"PHONE_ID: {'SET' if PHONE_ID else 'NOT SET'}")
logger.info(f"VERIFY_TOKEN: {VERIFY_TOKEN}")
logger.info(f"APPS_URL: {'SET' if APPS_URL else 'NOT SET'}")

SCHEME_IMG_KEYS = ["SCHEME_IMG1","SCHEME_IMG2","SCHEME_IMG3","SCHEME_IMG4","SCHEME_IMG5"]
SCHEME_IMAGES   = [os.getenv(k, "") for k in SCHEME_IMG_KEYS if os.getenv(k, "")]

GRAPH   = "https://graph.facebook.com/v20.0"
HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type":"application/json"}

# ========= IN-MEMORY STORAGE =========
logger.info("Initializing in-memory storage...")
memory_sessions = {}
memory_messages = {}
session_lock = Lock()

def save_session(frm, s):
    with session_lock:
        memory_sessions[frm] = {
            'data': s,
            'expires': time.time() + (120 if s["state"] in ("lang","main") else 300)
        }

def sget(phone):
    with session_lock:
        current_time = time.time()
        expired = [k for k, v in memory_sessions.items() if v['expires'] < current_time]
        for k in expired:
            del memory_sessions[k]
        
        if phone in memory_sessions and memory_sessions[phone]['expires'] > current_time:
            s = memory_sessions[phone]['data']
        else:
            s = {"lang": "en", "state": "lang"}
        
        save_session(phone, s)
        return s

def already_processed(mid: str) -> bool:
    if not mid: return False
    with session_lock:
        current_time = time.time()
        expired = [k for k, v in memory_messages.items() if v < current_time]
        for k in expired:
            del memory_messages[k]
        
        if mid in memory_messages:
            return True
        
        memory_messages[mid] = current_time + 600
        return False

# ========= MESSAGING HELPERS =========
def send_text(to, body):
    try:
        requests.post(f"{GRAPH}/{PHONE_ID}/messages", headers=HEADERS,
            json={"messaging_product":"whatsapp","to":to,"text":{"body":body}}, timeout=15)
    except Exception as e:
        logger.error(f"Error sending text: {e}")

def send_interactive_buttons(to, body_text, buttons):
    if len(buttons) > 3:
        buttons = buttons[:3]
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body_text},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": btn["id"],
                            "title": btn["title"]
                        }
                    } for btn in buttons
                ]
            }
        }
    }
    
    try:
        requests.post(f"{GRAPH}/{PHONE_ID}/messages", headers=HEADERS, json=payload, timeout=15)
    except Exception as e:
        logger.error(f"Error sending buttons: {e}")

def send_interactive_list(to, body_text, button_text, sections):
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body_text},
            "action": {
                "button": button_text,
                "sections": sections
            }
        }
    }
    
    try:
        requests.post(f"{GRAPH}/{PHONE_ID}/messages", headers=HEADERS, json=payload, timeout=15)
    except Exception as e:
        logger.error(f"Error sending list: {e}")

def send_image(to, url, caption=None):
    payload = {"messaging_product":"whatsapp","to":to,"type":"image","image":{"link":url}}
    if caption: payload["image"]["caption"] = caption
    try:
        requests.post(f"{GRAPH}/{PHONE_ID}/messages", headers=HEADERS, json=payload, timeout=15)
    except Exception as e:
        logger.error(f"Error sending image: {e}")

def send_document(to, link, caption=None, filename=None):
    doc = {"link": link}
    if filename: doc["filename"] = filename
    payload = {"messaging_product":"whatsapp","to":to,"type":"document","document":doc}
    if caption: payload["document"]["caption"] = caption
    try:
        requests.post(f"{GRAPH}/{PHONE_ID}/messages", headers=HEADERS, json=payload, timeout=15)
    except Exception as e:
        logger.error(f"Error sending document: {e}")

def log_pumble(msg: str):
    if not PUMBLE_WEBHOOK: return
    try:
        requests.post(PUMBLE_WEBHOOK, json={"text": msg}, timeout=5)
    except Exception as e:
        logger.error(f"Error logging to Pumble: {e}")

# ========= UI MESSAGES =========
def invalid(to, lang):
    msg = "Invalid selection. Please try again." if lang=="en" else "தவறான தேர்வு. மீண்டும் முயற்சிக்கவும்."
    send_text(to, msg)

def ask_language(to):
    send_interactive_buttons(
        to,
        "Welcome to GAJA! Please select your language.\n\nGAJA-விற்கு வரவேற்கிறோம்! உங்கள் மொழியைத் தேர்ந்தெடுக்கவும்.",
        [
            {"id": "lang_en", "title": "English"},
            {"id": "lang_ta", "title": "தமிழ்"}
        ]
    )

def main_menu(to, lang):
    if lang == "en":
        send_interactive_buttons(
            to,
            "👋 Welcome! How can we help you today?",
            [
                {"id": "main_customer", "title": "🛒 Customer"},
                {"id": "main_carpenter", "title": "🔨 Carpenter"},
                {"id": "main_talk", "title": "💬 Talk to Us"}
            ]
        )
    else:
        send_interactive_buttons(
            to,
            "👋 வணக்கம்! இன்று நாங்கள் உங்களுக்கு எவ்வாறு உதவ முடியும்?",
            [
                {"id": "main_customer", "title": "🛒 வாடிக்கையாளர்"},
                {"id": "main_carpenter", "title": "🔨 கார்பென்டர்"},
                {"id": "main_talk", "title": "💬 எங்களிடம் பேசுங்கள்"}
            ]
        )

def customer_menu(to, lang):
    if lang == "en":
        send_interactive_buttons(
            to,
            "📋 Customer Menu - What would you like to see?",
            [
                {"id": "cust_catalog", "title": "📖 View Catalogue"},
                {"id": "cust_back", "title": "⬅️ Back to Menu"}
            ]
        )
    else:
        send_interactive_buttons(
            to,
            "📋 வாடிக்கையாளர் மெனு - நீங்கள் என்ன பார்க்க விரும்புகிறீர்கள்?",
            [
                {"id": "cust_catalog", "title": "📖 விவரப்பட்டியல்"},
                {"id": "cust_back", "title": "⬅️ மெனுவுக்குத் திரும்பு"}
            ]
        )

def carpenter_menu(to, lang):
    if lang == "en":
        send_interactive_buttons(
            to,
            "🔨 Carpenter Menu - Select an option:",
            [
                {"id": "carp_register", "title": "📝 Register"},
                {"id": "carp_scheme", "title": "💎 Scheme Info"},
                {"id": "carp_cashback", "title": "💰 Check Cashback"}
            ]
        )
    else:
        send_interactive_buttons(
            to,
            "🔨 கார்பென்டர் மெனு - ஒரு விருப்பத்தைத் தேர்ந்தெடுக்கவும்:",
            [
                {"id": "carp_register", "title": "📝 பதிவு"},
                {"id": "carp_scheme", "title": "💎 ஸ்கீம் தகவல்"},
                {"id": "carp_cashback", "title": "💰 கேஷ்பேக் சரிபார்க்கவும்"}
            ]
        )

def ask_code(to, lang):
    msg = ("Please type your Carpenter Code.\n\nExample: ABC123" if lang=="en" 
           else "உங்கள் கார்பென்டர் குறியீட்டை உள்ளிடவும்.\n\nஉதாரணம்: ABC123")
    send_text(to, msg)

def server_down_msg(lang):
    return (f"⛔ Our server is temporarily unavailable. Please try again later or call {GAJA_PHONE}"
            if lang=="en" else
            f"⛔ சர்வர் தற்காலிகமாக கிடைக்கவில்லை. பின்னர் முயற்சிக்கவும் அல்லது {GAJA_PHONE} அழைக்கவும்")

# ========= Apps Script API =========
def fetch_months(n=3):
    try:
        params = {"action":"months","latest":str(n)}
        if APPS_SECRET: params["secret"] = APPS_SECRET
        r2 = requests.get(APPS_URL, params=params, timeout=10)
        if not r2.ok: return None
        data = r2.json()
        return data.get("months", [])
    except Exception as e:
        logger.error(f"Error fetching months: {e}")
        return None

def fetch_cashback(code, month):
    try:
        params = {"action":"cashback","code":code,"month":month}
        if APPS_SECRET: params["secret"] = APPS_SECRET
        r2 = requests.get(APPS_URL, params=params, timeout=10)
        if not r2.ok: return None
        return r2.json()
    except Exception as e:
        logger.error(f"Error fetching cashback: {e}")
        return None

# ========= Flask App =========
logger.info("Initializing Flask app...")
app = Flask(__name__)

@app.get("/")
def health():
    logger.info("Health check endpoint called")
    return "GAJA bot running (No Redis) ✓", 200

@app.get("/webhook")
def verify():
    logger.info("Webhook verification called")
    if request.args.get("hub.mode")=="subscribe" and request.args.get("hub.verify_token")==VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "forbidden", 403

@app.post("/webhook")
def incoming():
    logger.info("Webhook POST received")
    data = request.get_json(silent=True) or {}
    
    try:
        msg = data["entry"][0]["changes"][0]["value"]["messages"][0]
        logger.info(f"Message from: {msg.get('from')}")
    except Exception as e:
        logger.error(f"Error parsing message: {e}")
        return "ok", 200

    mid = msg.get("id")
    if already_processed(mid):
        logger.info(f"Message {mid} already processed")
        return "ok", 200
    
    frm = msg["from"]
    s = sget(frm)
    
    if msg.get("type") == "interactive":
        interactive = msg.get("interactive", {})
        
        if interactive.get("type") == "button_reply":
            button_id = interactive.get("button_reply", {}).get("id", "")
            logger.info(f"Button clicked: {button_id}")
            return handle_button_click(frm, s, button_id)
        
        elif interactive.get("type") == "list_reply":
            list_id = interactive.get("list_reply", {}).get("id", "")
            logger.info(f"List item selected: {list_id}")
            return handle_list_click(frm, s, list_id)
    
    elif msg.get("type") == "text":
        text = (msg.get("text", {}).get("body") or "").strip()
        if not text: return "ok", 200
        
        logger.info(f"Text received: {text[:20]}...")
        
        if text.upper() in ("EXIT", "STOP"):
            with session_lock:
                if frm in memory_sessions:
                    del memory_sessions[frm]
            send_text(frm, "✅ Session ended. Send any message to start again.")
            return "ok", 200
        
        if text == "9":
            s["state"] = "lang"
            ask_language(frm)
            save_session(frm, s)
            return "ok", 200
        
        if s["state"] == "cb_code":
            return handle_carpenter_code_input(frm, s, text)
    
    return "ok", 200

# Import handlers (keep existing code)
def handle_button_click(frm, s, button_id):
    if button_id == "lang_en":
        s["lang"] = "en"
        s["state"] = "main"
        main_menu(frm, s["lang"])
        save_session(frm, s)
        return "ok", 200
    
    elif button_id == "lang_ta":
        s["lang"] = "ta"
        s["state"] = "main"
        main_menu(frm, s["lang"])
        save_session(frm, s)
        return "ok", 200
    
    elif button_id == "main_customer":
        s["state"] = "cust"
        customer_menu(frm, s["lang"])
        save_session(frm, s)
        return "ok", 200
    
    elif button_id == "main_carpenter":
        s["state"] = "carp"
        carpenter_menu(frm, s["lang"])
        save_session(frm, s)
        return "ok", 200
    
    elif button_id == "main_talk":
        msg = f"✅ A team member will contact you soon.\n📞 Or call us: {GAJA_PHONE}" if s["lang"]=="en" else f"✅ எங்கள் குழு உறுப்பினர் விரைவில் தொடர்பு கொள்வார்.\n📞 அல்லது எங்களை அழையுங்கள்: {GAJA_PHONE}"
        send_text(frm, msg)
        log_pumble(f"📞 Customer {frm} requested to talk to team")
        s["state"] = "main"
        save_session(frm, s)
        return "ok", 200
    
    elif button_id == "cust_catalog":
        if CATALOG_URL:
            send_document(frm, CATALOG_URL, "📖 GAJA Catalogue", CATALOG_FILENAME)
            log_pumble(f"📂 Catalogue sent to {frm}")
        else:
            send_text(frm, "Catalogue not available." if s["lang"]=="en" else "கையேடு கிடைக்கவில்லை.")
        return "ok", 200
    
    elif button_id == "cust_back":
        s["state"] = "main"
        main_menu(frm, s["lang"])
        save_session(frm, s)
        return "ok", 200
    
    elif button_id == "carp_register":
        msg = ("Please share your contact details:\n\n📱 Phone Number\n👤 Full Name\n📍 Location\n\nOur team will contact you for registration." 
               if s["lang"]=="en" else 
               "உங்கள் தொடர்பு விவரங்களைப் பகிரவும்:\n\n📱 தொலைபேசி எண்\n👤 முழு பெயர்\n📍 இடம்\n\nபதிவுக்கு எங்கள் குழு உங்களைத் தொடர்பு கொள்ளும்.")
        send_text(frm, msg)
        log_pumble(f"📝 Carpenter registration request from {frm}")
        return "ok", 200
    
    elif button_id == "carp_scheme":
        if SCHEME_IMAGES:
            for i, url in enumerate(SCHEME_IMAGES, 1):
                send_image(frm, url, f"🛠️ GAJA Scheme {i}/{len(SCHEME_IMAGES)}")
        else:
            send_text(frm, "Scheme info not available." if s["lang"]=="en" else "ஸ்கீம் தகவல் கிடைக்கவில்லை.")
        return "ok", 200
    
    elif button_id == "carp_cashback":
        s["state"] = "cb_code"
        ask_code(frm, s["lang"])
        save_session(frm, s)
        return "ok", 200
    
    else:
        invalid(frm, s["lang"])
        return "ok", 200

def handle_list_click(frm, s, list_id):
    if list_id.startswith("month_"):
        try:
            idx = int(list_id.split("_")[1])
            month = s["months"][idx]
        except:
            invalid(frm, s["lang"])
            return "ok", 200
        
        j = fetch_cashback(s["code"], month)
        
        if j is None:
            send_text(frm, server_down_msg(s["lang"]))
            s["state"] = "carp"
            carpenter_menu(frm, s["lang"])
            save_session(frm, s)
            return "ok", 200
        
        if not j.get("found"):
            msg = (f"❌ Code: {s['code']}\n📅 Month: {month}\n\nNo cashback recorded." 
                   if s["lang"]=="en" else 
                   f"❌ குறியீடு: {s['code']}\n📅 மாதம்: {month}\n\nபதிவு இல்லை.")
        else:
            name = j.get("name", "")
            amt = j.get("cashback_amount", 0)
            msg = (f"✅ Hello {name}!\n\n💰 Cashback: ₹{amt}\n📅 Month: {month}\n\n✨ Amount will be transferred at month end.\n📞 Questions? Call {GAJA_PHONE}"
                   if s["lang"]=="en" else
                   f"✅ வணக்கம் {name}!\n\n💰 கேஷ்பேக்: ₹{amt}\n📅 மாதம்: {month}\n\n✨ தொகை மாத இறுதியில் செலுத்தப்படும்.\n📞 கேள்விகள்? {GAJA_PHONE} அழைக்கவும்.")
            log_pumble(f"💰 Cashback query: {frm} | Code: {s['code']} | Month: {month} | Amount: ₹{amt}")
        
        send_text(frm, msg)
        s["state"] = "carp"
        carpenter_menu(frm, s["lang"])
        save_session(frm, s)
        return "ok", 200
    
    return "ok", 200

def handle_carpenter_code_input(frm, s, text):
    code = text.strip().upper()
    s["code"] = code
    
    months = fetch_months(3)
    
    if not months:
        send_text(frm, server_down_msg(s["lang"]))
        s["state"] = "carp"
        carpenter_menu(frm, s["lang"])
        save_session(frm, s)
        return "ok", 200
    
    s["months"] = months
    
    body_text = (f"✅ Code: {code}\n\nSelect a month to check cashback:" 
                 if s["lang"]=="en" else 
                 f"✅ குறியீடு: {code}\n\nகேஷ்பேக் சரிபார்க்க மாதத்தைத் தேர்ந்தெடுக்கவும்:")
    
    button_text = "Select Month" if s["lang"]=="en" else "மாதம் தேர்வு"
    
    sections = [{
        "title": "Available Months" if s["lang"]=="en" else "கிடைக்கும் மாதங்கள்",
        "rows": [
            {
                "id": f"month_{i}",
                "title": month,
                "description": "Click to view" if s["lang"]=="en" else "பார்க்க கிளிக் செய்யவும்"
            } for i, month in enumerate(months)
        ]
    }]
    
    send_interactive_list(frm, body_text, button_text, sections)
    
    s["state"] = "cb_month"
    save_session(frm, s)
    return "ok", 200

logger.info("Flask app initialized")
logger.info("=" * 50)

if __name__ == "__main__":
    try:
        port = int(os.getenv("PORT", "10000"))
        logger.info(f"🚀 Starting GAJA Bot on port {port}")
        logger.info(f"Access at: http://0.0.0.0:{port}")
        
        # Use Flask development server (simpler, more reliable)
        app.run(host="0.0.0.0", port=port, debug=False)
        
    except Exception as e:
        logger.error(f"FATAL ERROR starting server: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
