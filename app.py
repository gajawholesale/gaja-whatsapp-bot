import os, requests, time, json, traceback
from flask import Flask, request
import redis
from datetime import datetime

# ========= ENV =========
ACCESS_TOKEN    = os.getenv("ACCESS_TOKEN")
PHONE_ID        = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN    = os.getenv("VERIFY_TOKEN", "gaja-verify-123")
APPS_URL        = os.getenv("APPS_SCRIPT_URL")       # must end with /exec (no query)
APPS_SECRET     = os.getenv("APPS_SECRET", "")
GAJA_PHONE      = os.getenv("GAJA_PHONE", "+91-XXXXXXXXXX")
CATALOG_URL     = os.getenv("CATALOG_URL", "")
CATALOG_FILENAME= os.getenv("CATALOG_FILENAME", "GAJA-Catalogue.pdf")
PUMBLE_WEBHOOK  = os.getenv("PUMBLE_WEBHOOK_URL", "")

SCHEME_IMG_KEYS = ["SCHEME_IMG1","SCHEME_IMG2","SCHEME_IMG3","SCHEME_IMG4","SCHEME_IMG5"]
SCHEME_IMAGES   = [os.getenv(k, "") for k in SCHEME_IMG_KEYS if os.getenv(k, "")]

GRAPH   = "https://graph.facebook.com/v20.0"
HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type":"application/json"}

# ========= REDIS =========
REDIS_URL = os.getenv("REDIS_URL")
r = redis.from_url(REDIS_URL, decode_responses=True)

# ========= LOGGING =========
def log_pumble(msg: str):
    if not PUMBLE_WEBHOOK:
        return
    try:
        requests.post(PUMBLE_WEBHOOK, json={"text": msg}, timeout=5)
    except Exception as e:
        print("Pumble logging failed:", e)

def log_event(phone, state, flow_type, dup_count):
    msg = (f"📲 GAJA IVR Log\n"
           f"Phone: {phone}\n"
           f"Type: {flow_type}\n"
           f"End point: {state}\n"
           f"Duplicacy: {dup_count}")
    log_pumble(msg)

# ========= SESSION STORE =========
def sget(phone):
    key = f"sess:{phone}"
    s = r.get(key)
    if s:
        s = json.loads(s)
    else:
        s = {"lang": "en", "state": "lang"}
    s["last"] = time.time()
    ttl = 120 if s["state"] in ("lang","main") else 300
    r.setex(key, ttl, json.dumps(s))
    return s

# ========= DEDUP =========
def already_processed(mid: str) -> bool:
    if not mid:
        return False
    key = f"msg:{mid}"
    return not r.set(name=key, value="1", nx=True, ex=600)

# ========= CARPENTER LIMIT =========
def check_carpenter_limit(frm, text, state):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    dup_key = f"count:{today}:{frm}"
    bypass_key = f"bypass:{today}:{frm}"

    # BYPASS command
    if text.upper() == "BYPASS":
        r.set(bypass_key, "1", ex=86400)
        send_text(frm, "✅ Bypass activated. Limits skipped for today.")
        return False, 0

    # Only apply to carpenter/warranty/cashback states
    if not (state.startswith("carp") or state.startswith("cb")):
        return False, 0

    # Check bypass flag
    if r.get(bypass_key):
        return False, 0

    # Increment counter
    dup_count = r.incr(dup_key)
    r.expire(dup_key, 86400)

    if dup_count > 5:
        send_text(frm, f"⚠️ You have reached today’s query limit.\n"
                       f"Please contact GAJA for further support: {GAJA_PHONE}.")
        log_event(frm, state, "Carpenter", dup_count)
        return True, dup_count

    return False, dup_count

# ========= SEND HELPERS =========
def send_text(to, body):
    try:
        r2 = requests.post(
            f"{GRAPH}/{PHONE_ID}/messages",
            headers=HEADERS,
            json={"messaging_product":"whatsapp","to":to,"text":{"body":body}},
            timeout=15
        )
        if not r2.ok:
            print("WA send_text error:", r2.status_code, r2.text)
    except Exception as e:
        print("send_text exception:", e)
        traceback.print_exc()

def send_image(to, url, caption=None):
    payload = {"messaging_product":"whatsapp","to":to,"type":"image","image":{"link":url}}
    if caption: payload["image"]["caption"] = caption
    try:
        requests.post(f"{GRAPH}/{PHONE_ID}/messages", headers=HEADERS, json=payload, timeout=15)
    except: pass

def send_document(to, link, caption=None, filename=None):
    doc = {"link": link}
    if filename: doc["filename"] = filename
    payload = {"messaging_product":"whatsapp","to":to,"type":"document","document":doc}
    if caption: payload["document"]["caption"] = caption
    try:
        requests.post(f"{GRAPH}/{PHONE_ID}/messages", headers=HEADERS, json=payload, timeout=15)
    except: pass

# ========= COPY HELPERS =========
INSTRUCT_EN = "👉 Reply with the number of your choice."
INSTRUCT_TA = "👉 விருப்ப எண்ணை மட்டும் பதிலளிக்கவும்."
INVALID_EN  = "Invalid entry, try again."
INVALID_TA  = "தவறான உள்ளீடு, மீண்டும் முயற்சிக்கவும்."

def invalid(to, lang): send_text(to, INVALID_EN if lang=="en" else INVALID_TA)

def ask_language(to):
    send_text(to,
        "Please select your language / தயவுசெய்து மொழியைத் தேர்ந்தெடுக்கவும்:\n"
        "1. English\n"
        "2. தமிழ்\n\n"
        f"{INSTRUCT_EN}\n{INSTRUCT_TA}"
    )

def main_menu(to, lang):
    if lang == "en":
        msg = ("Please choose:\n"
               "1. Customer\n"
               "2. Retailer\n"
               "3. Carpenter\n\n"
               "4. Talk to Gaja\n\n"
               f"{INSTRUCT_EN}")
    else:
        msg = ("நீங்கள் யார்?\n"
               "1. வாடிக்கையாளர்\n"
               "2. விற்பனையாளர்\n"
               "3. கார்பென்டர்\n\n"
               "4. கஜா அணியுடன் பேச\n\n"
               f"{INSTRUCT_TA}")
    send_text(to, msg)

def ask_code(to, lang):
    if lang == "en":
        send_text(to, "Please enter your Carpenter Code (e.g., ABC123).")
    else:
        send_text(to, "உங்கள் கார்பென்டர் குறியீட்டை உள்ளிடவும் (உ.தா., ABC123).")

def server_down_msg(lang):
    en = f"⛔ Our server is unavailable right now. Please try again in a few minutes or contact us: {GAJA_PHONE}"
    ta = f"⛔ சர்வர் தற்போது பதிலளிக்கவில்லை. சில நிமிடங்களில் மீண்டும் முயற்சிக்கவும் அல்லது எங்களை தொடர்புகொள்ளவும்: {GAJA_PHONE}"
    return en if lang == "en" else ta

# ========= Apps Script calls =========
def fetch_months(n=3):
    try:
        params = {"action":"months","latest":str(n)}
        if APPS_SECRET: params["secret"] = APPS_SECRET
        r2 = requests.get(APPS_URL, params=params, timeout=10)
        if not r2.ok: return None
        return r2.json().get("months", [])
    except: return None

def fetch_cashback(code, month):
    try:
        params = {"action":"cashback","code":code,"month":month}
        if APPS_SECRET: params["secret"] = APPS_SECRET
        r2 = requests.get(APPS_URL, params=params, timeout=10)
        if not r2.ok: return None
        return r2.json()
    except: return None

# ========= Flask app =========
app = Flask(__name__)

@app.get("/")
def health():
    return "GAJA bot running", 200

@app.get("/webhook")
def verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "forbidden", 403

@app.post("/webhook")
def incoming():
    data = request.get_json(silent=True) or {}
    try:
        msg = data["entry"][0]["changes"][0]["value"]["messages"][0]
    except Exception:
        return "ok", 200

    mid = msg.get("id")
    if already_processed(mid): return "ok", 200
    if msg.get("type") != "text": return "ok", 200

    frm  = msg["from"]
    s    = sget(frm)
    text = (msg.get("text", {}).get("body") or "").strip()
    if not text: return "ok", 200

    # Check carpenter daily limit
    blocked, dup_count = check_carpenter_limit(frm, text, s.get("state",""))
    if blocked:
        return "ok", 200

    # EXIT
    if text.upper() in ("EXIT","STOP"):
        r.delete(f"sess:{frm}")
        send_text(frm, "✅ Session ended. Send any message to start again.")
        log_event(frm, s.get("state",""), "Exit", dup_count)
        return "ok", 200

    # Main menu
    if text == "9":
        s["state"] = "lang"; ask_language(frm)
        log_event(frm, s["state"], "Reset", dup_count)
        return "ok", 200

    # Language selection
    if s["state"] == "lang":
        if text == "1":
            s["lang"] = "en"; s["state"] = "main"; main_menu(frm, s["lang"])
            log_event(frm, s["state"], "Lang EN", dup_count)
            return "ok", 200
        if text == "2":
            s["lang"] = "ta"; s["state"] = "main"; main_menu(frm, s["lang"])
            log_event(frm, s["state"], "Lang TA", dup_count)
            return "ok", 200
        invalid(frm, s["lang"]); ask_language(frm); return "ok", 200

    # Main menu
    if s["state"] == "main":
        if text == "1":
            s["state"] = "cust"
            if CATALOG_URL:
                send_document(frm, CATALOG_URL, "📖 GAJA Catalogue", CATALOG_FILENAME)
            else:
                send_text(frm, "Catalogue not available." if s["lang"]=="en" else "கையேடு இல்லை.")
            log_event(frm, s["state"], "Customer", dup_count)
            return "ok", 200
        if text == "2":
            send_text(frm,"Retailer options (coming soon). Returning to main menu...")
            s["state"] = "lang"; ask_language(frm)
            log_event(frm, s["state"], "Retailer", dup_count)
            return "ok", 200
        if text == "3":
            s["state"] = "carp"; send_text(frm,"Carpenter options:\n1. Register\n2. Scheme values\n3. Cashback\n\n"+INSTRUCT_EN)
            log_event(frm, s["state"], "Carpenter", dup_count)
            return "ok", 200
        if text == "4":
            send_text(frm,f"✅ A human will reply here soon.\n📞 Call us directly: {GAJA_PHONE}")
            log_event(frm, s["state"], "Contact", dup_count)
            return "ok", 200
        invalid(frm, s["lang"]); main_menu(frm, s["lang"]); return "ok", 200

    # Carpenter flow
    if s["state"] == "carp":
        if text == "1":
            send_text(frm, "Please send your phone number.\nOur team will call you and collect the details." if s["lang"]=="en"
                      else "உங்கள் தொலைபேசி எண்ணை அனுப்பவும். எங்கள் அணி உங்களை அழைத்து விவரங்களைப் பெறுவார்.")
            log_event(frm, s["state"], "Carpenter Register", dup_count)
            return "ok", 200
        if text == "2":
            sent = False
            for i, url in enumerate(SCHEME_IMAGES, start=1):
                if url:
                    sent = True
                    send_image(frm, url, f"🛠️ GAJA Carpenter Scheme ({i}/{len(SCHEME_IMAGES)})")
            if not sent:
                send_text(frm, "Scheme graphics not set." if s["lang"]=="en" else "ஸ்கீம் படங்கள் இல்லை.")
            log_event(frm, s["state"], "Carpenter Scheme", dup_count)
            return "ok", 200
        if text == "3":
            s["state"] = "cb_code"; ask_code(frm, s["lang"])
            log_event(frm, s["state"], "Cashback Start", dup_count)
            return "ok", 200
        invalid(frm, s["lang"]); return "ok", 200

    # Cashback: code → months → result
    if s["state"] == "cb_code":
        s["code"] = text.strip().upper()
        months = fetch_months(3)
        if not months:
            send_text(frm, server_down_msg(s["lang"]))
            s["state"] = "carp"; return "ok", 200
        s["months"] = months
        menu = ("Select a month:\n" if s["lang"]=="en" else "மாதத்தைத் தேர்ந்தெடுக்கவும்:\n")
        menu += "\n".join([f"{i+1}. {m}" for i,m in enumerate(months)])
        send_text(frm, menu + ("\n\n"+INSTRUCT_EN if s["lang"]=="en" else "\n\n"+INSTRUCT_TA))
        s["state"] = "cb_month"
        log_event(frm, s["state"], "Cashback Month Menu", dup_count)
        return "ok", 200

    if s["state"] == "cb_month":
        try:
            idx = int(text)-1
            if idx<0 or idx>=len(s["months"]): raise ValueError()
            month = s["months"][idx]
        except:
            invalid(frm, s["lang"])
            menu = ("Select a month:\n" if s["lang"]=="en" else "மாதத்தைத் தேர்ந்தெடுக்கவும்:\n")
            menu += "\n".join([f"{i+1}. {m}" for i,m in enumerate(s["months"])])
            send_text(frm, menu + ("\n\n"+INSTRUCT_EN if s["lang"]=="en" else "\n\n"+INSTRUCT_TA))
            return "ok", 200

        j = fetch_cashback(s["code"], month)
        if j is None:
            send_text(frm, server_down_msg(s["lang"]))
            s["state"] = "carp"; return "ok", 200

        if not j.get("found"):
            msg = (f"{s['code']} – {month}\nNo cashback recorded."
                   if s["lang"]=="en" else f"{s['code']} – {month}\nஇந்த மாதத்திற்கு பதிவு இல்லை.")
        else:
            name = j.get("name","")
            amt  = j.get("cashback_amount", 0)
            if s["lang"] == "en":
                msg = (f"Hello {name}, you have received Rs.{amt} in {month}.\n\n"
                       f"The incentive will be transferred to your bank account at the end of the month. "
                       f"For queries, call {GAJA_PHONE}.")
            else:
                msg = (f"வணக்கம் {name}, நீங்கள் {month} மாதத்தில் ரூ.{amt} பெற்றுள்ளீர்கள்.\n\n"
                       f"மாத இறுதியில் ஊக்கத்தொகை வங்கி எண்ணுக்கு அனுப்பப்படும். "
                       f"சந்தேகங்களுக்கு {GAJA_PHONE} அழைக்கவும்.")
        send_text(frm, msg)
        s["state"] = "carp"
        log_event(frm, s["state"], "Cashback Result", dup_count)
        return "ok", 200

    return "ok", 200

if __name__ == "__main__":
    from waitress import serve
    port = int(os.getenv("PORT", "10000"))
    serve(app, host="0.0.0.0", port=port)
