# SIRA - Simple Print Shop System

This is a minimal Flask-based print shop system (SIRA) with two roles: **customer** and **shopkeeper**.

Features:
- Signup / Login / Logout with role selection (customer or shopkeeper).
- Shopkeepers can add services (name, cost) and upload a QR code image.
- Customers can select a shopkeeper, choose a service, upload a document, provide optional details (paper size, sides, color, additional requirements), and view the shopkeeper's QR to pay.
- Shopkeepers receive order notifications and can update order status.
- Simple SQLite database, file uploads stored in `static/uploads` and `static/qr`.
- Intended to be simple and easy — no complications.

## How to run (local)
1. Create a virtual environment (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate   # on Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Run the app:
   ```bash
   export FLASK_APP=app.py
   flask run
   ```
   By default it runs on http://127.0.0.1:5000

3. Use the app:
   - Register as a **shopkeeper** to add services and upload a QR code.
   - Register as a **customer** to place orders.

## Notes
- This is a minimal educational/demo project. For production use, secure file handling, CSRF protection, user input validation, and stronger authentication are required.
- The app stores uploaded files in `static/uploads` and `static/qr`.
- The project name is **SIRA**.

Enjoy — Hare Krishna!
