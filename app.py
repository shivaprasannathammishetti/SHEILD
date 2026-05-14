from flask import Flask, render_template, request, jsonify
import smtplib, os, json, socket, base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

app = Flask(__name__)

# ══════════════════════════════════════════════════════
#   YOUR GMAIL CREDENTIALS
# ══════════════════════════════════════════════════════
YOUR_EMAIL    = os.environ.get('YOUR_EMAIL', 'thammishettishivaprasanna@gmail.com')
YOUR_PASSWORD = os.environ.get('YOUR_PASSWORD', 'yxfzhltvgyvdoahz')

# ══════════════════════════════════════════════════════
#   YOUR NAME shown in alerts
# ══════════════════════════════════════════════════════
YOUR_NAME = "SHEild User"

# ══════════════════════════════════════════════════════
#   SERVER HOST — auto detect Render or local
# ══════════════════════════════════════════════════════
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'

SERVER_HOST = os.environ.get('RENDER_EXTERNAL_HOSTNAME', get_local_ip())
SERVER_PORT = 443 if os.environ.get('RENDER_EXTERNAL_HOSTNAME') else 5000
IS_RENDER   = bool(os.environ.get('RENDER_EXTERNAL_HOSTNAME'))

# ──────────────────────────────────────────────────────
# Runtime state
# ──────────────────────────────────────────────────────
TRUSTED_CONTACTS = []
CANCEL_PIN       = "1234"

# Evidence folder — absolute path so it works on Render
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
EVIDENCE_DIR = os.path.join(BASE_DIR, 'evidence')
os.makedirs(EVIDENCE_DIR, exist_ok=True)

alerts = []


# ── Load saved config on startup ──────────────────────
def load_config():
    global TRUSTED_CONTACTS, CANCEL_PIN
    config_path = os.path.join(BASE_DIR, 'config.json')
    if os.path.exists(config_path):
        with open(config_path) as f:
            saved = json.load(f)
            TRUSTED_CONTACTS = [
                c for c in saved.get('contacts', [])
                if c.get('email')
            ]
            CANCEL_PIN = saved.get('pin', '1234')
        print(f"\nConfig loaded:")
        for c in TRUSTED_CONTACTS:
            print(f"  Contact : {c.get('name')} | {c.get('email')} | {c.get('phone','no phone')}")
        print(f"  PIN     : {CANCEL_PIN}\n")
    else:
        print("\nNo config.json found — go to /setup first\n")

load_config()


# ══════════════════════════════════════════════════════
#   SEND EMAIL
#   Uses Brevo API — supports attachments via base64
# ══════════════════════════════════════════════════════
def send_email(to_email, subject, body, attachment_path=None):
    try:
        import requests as req
        print(f"  Attempting Brevo email to: {to_email}")

        payload = {
            'sender'     : {'email': YOUR_EMAIL},
            'to'         : [{'email': to_email}],
            'subject'    : subject,
            'textContent': body
        }

        # ── Add attachment if file exists ──
        if attachment_path and os.path.exists(attachment_path):
            file_size = os.path.getsize(attachment_path)
            print(f"  Attaching file: {attachment_path} ({file_size} bytes)")

            with open(attachment_path, 'rb') as f:
                file_data = f.read()

            # Brevo requires base64 encoded attachment
            encoded_data = base64.b64encode(file_data).decode('utf-8')
            fname        = os.path.basename(attachment_path)

            payload['attachment'] = [{
                'content': encoded_data,
                'name'   : fname
            }]
            print(f"  Attachment encoded: {len(encoded_data)} chars base64")
        else:
            if attachment_path:
                print(f"  WARNING: Attachment file not found: {attachment_path}")

        response = req.post(
            'https://api.brevo.com/v3/smtp/email',
            headers={
                'api-key'     : os.environ.get('BREVO_API_KEY', ''),
                'Content-Type': 'application/json'
            },
            json=payload,
            timeout=15
        )

        if response.status_code == 201:
            print(f"  ✓ Email sent to: {to_email}")
            return True
        else:
            print(f"  ✗ Email failed: {response.status_code} — {response.text[:200]}")
            return False

    except Exception as e:
        print(f"  ✗ Email error: {e}")
        return False


# ══════════════════════════════════════════════════════
#   SEND SMS via SMS Gateway app
# ══════════════════════════════════════════════════════
def send_sms(to_phone, body):
    phone = to_phone.strip().replace(' ', '').replace('-', '')
    if not phone:
        print(f"  SMS skipped — no phone number")
        return False

    phone = phone[-10:]

    try:
        import requests as req
        SMS_GATEWAY_URL = os.environ.get('SMS_GATEWAY_URL', 'https://skimmed-upchuck-document.ngrok-free.dev/send-sms')
        response = req.post(
            SMS_GATEWAY_URL,
            json={'phone': phone, 'message': body},
            timeout=40
        )

        if response.status_code == 200:
            print(f"  ✓ SMS sent to: {phone}")
            return True
        else:
            print(f"  ✗ SMS failed: {response.status_code}")
            return False

    except Exception as e:
        print(f"  ✗ SMS error: {e}")
        return False


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


# ── Live tracking ─────────────────────────────────────
@app.route('/track/<alert_id>')
def track(alert_id):
    alert = next((a for a in alerts if a['id'] == alert_id), None)
    return render_template('track.html', alert=alert, alert_id=alert_id)

@app.route('/track-data/<alert_id>')
def track_data(alert_id):
    alert = next((a for a in alerts if a['id'] == alert_id), None)
    if alert:
        return jsonify({
            'lat'  : alert.get('lat'),
            'lng'  : alert.get('lng'),
            'time' : alert.get('time'),
            'maps' : alert.get('maps'),
            'audio': alert.get('audio', False)
        })
    return jsonify({}), 404


# ── Save setup config ─────────────────────────────────
@app.route('/setup', methods=['POST'])
def save_setup():
    global TRUSTED_CONTACTS, CANCEL_PIN

    data = request.get_json()
    print(f"\nSetup received: {data}")

    TRUSTED_CONTACTS = [
        c for c in data.get('contacts', [])
        if c.get('email') and c['email'].strip()
    ]
    CANCEL_PIN = data.get('pin', '1234')

    config_path = os.path.join(BASE_DIR, 'config.json')
    with open(config_path, 'w') as f:
        json.dump({
            'contacts' : data.get('contacts', []),
            'pin'      : CANCEL_PIN,
            'gesture'  : data.get('gesture', 'key_s'),
            'from'     : data.get('from', '20'),
            'to'       : data.get('to', '6')
        }, f, indent=2)

    print(f"Setup saved — contacts: {[c.get('email') for c in TRUSTED_CONTACTS]}")

    for contact in TRUSTED_CONTACTS:
        send_email(
            to_email = contact['email'],
            subject  = 'SHEild — You are now a trusted contact',
            body     = (
                f"Hello {contact.get('name', '')},\n\n"
                f"You have been added as a trusted emergency contact on SHEild.\n\n"
                f"If this person triggers an SOS alert, you will receive an automatic "
                f"emergency email with their live GPS location.\n\n"
                f"Please respond immediately if you receive an SOS alert.\n\n"
                f"— SHEild Safety System"
            )
        )

    return jsonify({
        'status'   : 'saved',
        'contacts' : [c['email'] for c in TRUSTED_CONTACTS],
        'pin'      : CANCEL_PIN
    })


# ── Receive SOS alert ─────────────────────────────────
@app.route('/sos', methods=['POST'])
def sos():
    data = request.get_json()
    lat  = data.get('lat')
    lng  = data.get('lng')
    time = data.get('time', datetime.utcnow().isoformat())

    maps_link  = f"https://maps.google.com/?q={lat},{lng}" if lat else "GPS unavailable"
    alert_id   = f"alert_{len(alerts)+1}_{int(datetime.utcnow().timestamp())}"
    protocol   = 'https' if IS_RENDER else 'http'
    track_link = f"{protocol}://{SERVER_HOST}/track/{alert_id}"

    alert = {
        'id'    : alert_id,
        'lat'   : lat,
        'lng'   : lng,
        'time'  : time,
        'maps'  : maps_link,
        'audio' : False
    }
    alerts.append(alert)

    print(f"\nSOS received!")
    print(f"  Alert ID   : {alert_id}")
    print(f"  Location   : {maps_link}")
    print(f"  Live track : {track_link}")
    print(f"  Contacts   : {[c.get('email') for c in TRUSTED_CONTACTS]}")

    if not TRUSTED_CONTACTS:
        print("  WARNING: No trusted contacts configured!")
        return jsonify({
            'status'   : 'SOS received but no contacts configured',
            'alert_id' : alert_id,
            'maps'     : maps_link
        })

    email_body = (
        f"🚨 SOS ALERT — {YOUR_NAME} needs help!\n\n"
        f"Time     : {time}\n"
        f"Location : {maps_link}\n\n"
        f"LIVE TRACKING LINK (updates every 10s):\n"
        f"{track_link}\n\n"
        f"Open on Google Maps: {maps_link}\n\n"
        f"This is an automatic emergency alert from SHEild.\n"
        f"Please respond immediately.\n\n"
        f"Alert ID : {alert_id}"
    )

    sms_body = (
        f"SOS! {YOUR_NAME} needs help NOW!\n"
        f"Location: {maps_link}\nTrack: {track_link}"
        if lat else
        f"SOS! {YOUR_NAME} needs help NOW!\nGPS unavailable. Call immediately!"
    )

    for contact in TRUSTED_CONTACTS:
        send_email(to_email=contact['email'], subject='🚨 SOS - Emergency Alert from SHEild', body=email_body)
        if contact.get('phone'):
            send_sms(to_phone=contact['phone'], body=sms_body)

    return jsonify({
        'status'   : 'SOS sent',
        'alert_id' : alert_id,
        'maps'     : maps_link,
        'track'    : track_link
    })


# ── Receive audio evidence ────────────────────────────
@app.route('/upload-audio', methods=['POST'])
def upload_audio():
    if 'audio' not in request.files:
        return jsonify({'status': 'no audio file'}), 400

    audio_file = request.files['audio']
    alert_id   = request.form.get('alert_id', 'unknown')

    # ── Save to absolute path ──
    filename = os.path.join(EVIDENCE_DIR, f"{alert_id}.webm")
    audio_file.save(filename)

    file_size = os.path.getsize(filename)
    print(f"\n🎙 Audio evidence saved: {filename} ({file_size} bytes)")

    # Mark alert as having audio
    for alert in alerts:
        if alert['id'] == alert_id:
            alert['audio']      = True
            alert['audio_file'] = filename
            break

    # ── Send downloadable audio evidence link ──
audio_link = f"https://sheild-e86f.onrender.com/evidence/{alert_id}.webm"

for contact in TRUSTED_CONTACTS:
    success = send_email(
        to_email = contact['email'],
        subject  = '🎙 Audio Evidence — SHEild SOS Recording',
        body     = (
            f"Audio evidence recording was captured during the SOS alert.\n\n"
            f"Alert ID : {alert_id}\n\n"
            f"Audio Evidence Link:\n"
            f"{audio_link}\n\n"
            f"Open this link in browser to hear/download the recording.\n\n"
            f"— SHEild Safety System"
        )
    )

    if success:
        print(f"  ✓ Audio evidence link sent to: {contact['email']}")
    else:
        print(f"  ✗ Audio email failed for: {contact['email']}")

# ── Serve audio evidence files ────────────────────────
@app.route('/evidence/<filename>')
def serve_evidence(filename):
    from flask import send_from_directory
    return send_from_directory(EVIDENCE_DIR, filename)


# ── Update location ───────────────────────────────────
@app.route('/update-location', methods=['POST'])
def update_location():
    data     = request.get_json()
    alert_id = data.get('alert_id')
    lat      = data.get('lat')
    lng      = data.get('lng')

    for alert in alerts:
        if alert['id'] == alert_id:
            alert['lat']  = lat
            alert['lng']  = lng
            alert['time'] = datetime.utcnow().isoformat()
            alert['maps'] = f"https://maps.google.com/?q={lat},{lng}" if lat else alert['maps']
            print(f"  Location updated: {alert_id} → {lat}, {lng}")
            break

    return jsonify({'status': 'updated'})


# ── Battery low alert ─────────────────────────────────
@app.route('/battery-low', methods=['POST'])
def battery_low():
    data  = request.get_json()
    lat   = data.get('lat')
    lng   = data.get('lng')
    level = data.get('level', '?')
    time  = data.get('time', datetime.utcnow().isoformat())
    maps  = f"https://maps.google.com/?q={lat},{lng}" if lat else "GPS unavailable"

    alert_id   = f"battery_{int(datetime.utcnow().timestamp())}"
    protocol   = 'https' if IS_RENDER else 'http'
    track_link = f"{protocol}://{SERVER_HOST}/track/{alert_id}"

    alerts.append({
        'id': alert_id, 'lat': lat, 'lng': lng,
        'time': time, 'maps': maps, 'audio': False
    })

    print(f"\nBattery low alert! Level: {level}% | {maps}")

    for contact in TRUSTED_CONTACTS:
        send_email(
            to_email = contact['email'],
            subject  = f'🔋 Battery Low ({level}%) — SHEild Location Update',
            body     = (
                f"Battery Low Warning\n\n"
                f"Battery level : {level}%\n"
                f"Time          : {time}\n"
                f"Last location : {maps}\n\n"
                f"LIVE TRACKING LINK:\n{track_link}\n\n"
                f"The phone battery is critically low.\n"
                f"This may be the last location update.\n"
                f"Please check on her immediately.\n\n"
                f"— SHEild Safety System"
            )
        )
        if contact.get('phone'):
            send_sms(to_phone=contact['phone'], body=f"SHEild: Battery low ({level}%)! Track: {track_link}")

    return jsonify({'status': 'battery alert sent', 'track': track_link})


# ── Alert log API ─────────────────────────────────────
@app.route('/alerts')
def get_alerts():
    return jsonify(alerts)


# ── Main ──────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 50)
    print("  SHEild — Women Safety System")
    print("=" * 50)
    print(f"  Host      : {SERVER_HOST}")
    print(f"  Render    : {IS_RENDER}")
    print(f"  Evidence  : {EVIDENCE_DIR}")
    print("=" * 50)

port = int(os.environ.get('PORT', 5000))
app.run(host="0.0.0.0", port=port)