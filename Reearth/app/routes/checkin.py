from flask import Blueprint, request, jsonify
from itsdangerous import TimestampSigner, BadSignature
from werkzeug.utils import secure_filename
import os

checkin = Blueprint('checkin', __name__)
signer = TimestampSigner('eco-nova-secret')

@checkin.route("/verify_checkin_auth", methods=["POST"])
def verify_checkin_auth():
    event_id = request.form.get("event_id")
    passcode = request.form.get("passcode", "")
    qr_image = request.files.get("qr_image")

    expected_passcode = "ECO2025"  # TODO: Pull from DB per event

    # 1. Passcode check
    if passcode and passcode == expected_passcode:
        return jsonify({"success": True})

    # 2. QR image check (Placeholder logic – you can scan and decode using OpenCV or pyzbar)
    if qr_image:
        filename = secure_filename(qr_image.filename)
        filepath = os.path.join("temp", filename)
        qr_image.save(filepath)
        # Decode QR logic here (not shown for brevity)
        os.remove(filepath)
        # Suppose we verified QR matches event_id
        return jsonify({"success": True})

    return jsonify({"success": False, "message": "Invalid credentials"})
