import requests as req
from flask import Flask, render_template, request, jsonify, send_from_directory
import os, json, socket, base64
from datetime import datetime, timezone

app = Flask(__name__)

# ══════════════════════════════════════════════════════
#   BREVO EMAIL API  (works on Render free plan)
#   Gmail SMTP ports 465/587 are BLOCKED on Render free.
#   Sign up free at https://app.brevo.com
#   Top menu → SMTP & API → API Keys → Create key
#   Add to Render env: BREVO_API_KEY = xkeysib-xxxxx
# ══════════════════════════════════════════════════════
BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')
YOUR_EMAIL    = os.environ.get('YOUR_EMAIL', 'thammishettishivaprasanna@gmail.com')
YOUR_NAME     = "SHEild User"

# ══════════════════════════════════════════════════════
#   HOST — auto-detects Render or local
# ══════════════════════════════════════════════════════
RENDER_HOST = os.environ.get('RENDER_EXTERNAL_HOSTNAME', '')
IS_RENDER   = bool(RENDER_HOST)
SERVER_BASE = f"https://{RENDER_HOST}" if IS_RENDER else "http://localhost:5000"
SERVER_PORT = int(os.environ.get('PORT', 5000))

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
EVIDENCE_DIR = os.path.join(BASE_DIR, 'evidence')
CONFIG_PATH  = os.path.join(BASE_DIR, 'config.json')
os.makedirs(EVIDENCE_DIR, exist_ok=True)

TRUSTED_CONTACTS = []
CANCEL_PIN       = "1234"
alerts           = []


def utcnow():
    return datetime.now(timezone.utc)


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
        print(f"  PIN   : {CANCEL_PIN}")
        print(f"  Host  : {SERVER_BASE}")
        print(f"  Email : {'Brevo ready ✓' if BREVO_API_KEY else '✗ set BREVO_API_KEY in Render env'}\n")
    else:
        print("\nNo config.json — go to /setup first\n")

load_config()


# ══════════════════════════════════════════════════════
#   SEND EMAIL via Brevo HTTP API
#   No attachments — sends download links instead
#   (Brevo rejects .webm; links work better anyway)
# ══════════════════════════════════════════════════════
def send_email(to_email, subject, body):
    if not BREVO_API_KEY:
        print(f"  ✗ Email skipped — BREVO_API_KEY not set")
        return False
    try:
        r = req.post(
            'https://api.brevo.com/v3/smtp/email',
            headers={'api-key': BREVO_API_KEY, 'Content-Type': 'application/json'},
            json={
                'sender'     : {'name': 'SHEild Safety', 'email': YOUR_EMAIL},
                'to'         : [{'email': to_email}],
                'subject'    : subject,
                'textContent': body
            },
            timeout=15
        )
        if r.status_code == 201:
            print(f"  ✓ Email → {to_email}")
            return True
        else:
            print(f"  ✗ Email failed {r.status_code}: {r.text[:150]}")
            return False
    except Exception as e:
        print(f"  ✗ Email error: {e}")
        return False


# ══════════════════════════════════════════════════════
#   SMS — handled FREE on the client (browser)
#
#   The index.html already calls sendNativeSMS() which
#   uses the Android/iOS  sms:  URL scheme to open the
#   phone's built-in SMS app with a pre-filled message.
#   This is 100% free, works offline, needs no API key.
#
#   This server function is a no-op kept so existing
#   call-sites don't crash.
# ══════════════════════════════════════════════════════
def send_sms(to_phone, body):
    print(f"  SMS: sent via browser native SMS (free, no API needed)")
    return True


# ── Pages ─────────────────────────────────────────────
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


# ── Setup ─────────────────────────────────────────────
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
            contact['email'],
            'SHEild — You are now a trusted contact',
            f"Hello {contact.get('name', '')},\n\n"
            f"You have been added as a trusted emergency contact on SHEild.\n\n"
            f"If an SOS is triggered you will receive an immediate email with a live GPS link.\n\n"
            f"Please respond immediately if you receive an SOS alert.\n\n"
            f"— SHEild Safety System"
        )

    return jsonify({'status': 'saved',
                    'contacts': [c['email'] for c in TRUSTED_CONTACTS],
                    'pin': CANCEL_PIN})


# ── SOS ───────────────────────────────────────────────
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

    print(f"\n🚨 SOS! ID={alert_id}")
    print(f"  Location  : {maps_link}")
    print(f"  Track     : {track_link}")

    if not TRUSTED_CONTACTS:
        print("  WARNING: No trusted contacts!")
        return jsonify({'status': 'no contacts', 'alert_id': alert_id})

    email_body = (
        f"🚨 SOS ALERT — {YOUR_NAME} needs help!\n\n"
        f"Time     : {time_str}\n"
        f"Location : {maps_link}\n\n"
        f"▶ LIVE TRACKING (updates every 10s):\n{track_link}\n\n"
        f"▶ Google Maps: {maps_link}\n\n"
        f"Please respond immediately.\n\nAlert ID: {alert_id}"
    )

    for contact in TRUSTED_CONTACTS:
        send_email(contact['email'], '🚨 SOS - Emergency Alert from SHEild', email_body)
        # Native SMS is fired from browser (index.html → sendNativeSMS)

    return jsonify({'status': 'SOS sent', 'alert_id': alert_id,
                    'maps': maps_link, 'track': track_link})


# ══════════════════════════════════════════════════════
#   AUDIO EVIDENCE
#   Saves file, emails a clickable DOWNLOAD LINK.
#   Brevo rejects .webm attachments → link is better.
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
        file_size  = os.path.getsize(save_path)

        print(f"\n🎙 Audio saved: {fname} ({file_size} bytes)")

        for alert in alerts:
            if alert['id'] == alert_id:
                alert['audio'] = True
                alert['audio_file'] = save_path
                break

        # Public link — contact clicks to listen/download
        audio_link = f"{SERVER_BASE}/evidence/{fname}"
        print(f"  Link: {audio_link}")

        for contact in TRUSTED_CONTACTS:
            ok = send_email(
                contact['email'],
                '🎙 Audio Evidence — SHEild SOS Recording',
                f"Audio evidence was recorded during the SOS alert.\n\n"
                f"Alert ID  : {alert_id}\n"
                f"Recorded  : {utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
                f"File size : {file_size} bytes\n\n"
                f"▶ LISTEN / DOWNLOAD:\n"
                f"{audio_link}\n\n"
                f"Click the link to play or download the recording.\n"
                f"Works in Chrome, Firefox, VLC.\n\n"
                f"— SHEild Safety System"
            )
            print(f"  {'✓' if ok else '✗'} Audio email → {contact['email']}")

        return jsonify({'status': 'audio saved', 'link': audio_link})

    except Exception as e:
        print(f"  ✗ upload_audio error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ── Continuous location update ────────────────────────
@app.route('/update-location', methods=['POST'])
def update_location():
    data = request.get_json()
    for alert in alerts:
        if alert['id'] == data.get('alert_id'):
            alert['lat']  = data.get('lat')
            alert['lng']  = data.get('lng')
            alert['time'] = utcnow().isoformat()
            if data.get('lat'):
                alert['maps'] = f"https://maps.google.com/?q={data['lat']},{data['lng']}"
            break
    return jsonify({'status': 'updated'})


# ── Late GPS follow-up ────────────────────────────────
@app.route('/sos-update', methods=['POST'])
def sos_update():
    data = request.get_json()
    lat  = data.get('lat'); lng = data.get('lng')
    if not lat or not lng:
        return jsonify({'status': 'no GPS'}), 400
    maps_link = f"https://maps.google.com/?q={lat},{lng}"
    for alert in alerts:
        if alert['id'] == data.get('alert_id'):
            alert['lat'] = lat; alert['lng'] = lng; alert['maps'] = maps_link
            break
    print(f"  📍 GPS follow-up: {maps_link}")
    return jsonify({'status': 'updated', 'maps': maps_link})


# ── Battery low ───────────────────────────────────────
@app.route('/battery-low', methods=['POST'])
def battery_low():
    data     = request.get_json()
    lat      = data.get('lat'); lng = data.get('lng')
    level    = data.get('level', '?')
    time_str = data.get('time', utcnow().isoformat())
    maps     = f"https://maps.google.com/?q={lat},{lng}" if lat else "GPS unavailable"
    alert_id = f"battery_{int(utcnow().timestamp())}"
    track_link = f"{SERVER_BASE}/track/{alert_id}"
    alerts.append({'id': alert_id, 'lat': lat, 'lng': lng,
                   'time': time_str, 'maps': maps, 'audio': False})
    print(f"\n🔋 Battery low: {level}%")
    for contact in TRUSTED_CONTACTS:
        send_email(contact['email'], f'🔋 Battery Low ({level}%) — SHEild',
                   f"Battery Low Warning\n\nLevel: {level}%\nTime: {time_str}\n"
                   f"Location: {maps}\n\nTrack live:\n{track_link}\n\n"
                   f"Please check immediately.\n\n— SHEild Safety System")
    return jsonify({'status': 'battery alert sent', 'track': track_link})
@app.route('/manifest.json')
def manifest():
    from flask import send_from_directory
    return send_from_directory(BASE_DIR, 'manifest.json')
# ── Main ──────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 50)
    print("  SHEild — Women Safety System")
    print(f"  Host    : {SERVER_BASE}")
    print(f"  Render  : {IS_RENDER}")
    print("=" * 50)
    app.run(debug=False, host='0.0.0.0', port=SERVER_PORT)