import os, requests
from flask import Flask, request

ACCESS_TOKEN   = os.getenv("ACCESS_TOKEN")
PHONE_ID       = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN   = os.getenv("VERIFY_TOKEN", "gaja-verify-123")
APPS_URL       = os.getenv("APPS_SCRIPT_URL")
APPS_SECRET    = os.getenv("APPS_SECRET", "")
SCHEME_IMAGE   = os.getenv("SCHEME_IMAGE_URL", "")

GRAPH = "https://graph.facebook.com/v20.0"
HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type":"application/json"}
SESS = {}  # { phone: {"lang":"en|ta", "state":"lang|main|carp|cb_code|cb_month", "code":"", "months":[...] } }

def send_text(to, body):
    requests.post(f"{GRAPH}/{PHONE_ID}/messages", headers=HEADERS,
                  json={"messaging_product":"whatsapp","to":to,"text":{"body":body}})

def send_image(to, url, caption=None):
    payload = {"messaging_product":"whatsapp","to":to,"type":"image","image":{"link":url}}
    if caption: payload["image"]["caption"] = caption
    requests.post(f"{GRAPH}/{PHONE_ID}/messages", headers=HEADERS, json=payload)

def sget(phone):
    if phone not in SESS: SESS[phone] = {"lang":"en","state":"lang"}
    return SESS[phone]

def ask_language(to):
    send_text(to, "Please select your language / தயவுசெய்து உங்கள் மொழியைத் தேர்ந்தெடுக்கவும்:\n1) English\n2) தமிழ்")

def main_menu(to, lang):
    en = "Please choose:\n1) Customer\n2) Retailer\n3) Carpenter\n9) Talk to Gaja"
    ta = "தயவு செய்து தேர்ந்தெடுக்கவும்:\n1) வாடிக்கையாளர்\n2) ரிட்டெய்லர்\n3) மரப்பணிக்காரர்\n9) Gaja அணியுடன் பேச"
    send_text(to, en if lang=="en" else ta)

def carpenter_menu(to, lang):
    en = "Carpenter options:\n1) Register for Carpenter Code\n2) Scheme values\n3) Cashback details\n0) Back"
    ta = "மரப்பணிக்காரர் விருப்பங்கள்:\n1) பதிவு\n2) ஸ்கீம் மதிப்புகள்\n3) கேஷ்பேக் விவரம்\n0) பின் செல்ல"
    send_text(to, en if lang=="en" else ta)

def ask_code(to, lang):
    en = "Please enter your Carpenter Code (e.g., ABC123)."
    ta = "உங்கள் மரப்பணிக்காரர் குறியீட்டை உள்ளிடவும் (உ.தா., ABC123)."
    send_text(to, en if lang=="en" else ta)

def fetch_months(n=3):
    params = {"action":"months","latest":str(n)}
    if APPS_SECRET: params["secret"] = APPS_SECRET
    r = requests.get(APPS_URL, params=params, timeout=20)
    return (r.json().get("months") or []) if r.ok else []

def fetch_cashback(code, month):
    params = {"action":"cashback","code":code,"month":month}
    if APPS_SECRET: params["secret"] = APPS_SECRET
    r = requests.get(APPS_URL, params=params, timeout=20)
    return r.json() if r.ok else {"found":False}

app = Flask(__name__)

@app.get("/")
def health(): return "GAJA bot running", 200

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

    frm = msg["from"]
    s = sget(frm)
    text = msg["text"]["body"].strip() if msg.get("type")=="text" else ""

    if s["state"] == "lang":
        if text == "1": s["lang"]="en"; s["state"]="main"; main_menu(frm, s["lang"]); return "ok", 200
        if text == "2": s["lang"]="ta"; s["state"]="main"; main_menu(frm, s["lang"]); return "ok", 200
        ask_language(frm); return "ok", 200

    if s["state"] == "main":
        if text == "3": s["state"]="carp"; carpenter_menu(frm, s["lang"]); return "ok", 200
        if text == "9": send_text(frm, "Call/WhatsApp: +91-XXXXXXXXXX"); return "ok", 200
        main_menu(frm, s["lang"]); return "ok", 200

    if s["state"] == "carp":
        if text == "1": send_text(frm, "Send: Name – Location – Phone – Pincode"); return "ok", 200
        if text == "2": send_image(frm, SCHEME_IMAGE, "GAJA Scheme values") if SCHEME_IMAGE else send_text(frm,"Scheme graphic not set."); return "ok", 200
        if text == "3": s["state"]="cb_code"; ask_code(frm, s["lang"]); return "ok", 200
        if text == "0": s["state"]="main"; main_menu(frm, s["lang"]); return "ok", 200
        carpenter_menu(frm, s["lang"]); return "ok", 200

    if s["state"] == "cb_code":
        s["code"] = text.strip().upper()
        s["months"] = fetch_months(3) or ["June 2025","July 2025","August 2025"]
        menu = "\n".join([f"{i+1}) {m}" for i,m in enumerate(s["months"])]) + "\n0) Back"
        ask = "Select a month:\n" if s["lang"]=="en" else "மாதத்தைத் தேர்ந்தெடுக்கவும்:\n"
        send_text(frm, ask + menu)
        s["state"]="cb_month"; return "ok", 200

    if s["state"] == "cb_month":
        if text == "0": s["state"]="carp"; carpenter_menu(frm, s["lang"]); return "ok", 200
        try:
            month = s["months"][int(text)-1]
        except Exception:
            send_text(frm, "Invalid choice. Try again."); return "ok", 200
        j = fetch_cashback(s["code"], month)
        if not j.get("found"):
            msg = f"{s['code']} – {month}\nNo cashback recorded." if s["lang"]=="en" else f"{s['code']} – {month}\nஇந்த மாதத்திற்கு பதிவு இல்லை."
        else:
            if s["lang"]=="en":
                msg = f"{s['code']} – {month}\n{j.get('name','')}\n💰 Cashback: ₹{j.get('cashback_amount',0)}\n0) Back  |  9) Talk to Gaja"
            else:
                msg = f"{s['code']} – {month}\n{j.get('name','')}\n💰 கேஷ்பேக்: ₹{j.get('cashback_amount',0)}\n0) பின் செல்ல  |  9) பேச"
        send_text(frm, msg)
        s["state"]="carp"; return "ok", 200

    s["state"]="lang"; ask_language(frm); return "ok", 200

if __name__ == "__main__":
    import os
    from waitress import serve
    port = int(os.getenv("PORT", "10000"))
    serve(app, host="0.0.0.0", port=port)
