import requests as req
from flask import Flask, render_template, request, jsonify, send_from_directory
import smtplib, os, json, socket, base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

app = Flask(__name__)

# ══════════════════════════════════════════════════════
#   GMAIL  (reads from Render env vars OR uses defaults)
# ══════════════════════════════════════════════════════
YOUR_EMAIL    = os.environ.get('YOUR_EMAIL',    'thammishettishivaprasanna@gmail.com')
YOUR_PASSWORD = os.environ.get('YOUR_PASSWORD', 'yxfzhltvgyvdoahz')

# ══════════════════════════════════════════════════════
#   FAST2SMS  ← set this in Render → Environment
#   Sign up free at https://www.fast2sms.com
#   Dashboard → Dev API → copy key → paste in Render env
# ══════════════════════════════════════════════════════
FAST2SMS_KEY = os.environ.get('FAST2SMS_KEY', 'YOUR_FAST2SMS_KEY')

YOUR_NAME = "SHEild User"

# ══════════════════════════════════════════════════════
#   HOST — auto-detects Render or local
# ══════════════════════════════════════════════════════
RENDER_HOST = os.environ.get('RENDER_EXTERNAL_HOSTNAME', '')
IS_RENDER   = bool(RENDER_HOST)
SERVER_BASE = f"https://{RENDER_HOST}" if IS_RENDER else "http://localhost:5000"
SERVER_PORT = int(os.environ.get('PORT', 5000))

# ══════════════════════════════════════════════════════
#   PATHS
# ══════════════════════════════════════════════════════
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
EVIDENCE_DIR = os.path.join(BASE_DIR, 'evidence')
CONFIG_PATH  = os.path.join(BASE_DIR, 'config.json')
os.makedirs(EVIDENCE_DIR, exist_ok=True)

TRUSTED_CONTACTS = []
CANCEL_PIN       = "1234"
alerts           = []


def utcnow():
    return datetime.now(timezone.utc)


# ── Load config ───────────────────────────────────────
def load_config():
    global TRUSTED_CONTACTS, CANCEL_PIN
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            saved = json.load(f)
        TRUSTED_CONTACTS = [c for c in saved.get('contacts', []) if c.get('email')]
        CANCEL_PIN = saved.get('pin', '1234')
        print(f"\nConfig loaded:")
        for c in TRUSTED_CONTACTS:
            print(f"  {c.get('name')} | {c.get('email')} | {c.get('phone','no phone')}")
        print(f"  PIN  : {CANCEL_PIN}")
        print(f"  Host : {SERVER_BASE}")
        sms_ok = not FAST2SMS_KEY.startswith('YOUR_')
        print(f"  SMS  : {'Fast2SMS ready ✓' if sms_ok else 'NOT SET — add FAST2SMS_KEY env var'}\n")
    else:
        print("\nNo config.json — go to /setup first\n")

load_config()


# ══════════════════════════════════════════════════════
#   SEND EMAIL  (Gmail SMTP — plain text, no attachment)
# ══════════════════════════════════════════════════════
def send_email(to_email, subject, body):
    try:
        msg            = MIMEMultipart()
        msg['Subject'] = subject
        msg['From']    = YOUR_EMAIL
        msg['To']      = to_email
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(YOUR_EMAIL, YOUR_PASSWORD)
            smtp.send_message(msg)

        print(f"  ✓ Email → {to_email}")
        return True
    except smtplib.SMTPAuthenticationError:
        print(f"  ✗ Gmail auth failed")
        return False
    except Exception as e:
        print(f"  ✗ Email error: {e}")
        return False


# ══════════════════════════════════════════════════════
#   SEND SMS  (Fast2SMS — works from Render, no phone app)
# ══════════════════════════════════════════════════════
def send_sms(to_phone, body):
    if not to_phone or not to_phone.strip():
        print("  SMS skipped — no phone")
        return False

    phone = to_phone.strip().replace(' ', '').replace('-', '')[-10:]

    if FAST2SMS_KEY.startswith('YOUR_'):
        print("  SMS skipped — FAST2SMS_KEY not set in Render env vars")
        return False

    try:
        r = req.post(
            "https://www.fast2sms.com/dev/bulkV2",
            headers={"authorization": FAST2SMS_KEY, "Content-Type": "application/json"},
            json={"route": "q", "message": body, "numbers": phone},
            timeout=15
        )
        result = r.json()
        if result.get("return") is True:
            print(f"  ✓ SMS → {phone}")
            return True
        else:
            print(f"  ✗ SMS failed: {result.get('message', result)}")
            return False
    except Exception as e:
        print(f"  ✗ SMS error: {e}")
        return False


# ══════════════════════════════════════════════════════
#   PAGES
# ══════════════════════════════════════════════════════
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/setup')
def setup_page():
    return render_template('setup.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html', alerts=alerts)

@app.route('/live')
def live():
    return render_template('live.html')

@app.route('/history')
def history():
    return render_template('history.html')

@app.route('/saferoute')
def saferoute():
    return render_template('saferoute.html')

@app.route('/track/<alert_id>')
def track(alert_id):
    alert = next((a for a in alerts if a['id'] == alert_id), None)
    return render_template('track.html', alert=alert, alert_id=alert_id)

@app.route('/track-data/<alert_id>')
def track_data(alert_id):
    alert = next((a for a in alerts if a['id'] == alert_id), None)
    if alert:
        return jsonify({'lat': alert.get('lat'), 'lng': alert.get('lng'),
                        'time': alert.get('time'), 'maps': alert.get('maps'),
                        'audio': alert.get('audio', False)})
    return jsonify({}), 404

@app.route('/alerts')
def get_alerts():
    return jsonify(alerts)

@app.route('/evidence/<filename>')
def serve_evidence(filename):
    return send_from_directory(EVIDENCE_DIR, filename)


# ══════════════════════════════════════════════════════
#   SETUP
# ══════════════════════════════════════════════════════
@app.route('/setup', methods=['POST'])
def save_setup():
    global TRUSTED_CONTACTS, CANCEL_PIN
    data = request.get_json()

    TRUSTED_CONTACTS = [c for c in data.get('contacts', [])
                        if c.get('email') and c['email'].strip()]
    CANCEL_PIN = data.get('pin', '1234')

    with open(CONFIG_PATH, 'w') as f:
        json.dump({'contacts': data.get('contacts', []), 'pin': CANCEL_PIN,
                   'gesture': data.get('gesture', 'key_s'),
                   'from': data.get('from', '20'), 'to': data.get('to', '6')}, f, indent=2)

    print(f"\nSetup saved — {[c.get('email') for c in TRUSTED_CONTACTS]}")

    for contact in TRUSTED_CONTACTS:
        send_email(
            to_email = contact['email'],
            subject  = 'SHEild — You are now a trusted contact',
            body     = (
                f"Hello {contact.get('name', '')},\n\n"
                f"You have been added as a trusted emergency contact on SHEild.\n\n"
                f"If an SOS is triggered you will receive an immediate email AND SMS "
                f"with a live GPS tracking link.\n\n"
                f"Please respond immediately if you receive an SOS alert.\n\n"
                f"— SHEild Safety System"
            )
        )
        if contact.get('phone'):
            send_sms(contact['phone'],
                     f"SHEild: You are now a trusted contact for {YOUR_NAME}. "
                     f"You will receive SMS alerts if they need help.")

    return jsonify({'status': 'saved',
                    'contacts': [c['email'] for c in TRUSTED_CONTACTS],
                    'pin': CANCEL_PIN})


# ══════════════════════════════════════════════════════
#   SOS ALERT
# ══════════════════════════════════════════════════════
@app.route('/sos', methods=['POST'])
def sos():
    data       = request.get_json()
    lat        = data.get('lat')
    lng        = data.get('lng')
    time_str   = data.get('time', utcnow().isoformat())
    maps_link  = f"https://maps.google.com/?q={lat},{lng}" if lat else "GPS unavailable"
    alert_id   = f"alert_{len(alerts)+1}_{int(utcnow().timestamp())}"
    track_link = f"{SERVER_BASE}/track/{alert_id}"

    alerts.append({'id': alert_id, 'lat': lat, 'lng': lng, 'time': time_str,
                   'maps': maps_link, 'audio': False})

    print(f"\n🚨 SOS received! ID={alert_id}  Location={maps_link}")

    if not TRUSTED_CONTACTS:
        print("  WARNING: No trusted contacts!")
        return jsonify({'status': 'no contacts', 'alert_id': alert_id})

    email_body = (
        f"🚨 SOS ALERT — {YOUR_NAME} needs help!\n\n"
        f"Time     : {time_str}\n"
        f"Location : {maps_link}\n\n"
        f"▶ LIVE TRACKING (updates every 10 seconds):\n{track_link}\n\n"
        f"▶ Open in Google Maps: {maps_link}\n\n"
        f"Respond immediately.\n\nAlert ID: {alert_id}"
    )
    sms_body = (
        f"🚨 SOS! {YOUR_NAME} needs help!\nLocation: {maps_link}\nTrack live: {track_link}"
        if lat else
        f"🚨 SOS! {YOUR_NAME} needs help NOW!\nGPS unavailable. Call immediately! Alert: {alert_id}"
    )

    for contact in TRUSTED_CONTACTS:
        send_email(contact['email'], '🚨 SOS - Emergency Alert from SHEild', email_body)
        if contact.get('phone'):
            send_sms(contact['phone'], sms_body)

    return jsonify({'status': 'SOS sent', 'alert_id': alert_id,
                    'maps': maps_link, 'track': track_link})


# ══════════════════════════════════════════════════════
#   AUDIO EVIDENCE
#   Saves file on Render, emails a DOWNLOAD LINK
#   (no attachment — Brevo/Gmail both reject .webm)
# ══════════════════════════════════════════════════════
@app.route('/upload-audio', methods=['POST'])
def upload_audio():
    try:
        if 'audio' not in request.files:
            return jsonify({'status': 'no audio file'}), 400

        audio_file = request.files['audio']
        alert_id   = request.form.get('alert_id', 'unknown')
        fname      = f"{alert_id}.webm"
        save_path  = os.path.join(EVIDENCE_DIR, fname)

        audio_file.save(save_path)
        file_size = os.path.getsize(save_path)
        print(f"\n🎙 Audio saved: {save_path} ({file_size} bytes)")

        # Mark alert as having audio
        for alert in alerts:
            if alert['id'] == alert_id:
                alert['audio']      = True
                alert['audio_file'] = save_path
                alert['audio_link'] = f"{SERVER_BASE}/evidence/{fname}"
                break

        # Public link to play/download the recording
        audio_link = f"{SERVER_BASE}/evidence/{fname}"
        print(f"  Audio link: {audio_link}")

        if not TRUSTED_CONTACTS:
            print("  No contacts to email audio link to")
            return jsonify({'status': 'audio saved, no contacts', 'link': audio_link})

        # Email a clickable download link — no attachment needed
        for contact in TRUSTED_CONTACTS:
            success = send_email(
                to_email = contact['email'],
                subject  = '🎙 Audio Evidence — SHEild SOS Recording',
                body     = (
                    f"Audio evidence was recorded during the SOS alert.\n\n"
                    f"Alert ID  : {alert_id}\n"
                    f"Recorded  : {utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
                    f"▶ LISTEN / DOWNLOAD RECORDING:\n"
                    f"{audio_link}\n\n"
                    f"Click the link above to play or download the 30-second recording.\n"
                    f"Please save it as evidence.\n\n"
                    f"— SHEild Safety System"
                )
            )
            if success:
                print(f"  ✓ Audio link emailed → {contact['email']}")
            else:
                print(f"  ✗ Audio email failed → {contact['email']}")

            # Also SMS the link
            if contact.get('phone'):
                send_sms(contact['phone'],
                         f"🎙 SHEild audio evidence recorded.\nListen: {audio_link}")

        return jsonify({'status': 'audio saved and notified', 'link': audio_link})

    except Exception as e:
        print(f"  ✗ upload_audio error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ══════════════════════════════════════════════════════
#   LATE GPS FOLLOW-UP
# ══════════════════════════════════════════════════════
@app.route('/sos-update', methods=['POST'])
def sos_update():
    data      = request.get_json()
    alert_id  = data.get('alert_id')
    lat       = data.get('lat')
    lng       = data.get('lng')
    if not lat or not lng:
        return jsonify({'status': 'no GPS'}), 400

    maps_link = f"https://maps.google.com/?q={lat},{lng}"
    for alert in alerts:
        if alert['id'] == alert_id:
            alert['lat'] = lat; alert['lng'] = lng; alert['maps'] = maps_link
            break

    print(f"\n📍 GPS follow-up for {alert_id}: {maps_link}")
    for contact in TRUSTED_CONTACTS:
        if contact.get('phone'):
            send_sms(contact['phone'],
                     f"📍 SHEild Location Update\nGPS locked for earlier SOS.\nLocation: {maps_link}")

    return jsonify({'status': 'updated', 'maps': maps_link})


# ══════════════════════════════════════════════════════
#   CONTINUOUS LOCATION UPDATE
# ══════════════════════════════════════════════════════
@app.route('/update-location', methods=['POST'])
def update_location():
    data = request.get_json()
    alert_id = data.get('alert_id')
    lat = data.get('lat'); lng = data.get('lng')
    for alert in alerts:
        if alert['id'] == alert_id:
            alert['lat'] = lat; alert['lng'] = lng
            alert['time'] = utcnow().isoformat()
            alert['maps'] = f"https://maps.google.com/?q={lat},{lng}" if lat else alert['maps']
            break
    return jsonify({'status': 'updated'})


# ══════════════════════════════════════════════════════
#   BATTERY LOW
# ══════════════════════════════════════════════════════
@app.route('/battery-low', methods=['POST'])
def battery_low():
    data     = request.get_json()
    lat      = data.get('lat'); lng = data.get('lng')
    level    = data.get('level', '?')
    time_str = data.get('time', utcnow().isoformat())
    maps     = f"https://maps.google.com/?q={lat},{lng}" if lat else "GPS unavailable"
    alert_id = f"battery_{int(utcnow().timestamp())}"
    track_link = f"{SERVER_BASE}/track/{alert_id}"

    alerts.append({'id': alert_id, 'lat': lat, 'lng': lng, 'time': time_str,
                   'maps': maps, 'audio': False})
    print(f"\n🔋 Battery low: {level}% | {maps}")

    for contact in TRUSTED_CONTACTS:
        send_email(contact['email'],
                   f'🔋 Battery Low ({level}%) — SHEild',
                   f"Battery Low Warning\n\nLevel: {level}%\nTime: {time_str}\n"
                   f"Location: {maps}\n\nTrack live:\n{track_link}\n\n"
                   f"Please check immediately.\n\n— SHEild Safety System")
        if contact.get('phone'):
            send_sms(contact['phone'],
                     f"⚠️ SHEild: Battery {level}%! Last location: {maps}")

    return jsonify({'status': 'battery alert sent', 'track': track_link})


# ══════════════════════════════════════════════════════
#   MAIN
# ══════════════════════════════════════════════════════
if __name__ == '__main__':
    print("=" * 50)
    print("  SHEild — Women Safety System")
    print("=" * 50)
    print(f"  Host    : {SERVER_BASE}")
    print(f"  Render  : {IS_RENDER}")
    print(f"  Evidence: {EVIDENCE_DIR}")
    print("=" * 50)
    app.run(debug=False, host='0.0.0.0', port=SERVER_PORT)