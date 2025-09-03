import os, requests, json
from flask import Flask, request
import redis
from datetime import datetime

# ========= ENV =========
ACCESS_TOKEN    = os.getenv("ACCESS_TOKEN")
PHONE_ID        = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN    = os.getenv("VERIFY_TOKEN", "gaja-verify-123")
APPS_URL        = os.getenv("APPS_SCRIPT_URL")
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

# ========= HELPERS =========
def save_session(frm, s):
    ttl = 120 if s["state"] in ("lang","main") else 300
    r.setex(f"sess:{frm}", ttl, json.dumps(s))

def sget(phone):
    key = f"sess:{phone}"
    s = r.get(key)
    if s: s = json.loads(s)
    else: s = {"lang": "en", "state": "lang"}
    save_session(phone, s)
    return s

def already_processed(mid: str) -> bool:
    if not mid: return False
    key = f"msg:{mid}"
    return not r.set(name=key, value="1", nx=True, ex=600)

def send_text(to, body):
    try:
        requests.post(f"{GRAPH}/{PHONE_ID}/messages", headers=HEADERS,
            json={"messaging_product":"whatsapp","to":to,"text":{"body":body}}, timeout=15)
    except: pass

def send_image(to, url, caption=None):
    payload = {"messaging_product":"whatsapp","to":to,"type":"image","image":{"link":url}}
    if caption: payload["image"]["caption"] = caption
    try: requests.post(f"{GRAPH}/{PHONE_ID}/messages", headers=HEADERS, json=payload, timeout=15)
    except: pass

def send_document(to, link, caption=None, filename=None):
    doc = {"link": link}
    if filename: doc["filename"] = filename
    payload = {"messaging_product":"whatsapp","to":to,"type":"document","document":doc}
    if caption: payload["document"]["caption"] = caption
    try: requests.post(f"{GRAPH}/{PHONE_ID}/messages", headers=HEADERS, json=payload, timeout=15)
    except: pass

def log_pumble(msg: str):
    if not PUMBLE_WEBHOOK: return
    try: requests.post(PUMBLE_WEBHOOK, json={"text": msg}, timeout=5)
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
        "1. English\n2. தமிழ்\n\n"
        f"{INSTRUCT_EN}\n{INSTRUCT_TA}"
    )

def main_menu(to, lang):
    msg = ("Please choose:\n1. Customer\n2. Retailer\n3. Carpenter\n\n4. Talk to Gaja\n\n"+INSTRUCT_EN
           if lang=="en" else
           "நீங்கள் யார்?\n1. வாடிக்கையாளர்\n2. விற்பனையாளர்\n3. கார்பென்டர்\n\n4. கஜா அணியுடன் பேச\n\n"+INSTRUCT_TA)
    send_text(to, msg)

def customer_menu(to, lang):
    msg = ("Customer options:\n1. View Catalogue\n\n"+INSTRUCT_EN
           if lang=="en" else
           "வாடிக்கையாளர் விருப்பங்கள்:\n1. விவரப்பட்டியை பார்க்க\n\n"+INSTRUCT_TA)
    send_text(to, msg)

def carpenter_menu(to, lang):
    msg = ("Carpenter options:\n1. Register\n2. Scheme values\n3. Cashback\n\n"+INSTRUCT_EN
           if lang=="en" else
           "கார்பென்டர் விருப்பங்கள்:\n1. பதிவு\n2. ஸ்கீம் மதிப்புகள்\n3. கேஷ்பேக்\n\n"+INSTRUCT_TA)
    send_text(to, msg)

def ask_code(to, lang):
    send_text(to, "Please enter your Carpenter Code (e.g., ABC123)." if lang=="en"
              else "உங்கள் கார்பென்டர் குறியீட்டை உள்ளிடவும் (உ.தா., ABC123).")

def server_down_msg(lang):
    return (f"⛔ Our server is unavailable. Try again later or call {GAJA_PHONE}"
            if lang=="en" else
            f"⛔ சர்வர் கிடைக்கவில்லை. பிறகு முயற்சிக்கவும் அல்லது {GAJA_PHONE} அழைக்கவும்")

# ========= Apps Script =========
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

# ========= Flask =========
app = Flask(__name__)

@app.get("/")
def health(): return "GAJA bot running", 200

@app.get("/webhook")
def verify():
    if request.args.get("hub.mode")=="subscribe" and request.args.get("hub.verify_token")==VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "forbidden", 403

@app.post("/webhook")
def incoming():
    data = request.get_json(silent=True) or {}
    try: msg = data["entry"][0]["changes"][0]["value"]["messages"][0]
    except: return "ok", 200

    mid = msg.get("id")
    if already_processed(mid): return "ok", 200
    if msg.get("type")!="text": return "ok", 200

    frm  = msg["from"]
    s    = sget(frm)
    text = (msg.get("text", {}).get("body") or "").strip()
    if not text: return "ok", 200

    # EXIT
    if text.upper() in ("EXIT","STOP"):
        r.delete(f"sess:{frm}"); send_text(frm,"✅ Session ended. Send any msg to start again.")
        return "ok", 200

    # Main menu shortcut
    if text=="9": s["state"]="lang"; ask_language(frm); save_session(frm,s); return "ok", 200

    # Language
    if s["state"]=="lang":
        if text=="1": s["lang"]="en"; s["state"]="main"; main_menu(frm,s["lang"]); save_session(frm,s); return "ok",200
        if text=="2": s["lang"]="ta"; s["state"]="main"; main_menu(frm,s["lang"]); save_session(frm,s); return "ok",200
        invalid(frm,s["lang"]); ask_language(frm); return "ok",200

    # Main menu
    if s["state"]=="main":
        if text=="1": s["state"]="cust"; customer_menu(frm,s["lang"]); save_session(frm,s); return "ok",200
        if text=="2": send_text(frm,"Retailer options (coming soon)."); s["state"]="lang"; ask_language(frm); save_session(frm,s); return "ok",200
        if text=="3": s["state"]="carp"; carpenter_menu(frm,s["lang"]); save_session(frm,s); return "ok",200
        if text=="4": send_text(frm,f"✅ A human will reply.\n📞 Call {GAJA_PHONE}"); return "ok",200
        invalid(frm,s["lang"]); main_menu(frm,s["lang"]); return "ok",200

    # Customer
    if s["state"]=="cust":
        if text=="1":
            if CATALOG_URL:
                send_document(frm, CATALOG_URL, "📖 GAJA Catalogue", CATALOG_FILENAME)
                log_pumble(f"📂 Catalogue sent to {frm}")
            else: send_text(frm,"Catalogue not available." if s["lang"]=="en" else "கையேடு கிடைக்கவில்லை.")
            return "ok",200
        invalid(frm,s["lang"]); customer_menu(frm,s["lang"]); return "ok",200

    # Carpenter
    if s["state"]=="carp":
        if text=="1":
            send_text(frm,"Please send your phone number. Our team will call you." if s["lang"]=="en"
                      else "உங்கள் தொலைபேசி எண்ணை அனுப்பவும். எங்கள் அணி உங்களை அழைப்பார்.")
            return "ok",200
        if text=="2":
            if SCHEME_IMAGES:
                for i,u in enumerate(SCHEME_IMAGES,1): send_image(frm,u,f"🛠️ GAJA Scheme {i}/{len(SCHEME_IMAGES)}")
            else: send_text(frm,"Scheme graphics not set." if s["lang"]=="en" else "ஸ்கீம் படங்கள் இல்லை.")
            return "ok",200
        if text=="3": s["state"]="cb_code"; ask_code(frm,s["lang"]); save_session(frm,s); return "ok",200
        invalid(frm,s["lang"]); carpenter_menu(frm,s["lang"]); return "ok",200

    # Cashback
    if s["state"]=="cb_code":
        s["code"]=text.strip().upper(); months=fetch_months(3)
        if not months: send_text(frm,server_down_msg(s["lang"])); s["state"]="carp"; save_session(frm,s); return "ok",200
        s["months"]=months
        menu=("Select a month:\n" if s["lang"]=="en" else "மாதத்தைத் தேர்ந்தெடுக்கவும்:\n")+ \
             "\n".join([f"{i+1}. {m}" for i,m in enumerate(months)])
        send_text(frm,menu+("\n\n"+INSTRUCT_EN if s["lang"]=="en" else "\n\n"+INSTRUCT_TA))
        s["state"]="cb_month"; save_session(frm,s); return "ok",200

    if s["state"]=="cb_month":
        try: idx=int(text)-1; month=s["months"][idx]
        except: invalid(frm,s["lang"]); return "ok",200
        j=fetch_cashback(s["code"],month)
        if j is None: send_text(frm,server_down_msg(s["lang"])); s["state"]="carp"; save_session(frm,s); return "ok",200
        if not j.get("found"):
            msg=f"{s['code']} – {month}\nNo cashback recorded." if s["lang"]=="en" else f"{s['code']} – {month}\nபதிவு இல்லை."
        else:
            name=j.get("name",""); amt=j.get("cashback_amount",0)
            msg=(f"Hello {name}, you got Rs.{amt} in {month}.\n\nIt will be transferred at month end. Call {GAJA_PHONE}."
                 if s["lang"]=="en" else
                 f"வணக்கம் {name}, நீங்கள் {month} மாதத்தில் ரூ.{amt} பெற்றுள்ளீர்கள்.\n\nமாத இறுதியில் வங்கிக்குச் செலுத்தப்படும். {GAJA_PHONE} அழைக்கவும்.")
            log_pumble(f"💰 Cashback for {frm}\nCode: {s['code']}\nMonth: {month}\nAmount: {amt}")
        send_text(frm,msg); s["state"]="carp"; save_session(frm,s); return "ok",200

    save_session(frm,s)
    return "ok",200

if __name__=="__main__":
    from waitress import serve
    port=int(os.getenv("PORT","10000"))
    serve(app,host="0.0.0.0",port=port)
