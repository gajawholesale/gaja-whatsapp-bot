import os, requests
from flask import Flask, request

# ========= ENV =========
ACCESS_TOKEN    = os.getenv("ACCESS_TOKEN")
PHONE_ID        = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN    = os.getenv("VERIFY_TOKEN", "gaja-verify-123")

APPS_URL        = os.getenv("APPS_SCRIPT_URL")       # must end with /exec (no query)
APPS_SECRET     = os.getenv("APPS_SECRET", "")

GAJA_PHONE      = os.getenv("GAJA_PHONE", "+91-XXXXXXXXXX")

CATALOG_URL     = os.getenv("CATALOG_URL", "")
CATALOG_FILENAME= os.getenv("CATALOG_FILENAME", "GAJA-Catalogue.pdf")

SCHEME_IMG_KEYS = ["SCHEME_IMG1","SCHEME_IMG2","SCHEME_IMG3","SCHEME_IMG4","SCHEME_IMG5"]
SCHEME_IMAGES   = [os.getenv(k, "") for k in SCHEME_IMG_KEYS if os.getenv(k, "")]

GRAPH   = "https://graph.facebook.com/v20.0"
HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type":"application/json"}

# Simple in-memory session store
SESS = {}  # { phone: {"lang":"en|ta", "state":"lang|main|cust|ret|carp|cb_code|cb_month", "code":"", "months":[...] } }

# ========= WhatsApp send helpers =========
def send_text(to, body):
    try:
        requests.post(f"{GRAPH}/{PHONE_ID}/messages", headers=HEADERS,
                      json={"messaging_product":"whatsapp","to":to,"text":{"body":body}}, timeout=15)
    except Exception:
        pass

def send_image(to, url, caption=None):
    payload = {"messaging_product":"whatsapp","to":to,"type":"image","image":{"link":url}}
    if caption: payload["image"]["caption"] = caption
    try:
        requests.post(f"{GRAPH}/{PHONE_ID}/messages", headers=HEADERS, json=payload, timeout=15)
    except Exception:
        pass

def send_document(to, link, caption=None, filename=None):
    doc = {"link": link}
    if filename: doc["filename"] = filename  # ensure .pdf filename, avoids .bin
    payload = {"messaging_product":"whatsapp","to":to,"type":"document","document":doc}
    if caption: payload["document"]["caption"] = caption
    try:
        requests.post(f"{GRAPH}/{PHONE_ID}/messages", headers=HEADERS, json=payload, timeout=15)
    except Exception:
        pass

def sget(phone):
    if phone not in SESS: SESS[phone] = {"lang":"en", "state":"lang"}
    return SESS[phone]

# ========= Copy helpers & strings =========
INSTRUCT_EN = "👉 Reply with the number of your choice."
INSTRUCT_TA = "👉 விருப்ப எண்ணை மட்டும் பதிலளிக்கவும்."

INVALID_EN  = "Invalid entry, try again."
INVALID_TA  = "தவறான உள்ளீடு, மீண்டும் முயற்சிக்கவும்."

def invalid(to, lang):
    send_text(to, INVALID_EN if lang=="en" else INVALID_TA)

def back_block(lang):
    # always show a blank line, then back + change language
    return ("\n0. Back\n00. Change language"
            if lang=="en" else
            "\n0. திரும்பிச் செல்ல\n00. மொழியை மாற்ற")

def ask_language(to):
    send_text(
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
               "3. Carpenter\n"
               "9. Talk to Gaja"
               f"{back_block('en')}\n\n{INSTRUCT_EN}")
    else:
        msg = ("நீங்கள் யார்?\n"
               "1. வாடிக்கையாளர்\n"
               "2. விற்பனையாளர்\n"
               "3. கார்பென்டர்\n"
               "9. கஜா அணியுடன் பேச"
               f"{back_block('ta')}\n\n{INSTRUCT_TA}")
    send_text(to, msg)

def customer_menu(to, lang):
    if lang == "en":
        msg = ("Customer options:\n"
               "1. View Catalogue"
               f"{back_block('en')}\n\n{INSTRUCT_EN}")
    else:
        msg = ("வாடிக்கையாளருக்கான விருப்பங்கள்\n"
               "1. விவரப்பட்டியை பார்க்க (Catalogue)"
               f"{back_block('ta')}\n\n{INSTRUCT_TA}")
    send_text(to, msg)

def retailer_menu(to, lang):
    if lang == "en":
        msg = ("Retailer options (coming soon)."
               f"{back_block('en')}")
    else:
        msg = ("விற்பனையாளருக்கான விருப்பங்கள் (விரைவில் வரும்)."
               f"{back_block('ta')}")
    send_text(to, msg)

def carpenter_menu(to, lang):
    if lang == "en":
        msg = ("Carpenter options:\n"
               "1. Register for Carpenter Code\n"
               "2. Scheme values\n"
               "3. Cashback details"
               f"{back_block('en')}\n\n{INSTRUCT_EN}")
    else:
        msg = ("கார்பென்டருக்கான விருப்பங்கள்:\n"
               "1. கார்பென்டர் குறியீட்டைப் பதிவு செய்ய\n"
               "2. கஜா பொருட்களுக்கான ஊக்கத்தொகை மதிப்புகள்\n"
               "3. கேஷ்பேக் விவரங்கள்"
               f"{back_block('ta')}\n\n{INSTRUCT_TA}")
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

# ========= Apps Script calls (with timeouts & fallbacks) =========
def fetch_months(n=3):
    try:
        params = {"action":"months","latest":str(n)}
        if APPS_SECRET: params["secret"] = APPS_SECRET
        r = requests.get(APPS_URL, params=params, timeout=10)
        if not r.ok: return None
        return r.json().get("months", [])
    except Exception:
        return None

def fetch_cashback(code, month):
    try:
        params = {"action":"cashback","code":code,"month":month}
        if APPS_SECRET: params["secret"] = APPS_SECRET
        r = requests.get(APPS_URL, params=params, timeout=10)
        if not r.ok: return None
        return r.json()
    except Exception:
        return None

# ========= Flask app =========
app = Flask(__name__)

@app.get("/")
def health():
    return "GAJA bot running", 200

# Webhook verification
@app.get("/webhook")
def verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "forbidden", 403

# Incoming messages
@app.post("/webhook")
def incoming():
    data = request.get_json(silent=True) or {}
    try:
        msg = data["entry"][0]["changes"][0]["value"]["messages"][0]
    except Exception:
        return "ok", 200

    frm  = msg["from"]
    s    = sget(frm)
    text = msg["text"]["body"].strip() if msg.get("type") == "text" else ""

    # Global shortcuts
    if text == "00":  # change language from anywhere
        s["state"] = "lang"; ask_language(frm); return "ok", 200
    if text == "0":   # back from anywhere
        # From main, back goes to language
        if s["state"] in ("main", "lang"):
            s["state"] = "lang"; ask_language(frm); return "ok", 200
        # Otherwise go one level up
        s["state"] = "main"; main_menu(frm, s["lang"]); return "ok", 200

    # Language selection
    if s["state"] == "lang":
        if text == "1":
            s["lang"] = "en"; s["state"] = "main"; main_menu(frm, s["lang"]); return "ok", 200
        if text == "2":
            s["lang"] = "ta"; s["state"] = "main"; main_menu(frm, s["lang"]); return "ok", 200
        invalid(frm, "en"); ask_language(frm); return "ok", 200

    # Main menu
    if s["state"] == "main":
        if text == "1":
            s["state"] = "cust"; customer_menu(frm, s["lang"]); return "ok", 200
        if text == "2":
            s["state"] = "ret"; retailer_menu(frm, s["lang"]); return "ok", 200
        if text == "3":
            s["state"] = "carp"; carpenter_menu(frm, s["lang"]); return "ok", 200
        if text == "9":
            send_text(frm, f"✅ A human will reply here soon.\nFor urgent help: {GAJA_PHONE}")
            return "ok", 200
        invalid(frm, s["lang"]); main_menu(frm, s["lang"]); return "ok", 200

    # Customer flow
    if s["state"] == "cust":
        if text == "1":
            if CATALOG_URL:
                send_document(frm, CATALOG_URL, "📖 GAJA Catalogue", CATALOG_FILENAME)
            else:
                send_text(frm, "Catalogue not available right now." if s["lang"]=="en" else "கையேடு தற்போது கிடைக்கவில்லை.")
            return "ok", 200
        invalid(frm, s["lang"]); customer_menu(frm, s["lang"]); return "ok", 200

    # Retailer flow (stub)
    if s["state"] == "ret":
        invalid(frm, s["lang"]); retailer_menu(frm, s["lang"]); return "ok", 200

    # Carpenter flow
    if s["state"] == "carp":
        if text == "1":
            if s["lang"] == "en":
                send_text(frm, "Please send your phone number.\nOur team will call you and collect the required details to complete the registration.")
            else:
                send_text(frm, "உங்கள் தொலைபேசி எண்ணை அனுப்பவும்.\nபதிவு செய்ய, எங்கள் அணி உங்களை அழைத்து தேவையான விவரங்களைப் பெறுவார்.")
            return "ok", 200

        if text == "2":
            sent = False
            for i, url in enumerate(SCHEME_IMAGES, start=1):
                if url:
                    sent = True
                    cap = f"🛠️ GAJA Carpenter Scheme ({i}/{len(SCHEME_IMAGES)})"
                    send_image(frm, url, cap)
            if not sent:
                send_text(frm, "Scheme graphics not set." if s["lang"]=="en" else "ஸ்கீம் படங்கள் அமைக்கப்படவில்லை.")
            return "ok", 200

        if text == "3":
            s["state"] = "cb_code"; ask_code(frm, s["lang"]); return "ok", 200

        invalid(frm, s["lang"]); carpenter_menu(frm, s["lang"]); return "ok", 200

    # Cashback: code → months → result
    if s["state"] == "cb_code":
        s["code"] = text.strip().upper()
        months = fetch_months(3)
        if not months:
            send_text(frm, server_down_msg(s["lang"]))
            s["state"] = "carp"; return "ok", 200
        s["months"] = months
        if s["lang"] == "en":
            menu = ("Select a month:\n" +
                    "\n".join([f"{i+1}. {m}" for i, m in enumerate(months)]) +
                    f"{back_block('en')}\n\n{INSTRUCT_EN}")
        else:
            menu = ("மாதத்தைத் தேர்ந்தெடுக்கவும்:\n" +
                    "\n".join([f"{i+1}. {m}" for i, m in enumerate(months)]) +
                    f"{back_block('ta')}\n\n{INSTRUCT_TA}")
        send_text(frm, menu)
        s["state"] = "cb_month"; return "ok", 200

    if s["state"] == "cb_month":
        try:
            idx = int(text) - 1
            if idx < 0: raise ValueError()
            month = s["months"][idx]
        except Exception:
            invalid(frm, s["lang"])
            # re-show same month list
            if s["lang"] == "en":
                menu = ("Select a month:\n" +
                        "\n".join([f"{i+1}. {m}" for i, m in enumerate(s["months"])]) +
                        f"{back_block('en')}\n\n{INSTRUCT_EN}")
            else:
                menu = ("மாதத்தைத் தேர்ந்தெடுக்கவும்:\n" +
                        "\n".join([f"{i+1}. {m}" for i, m in enumerate(s["months"])]) +
                        f"{back_block('ta')}\n\n{INSTRUCT_TA}")
            send_text(frm, menu)
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
                msg = (f"Hello {name}, you have received an incentive of Rs.{amt} in the month {month}.\n\n"
                       f"The incentive will be transferred to your bank account at the end of the month. "
                       f"For any queries, please call us at {GAJA_PHONE}.")
            else:
                msg = (f"வணக்கம் {name}, நீங்கள் {month} மாதத்தில் ரூ.{amt} ஊக்கத்தொகையைப் பெற்றுள்ளீர்கள்.\n\n"
                       f"மாத இறுதியில் ஊக்கத்தொகை உங்கள் வங்கி எண்ணுக்கு அனுப்பப்படும். "
                       f"ஏதேனும் சந்தேகங்களுக்கு {GAJA_PHONE} என்ற எண்ணில் எங்களை அழைக்கவும்.")
        send_text(frm, msg)
        s["state"] = "carp"; return "ok", 200

    # Fallback to language
    s["state"] = "lang"; ask_language(frm); return "ok", 200


if __name__ == "__main__":
    from waitress import serve
    port = int(os.getenv("PORT", "10000"))
    serve(app, host="0.0.0.0", port=port)
