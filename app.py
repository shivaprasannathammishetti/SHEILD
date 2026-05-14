from flask import Flask, render_template, request, jsonify
import smtplib, os, json, socket
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
#   AUTO-DETECT LOCAL IP for live tracking link
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
# ──────────────────────────────────────────────────────
# Runtime state
# ──────────────────────────────────────────────────────
TRUSTED_CONTACTS = []
CANCEL_PIN       = "1234"

os.makedirs('evidence', exist_ok=True)
alerts = []


# ── Load saved config on startup ──────────────────────
def load_config():
    global TRUSTED_CONTACTS, CANCEL_PIN
    if os.path.exists('config.json'):
        with open('config.json') as f:
            saved = json.load(f)
            TRUSTED_CONTACTS = [
                c for c in saved.get('contacts', [])
                if c.get('email')
            ]
            CANCEL_PIN = saved.get('pin', '1234')
        print(f"\nConfig loaded:")
        for c in TRUSTED_CONTACTS:
            print(f"  Contact : {c.get('name')} | {c.get('email')} | {c.get('phone','no phone')}")
        print(f"  PIN     : {CANCEL_PIN}")
        print(f"  Server  : http://{SERVER_HOST}:{SERVER_PORT}\n")
    else:
        print("\nNo config.json found — go to /setup first\n")

load_config()


# ── Helper: send email ────────────────────────────────
def send_email(to_email, subject, body, attachment_path=None):
    try:
        import requests as req
        print(f"  Attempting Brevo email to: {to_email}")
        response = req.post(
            'https://api.brevo.com/v3/smtp/email',
            headers={
                'api-key' : os.environ.get('BREVO_API_KEY', ''),
                'Content-Type': 'application/json'
            },
            json={
                'sender'     : {'email': YOUR_EMAIL},
                'to'         : [{'email': to_email}],
                'subject'    : subject,
                'textContent': body
            },
            timeout=10
        )

        if response.status_code == 201:
            print(f"  Email sent to: {to_email}")
            return True
        else:
            print(f"  Email failed: {response.status_code} — {response.text}")
            return False

    except Exception as e:
        print(f"  Email error: {e}")
        return False


# ── Helper: send SMS via Twilio ───────────────────────
def send_sms(to_phone, body):
    phone = to_phone.strip().replace(' ', '').replace('-', '')
    if not phone:
        print(f"  SMS skipped — no phone number")
        return False

    # Keep last 10 digits only
    phone = phone[-10:]

    try:
        import requests as req

        # ── SMS Gateway app running on your phone ──
        # Make sure phone and laptop are on same WiFi
        # Open SMS Gateway app → tap Start → copy the IP shown
        SMS_GATEWAY_URL = "https://skimmed-upchuck-document.ngrok-free.dev/send-sms"
        response = req.post(
            SMS_GATEWAY_URL,
            json={
                'phone'  : phone,
                'message': body
            },
            timeout=40
        )

        if response.status_code == 200:
            print(f"  SMS sent to: {phone}")
            return True
        else:
            print(f"  SMS failed: {response.status_code} — {response.text}")
            return False

    except Exception as e:
        print(f"  SMS error: {e}")
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


# ── Live tracking pages ───────────────────────────────
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

    with open('config.json', 'w') as f:
        json.dump({
            'contacts' : data.get('contacts', []),
            'pin'      : CANCEL_PIN,
            'gesture'  : data.get('gesture', 'key_s'),
            'from'     : data.get('from', '20'),
            'to'       : data.get('to', '6')
        }, f, indent=2)

    print(f"Setup saved:")
    print(f"  Contacts : {[c.get('email') for c in TRUSTED_CONTACTS]}")
    print(f"  PIN      : {CANCEL_PIN}")

    # Send confirmation email + SMS to all contacts
    for contact in TRUSTED_CONTACTS:
        send_email(
            to_email = contact['email'],
            subject  = 'SHEild — You are now a trusted contact',
            body     = (
                f"Hello {contact.get('name', '')},\n\n"
                f"You have been added as a trusted emergency contact on SHEild.\n\n"
                f"If this person triggers an SOS alert, you will receive an automatic "
                f"emergency email AND SMS with their live GPS location.\n\n"
                f"Please respond immediately if you receive an SOS alert.\n\n"
                f"— SHEild Safety System"
            )
        )
        if contact.get('phone'):
            send_sms(
                to_phone = contact['phone'],
                body     = f"SHEild: You are now a trusted contact for {YOUR_NAME}. You will receive SMS alerts if they need help."
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
    protocol   = 'https' if os.environ.get('RENDER_EXTERNAL_HOSTNAME') else 'http'
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
        print("  WARNING: No trusted contacts — go to /setup first!")
        return jsonify({
            'status'   : 'SOS received but no contacts configured',
            'alert_id' : alert_id,
            'maps'     : maps_link
        })

    # ── Email body ──
    email_body = (
        f"SOS ALERT — {YOUR_NAME} needs help!\n\n"
        f"Time     : {time}\n"
        f"Location : {maps_link}\n\n"
        f"LIVE TRACKING LINK (updates every 10s):\n"
        f"{track_link}\n\n"
        f"Open on Google Maps: {maps_link}\n\n"
        f"This is an automatic emergency alert from SHEild.\n"
        f"Please respond immediately.\n\n"
        f"Alert ID : {alert_id}"
    )

    # ── SMS body (short — SMS has 160 char limit) ──
    if lat:
        sms_body = (
            f"SOS! {YOUR_NAME} needs help NOW!\n"
            f"Location: {maps_link}\n"
            f"Track live: {track_link}"
        )
    else:
        sms_body = (
            f"SOS! {YOUR_NAME} needs help NOW!\n"
            f"GPS unavailable. Call immediately!\n"
            f"Alert: {alert_id}"
        )

    # ── Send to all trusted contacts ──
    for contact in TRUSTED_CONTACTS:
        # Email
        send_email(
            to_email = contact['email'],
            subject  = f'SOS - Emergency Alert from SHEild',
            body     = email_body
        )
        # SMS
        if contact.get('phone'):
            send_sms(
                to_phone = contact['phone'],
                body     = sms_body
            )

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
    filename   = f"evidence/{alert_id}.webm"
    audio_file.save(filename)

    print(f"\nAudio evidence saved: {filename}")

    for alert in alerts:
        if alert['id'] == alert_id:
            alert['audio']      = True
            alert['audio_file'] = filename
            break

    for contact in TRUSTED_CONTACTS:
        send_email(
            to_email        = contact['email'],
            subject         = 'Audio Evidence — SHEild SOS Recording',
            body            = (
                f"Audio evidence recording is attached.\n\n"
                f"Alert ID  : {alert_id}\n"
                f"Recorded  : {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
                f"This 30-second recording was captured silently "
                f"during the SOS alert.\n"
                f"Keep this as evidence.\n\n"
                f"— SHEild Safety System"
            ),
            attachment_path = filename
        )

    return jsonify({'status': 'audio saved', 'file': filename})


# ── Update location (continuous tracking) ─────────────
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
            alert['maps'] = (
                f"https://maps.google.com/?q={lat},{lng}"
                if lat else alert['maps']
            )
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

    # ── Create a real alert entry so live tracking works ──
    alert_id   = f"battery_{int(datetime.utcnow().timestamp())}"
    protocol   = 'https' if os.environ.get('RENDER_EXTERNAL_HOSTNAME') else 'http'
    track_link = f"{protocol}://{SERVER_HOST}/track/{alert_id}"

    alert = {
        'id'   : alert_id,
        'lat'  : lat,
        'lng'  : lng,
        'time' : time,
        'maps' : maps,
        'audio': False
    }
    alerts.append(alert)

    print(f"\nBattery low alert! Level: {level}% | {maps}")

    for contact in TRUSTED_CONTACTS:
        send_email(
            to_email = contact['email'],
            subject  = f'Battery Low ({level}%) — SHEild Location Update',
            body     = (
                f"Battery Low Warning\n\n"
                f"Battery level : {level}%\n"
                f"Time          : {time}\n"
                f"Last location : {maps}\n\n"
                f"LIVE TRACKING LINK (updates every 10s):\n"
                f"{track_link}\n\n"
                f"The phone battery is critically low.\n"
                f"This may be the last location update.\n"
                f"Please check on her immediately.\n\n"
                f"— SHEild Safety System"
            )
        )
        if contact.get('phone'):
            send_sms(
                to_phone = contact['phone'],
                body     = f"SHEild: Battery low ({level}%)! Track live: {track_link}"
            )

    return jsonify({'status': 'battery alert sent', 'track': track_link})
# ── Alert log API ─────────────────────────────────────
@app.route('/alerts')
def get_alerts():
    return jsonify(alerts)
@app.route('/history')
def history():
    return render_template('history.html')

@app.route('/evidence/<filename>')
def serve_evidence(filename):
    from flask import send_from_directory
    return send_from_directory('evidence', filename)
@app.route('/saferoute')
def saferoute():
    return render_template('saferoute.html')
# ── Main ──────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 50)
    print("  SHEild — Women Safety System")
    print("=" * 50)
    print(f"  Local IP  : {SERVER_HOST}")
    print(f"  App       : http://{SERVER_HOST}:{SERVER_PORT}")
    print(f"  Setup     : http://{SERVER_HOST}:{SERVER_PORT}/setup")
    print(f"  Dashboard : http://{SERVER_HOST}:{SERVER_PORT}/dashboard")
    print(f"  History   : http://{SERVER_HOST}:{SERVER_PORT}/history")
    print(f"  Live      : http://{SERVER_HOST}:{SERVER_PORT}/live")
    print(f"  SafeRoute : http://{SERVER_HOST}:{SERVER_PORT}/saferoute")
    print("=" * 50)
port = int(os.environ.get('PORT', 5000))
app.run(host="0.0.0.0", port=port)