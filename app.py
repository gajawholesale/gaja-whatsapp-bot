# app.py - GAJA WhatsApp bot (full file)
import os
import sys
import logging
print("🚨 NEW BUILD LOADED 🚨")
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
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
PHONE_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "gaja-verify-123")
APPS_URL = os.getenv("APPS_SCRIPT_URL")
APPS_SECRET = os.getenv("APPS_SECRET", "")
GAJA_PHONE = os.getenv("GAJA_PHONE", "91XXXXXXXXXX")
CATALOG_URL = os.getenv("CATALOG_URL", "")
CATALOG_FILENAME= os.getenv("CATALOG_FILENAME", "GAJA-Catalogue.pdf")
PUMBLE_WEBHOOK = os.getenv("PUMBLE_WEBHOOK_URL", "")
logger.info(f"ACCESS_TOKEN: {'SET' if ACCESS_TOKEN else 'NOT SET'}")
logger.info(f"PHONE_ID: {'SET' if PHONE_ID else 'NOT SET'}")
logger.info(f"VERIFY_TOKEN: {VERIFY_TOKEN}")
logger.info(f"APPS_URL: {'SET' if APPS_URL else 'NOT SET'}")
SCHEME_IMG_KEYS = ["SCHEME_IMG1","SCHEME_IMG2","SCHEME_IMG3","SCHEME_IMG4","SCHEME_IMG5"]
SCHEME_IMAGES = [os.getenv(k, "") for k in SCHEME_IMG_KEYS if os.getenv(k, "")]
GRAPH = "https://graph.facebook.com/v20.0"
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
            'expires': time.time() + (120 if s.get("state") in ("lang","main") else 300)
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
# Unified _do_post returns a structured dict
def _do_post(payload):
    url = f"{GRAPH}/{PHONE_ID}/messages"
    logger.debug("Outgoing POST url: %s", url)
    logger.debug("Outgoing headers preview: %s", {k: HEADERS.get(k) for k in ('Authorization','Content-Type')})
    logger.debug("Outgoing payload preview: %s", payload)
    try:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=20)
        logger.info("POST %s -> %s", url, r.status_code)
        try:
            logger.debug("Response body: %s", r.text)
        except Exception:
            logger.debug("Could not decode response body")
        return {"ok": True, "status_code": r.status_code, "text": r.text}
    except Exception as e:
        logger.exception("Error doing POST to WhatsApp API: %s", e)
        return {"ok": False, "exception": str(e)}
def send_text(to, body):
    payload = {"messaging_product":"whatsapp","to":to,"text":{"body":body}}
    r = _do_post(payload)
    if not r.get("ok"):
        logger.error("send_text failed for %s: %s", to, r.get("exception"))
    elif r.get("status_code") and r["status_code"] >= 400:
        logger.error("send_text returned non-OK: %s %s", r.get("status_code"), r.get("text"))
    else:
        logger.info("Text sent to %s OK", to)
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
    r = _do_post(payload)
    if not r.get("ok"):
        logger.error("send_interactive_buttons failed for %s: %s", to, r.get("exception"))
    elif r.get("status_code") and r["status_code"] >= 400:
        logger.error("send_interactive_buttons returned non-OK: %s %s", r.get("status_code"), r.get("text"))
    else:
        logger.info("Buttons sent to %s OK", to)
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
    r = _do_post(payload)
    if not r.get("ok"):
        logger.error("send_interactive_list failed for %s: %s", to, r.get("exception"))
    elif r.get("status_code") and r["status_code"] >= 400:
        logger.error("send_interactive_list returned non-OK: %s %s", r.get("status_code"), r.get("text"))
    else:
        logger.info("List sent to %s OK", to)
def send_image(to, url, caption=None):
    payload = {"messaging_product":"whatsapp","to":to,"type":"image","image":{"link":url}}
    if caption: payload["image"]["caption"] = caption
    r = _do_post(payload)
    if not r.get("ok"):
        logger.error("send_image failed for %s: %s", to, r.get("exception"))
    elif r.get("status_code") and r["status_code"] >= 400:
        logger.error("send_image returned non-OK: %s %s", r.get("status_code"), r.get("text"))
    else:
        logger.info("Image sent to %s OK", to)
def send_document(to, link, caption=None, filename=None):
    doc = {"link": link}
    if filename: doc["filename"] = filename
    payload = {"messaging_product":"whatsapp","to":to,"type":"document","document":doc}
    if caption: payload["document"]["caption"] = caption
    r = _do_post(payload)
    if not r.get("ok"):
        logger.error("send_document failed for %s: %s", to, r.get("exception"))
    elif r.get("status_code") and r["status_code"] >= 400:
        logger.error("send_document returned non-OK: %s %s", r.get("status_code"), r.get("text"))
    else:
        logger.info("Document sent to %s OK", to)
# ========= misc helpers =========
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
    logger.info(f"Sending language selection to {to}")
    send_interactive_buttons(
        to,
        "Welcome to GAJA! Please select your language.\n\nGAJA-விற்கு வரவேற்கிறோம்! உங்கள் மொழியைத் தேர்ந்தெடுக்கவும்.",
        [
            {"id": "lang_en", "title": "English"},
            {"id": "lang_ta", "title": "தமிழ்"}
        ]
    )
def main_menu(to, lang):
    logger.info(f"Sending main menu to {to} in {lang}")
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
# ---------- Routes ----------
@app.get("/")
def health():
    logger.info("Health check endpoint called")
    return "GAJA bot running (No Redis) ✓", 200
@app.get("/debug")
def debug():
    env = {"ACCESS_TOKEN_set": bool(ACCESS_TOKEN), "PHONE_ID_set": bool(PHONE_ID)}
    results = {"env": env, "checks": {}}
    def safe_get(url, params=None):
        entry = {"url": url}
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=12)
            entry.update({"ok": True, "status_code": r.status_code, "text_preview": (r.text[:1000] if r.text else "")})
            logger.info("DEBUG GET %s -> %s", url, r.status_code)
        except Exception as e:
            entry.update({"ok": False, "exception": str(e)})
            logger.exception("DEBUG GET failed for %s : %s", url, e)
        return entry
    if PHONE_ID:
        results["checks"]["phone_id_get"] = safe_get(f"{GRAPH}/{PHONE_ID}", params={"fields":"id,display_phone_number"})
    else:
        results["checks"]["phone_id_get"] = {"ok": False, "reason": "PHONE_ID not set"}
    results["checks"]["me_get"] = safe_get(f"{GRAPH}/me")
    # optional: WABA listing if you set WABA_ID
    WABA_ID = os.getenv("WABA_ID", "")
    if WABA_ID:
        results["checks"]["waba_phone_numbers"] = safe_get(f"{GRAPH}/{WABA_ID}/phone_numbers")
        results["env"]["WABA_ID_preview"] = (WABA_ID[:8] + "..." if WABA_ID else None)
    else:
        results["checks"]["waba_phone_numbers"] = {"ok": False, "reason": "WABA_ID not set (optional)"}
    return results, 200
@app.get("/selftest")
def selftest():
    """
    This WILL perform an outgoing POST and return the response.
    """
    env = {"ACCESS_TOKEN_set": bool(ACCESS_TOKEN), "PHONE_ID_set": bool(PHONE_ID)}
    if not ACCESS_TOKEN or not PHONE_ID:
        return {"ok": False, "reason": "missing env", "env": env}, 400
    url = f"{GRAPH}/{PHONE_ID}/messages"
    to = os.getenv("SELFTEST_PHONE", GAJA_PHONE)
    payload = {"messaging_product": "whatsapp", "to": str(to),
               "text": {"body": "GAJA selftest at " + datetime.utcnow().isoformat() + "Z"}}
    logger.info("SELFTEST: posting test message to %s (to=%s)", url, to)
    try:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=20)
        logger.info("SELFTEST POST -> %s", r.status_code)
        logger.info("SELFTEST Response body: %s", r.text)
        return {"ok": True, "post_result": {"status_code": r.status_code, "text": r.text, "json": (r.json() if r.text else None)}}, 200
    except Exception as e:
        logger.exception("SELFTEST exception")
        return {"ok": False, "post_result": {"exception": str(e)}}, 500
# ---------- end routes ----------
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
    # Very verbose debug log of the payload (trimmed in logs if very large)
    try:
        logger.debug("Raw webhook payload: %s", json.dumps(data, ensure_ascii=False)[:4000])
    except Exception:
        logger.debug("Raw webhook payload (could not json.dumps)")
    # Try to locate a user message inside the usual nested structure:
    # entry -> changes -> value -> messages (array)
    msg = None
    frm = None
    mid = None
    msg_type = None
    try:
        entries = data.get("entry", []) if isinstance(data, dict) else []
        for entry in entries:
            changes = entry.get("changes", []) or []
            for change in changes:
                value = change.get("value", {}) or {}
                # If this change contains 'messages' (incoming message) use it
                if "messages" in value and isinstance(value["messages"], list) and value["messages"]:
                    msg = value["messages"][0]
                    # the sender phone is usually in msg['from'] or in value['metadata']['phone_number_id'] etc.
                    frm = msg.get("from") or value.get("metadata", {}).get("phone_number") or value.get("contacts", [{}])[0].get("wa_id")
                    mid = msg.get("id")
                    msg_type = msg.get("type")
                    # keep a reference to the entire 'value' for helper use later
                    change_value = value
                    break
                # Sometimes the update is a 'statuses' update (message delivery/read statuses)
                if "statuses" in value:
                    logger.info("Webhook contains status update (not a user message): %s", value.get("statuses"))
                    # we don't process delivery status here — just log and return 200
                    return "ok", 200
                # Other change types: contacts, etc.
                if "contacts" in value:
                    logger.info("Webhook contains contacts information: %s", value.get("contacts"))
                    # not a user chat to reply to
                    return "ok", 200
            if msg:
                break
        if not msg:
            # Nothing we can act on; it's not an incoming user message
            logger.error("Error parsing message: 'messages' not found in payload or messages empty")
            return "ok", 200
    except Exception as e:
        logger.exception("Exception while parsing webhook payload: %s", e)
        return "ok", 200
    # Dedup and session logic (same as before)
    if already_processed(mid):
        logger.info("Message %s already processed", mid)
        return "ok", 200
    # Ensure we have a 'from' value
    if not frm:
        logger.error("Could not determine sender (from) for message id %s", mid)
        return "ok", 200
    s = sget(frm)
    logger.info("Message from: %s, type: %s, id: %s", frm, msg_type, mid)
    logger.info(f"Current state for {frm}: {s.get('state')}, lang: {s.get('lang')}")
    # Handle interactive button/list replies if appropriate
    try:
        if msg_type == "interactive":
            interactive = msg.get("interactive", {})
            if interactive.get("type") == "button_reply":
                button_id = interactive.get("button_reply", {}).get("id", "")
                logger.info("Button clicked: %s", button_id)
                return handle_button_click(frm, s, button_id)
            elif interactive.get("type") == "list_reply":
                list_id = interactive.get("list_reply", {}).get("id", "")
                logger.info("List item selected: %s", list_id)
                return handle_list_click(frm, s, list_id)
        # If message is text
        if msg_type == "text":
            text = (msg.get("text", {}).get("body") or "").strip().lower()

            if not text:
                return "ok", 200

            logger.info("Text received: '%s' in state: %s", text, s.get("state"))

            # Universal commands
            if text in ("exit", "stop", "bye"):
                with session_lock:
                    if frm in memory_sessions:
                        del memory_sessions[frm]
                send_text(frm, "Session ended. Send any message to start again.")
                return "ok", 200

            if text in ("9", "menu", "hi", "hello", "start"):
                s["state"] = "lang"
                s["lang"] = "en"  # default, will be overridden if they choose
                save_session(frm, s)
                ask_language(frm)
                return "ok", 200

            # If waiting for carpenter code
            if s.get("state") == "cb_code":
                return handle_carpenter_code_input(frm, s, text.upper())

            # First message ever → force language selection
            if s.get("state") == "lang":
                ask_language(frm)
                save_session(frm, s)
                return "ok", 200

            # Any other text when already past language → treat as request for main menu
            main_menu(frm, s["lang"])
            save_session(frm, s)
            return "ok", 200
        # Non-text message types (image, audio, etc.) — log and optionally reply
        logger.info("Received non-text message type '%s' from %s; ignoring for now.", msg_type, frm)
        return "ok", 200
    except Exception as e:
        logger.exception("Unhandled exception processing message: %s", e)
        return "ok", 200
def handle_button_click(frm, s, button_id):
    lang = s.get("lang", "en")
    logger.info(f"Button clicked by {frm}: {button_id} | state: {s.get('state')}")

    # === LANGUAGE SELECTION ===
    if button_id.startswith("lang_"):
        new_lang = "en" if button_id == "lang_en" else "ta"
        s["lang"] = new_lang
        s["state"] = "main"
        save_session(frm, s)
        main_menu(frm, new_lang)
        return "ok", 200

    # === MAIN MENU ===
    if s.get("state") in ("lang", "main"):
        if button_id == "main_customer":
            s["state"] = "cust"
            save_session(frm, s)
            customer_menu(frm, lang)
        elif button_id == "main_carpenter":
            s["state"] = "carp"
            save_session(frm, s)
            carpenter_menu(frm, lang)
        elif button_id == "main_talk":
            msg = ("Thank you! We'll call you shortly on this number." 
                   if lang=="en" else "நன்றி! விரைவில் இந்த எண்ணில் அழைப்போம்.")
            send_text(frm, msg)
            log_pumble(f"Talk to us request from {frm}")
            s["state"] = "main"
            save_session(frm, s)
            main_menu(frm, lang)
        return "ok", 200

    # === CUSTOMER MENU ===
    if s.get("state") == "cust":
        if button_id == "cust_catalog":
            if CATALOG_URL:
                send_document(frm, CATALOG_URL, caption="GAJA Latest Catalogue", filename=CATALOG_FILENAME)
            else:
                send_text(frm, "Catalogue not available right now." if lang=="en" else "விவரப்பட்டியல் தற்போது கிடைக்கவில்லை.")
            customer_menu(frm, lang)  # send menu again
        elif button_id == "cust_back":
            s["state"] = "main"
            save_session(frm, s)
            main_menu(frm, lang)
        return "ok", 200

    # === CARPENTER MENU ===
    if s.get("state") == "carp":
        if button_id == "carp_register":
            send_text(frm, "Please visit our website or call us to register as carpenter." if lang=="en"
                           else "கார்பென்டராக பதிவு செய்ய எங்கள் வெப்சைட் செல்லவும் அல்லது அழைக்கவும்.")
            carpenter_menu(frm, lang)
        elif button_id == "carp_scheme":
            if SCHEME_IMAGES:
                # Send as album (max 10, but WhatsApp supports up to 10 images in one message)
                media_payloads = [
                    {"type": "image", "image": {"link": url}} for url in SCHEME_IMAGES[:10]
                ]
                payload = {
                    "messaging_product": "whatsapp",
                    "to": frm,
                    "type": "media",
                    "media": media_payloads[0] if len(media_payloads)==1 else media_payloads
                }
                if len(media_payloads) > 1:
                    payload["type"] = "album"  # WhatsApp now supports "album" type
                _do_post(payload)
            else:
                send_text(frm, "No scheme images configured." if lang=="en" else "ஸ்கீம் படங்கள் இல்லை.")
            carpenter_menu(frm, lang)
        elif button_id == "carp_cashback":
            s["state"] = "cb_code"
            save_session(frm, s)
            ask_code(frm, lang)
        return "ok", 200

    invalid(frm, lang)
    return "ok", 200
def handle_list_click(frm, s, list_id):
    if list_id.startswith("month_"):
        try:
            idx = int(list_id.split("_")[1])
            month = s["months"][idx]
            logger.info(f"Month selected: {month}")
        except Exception as e:
            logger.error(f"Error parsing month selection: {e}")
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
    logger.info(f"Carpenter code entered: {code}")
   
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
logger.info("Flask app initialized successfully")
logger.info("=" * 50)
if __name__ == "__main__":
    try:
        port = int(os.getenv("PORT", "10000"))
        logger.info(f"🚀 Starting GAJA Bot on port {port}")
        logger.info(f"Access at: http://0.0.0.0:{port}")
        logger.info("=" * 50)
       
        # Use Flask development server
        app.run(host="0.0.0.0", port=port, debug=False)
       
    except Exception as e:
        logger.error(f"FATAL ERROR starting server: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
