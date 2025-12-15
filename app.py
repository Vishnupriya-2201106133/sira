from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
import sqlite3, os
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime

# ---------------- RENDER SAFE PATH ----------------
DB_PATH = "/data/sira.db"

UPLOAD_FOLDER = "static/uploads"
QR_FOLDER = "static/qr"

os.makedirs("/data", exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = "change-me-now"

# ---------------- DATABASE ----------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        role TEXT,
        shop_name TEXT
    );

    CREATE TABLE IF NOT EXISTS services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id INTEGER,
        name TEXT,
        cost REAL
    );

    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        shop_id INTEGER,
        service_id INTEGER,
        doc_filename TEXT,
        paper_size TEXT,
        sides TEXT,
        color TEXT,
        copies INTEGER,
        additional TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS qr (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id INTEGER UNIQUE,
        qr_filename TEXT
    );
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------- USER SESSION ----------------
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return user

# ---------------- HOME ----------------
@app.route("/")
def index():
    return render_template("index.html", user=current_user())

# ---------------- AUTH ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":

        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role")
        shop_name = request.form.get("shop_name") or None

        # allow admin creation also
        if not email or not password or role not in ["customer", "shopkeeper", "admin"]:
            flash("Fill all fields properly.")
            return redirect(url_for("register"))

        hashed = generate_password_hash(password)

        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users (name,email,password,role,shop_name) VALUES (?,?,?,?,?)",
                (name, email, hashed, role, shop_name),
            )
            conn.commit()
        except:
            flash("Error: Email already in use.")
        finally:
            conn.close()

        flash("Registered successfully.")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            return redirect(url_for("index"))

        flash("Invalid credentials.")
        return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ---------------- ADMIN ----------------
@app.route("/admin/dashboard")
def admin_dashboard():
    user = current_user()
    if not user or user["role"] != "admin":
        flash("Admin access only.")
        return redirect(url_for("login"))

    conn = get_db()

    shopkeepers = conn.execute(
        "SELECT id, name, email, shop_name FROM users WHERE role='shopkeeper'"
    ).fetchall()

    customers = conn.execute(
        "SELECT id, name, email FROM users WHERE role='customer'"
    ).fetchall()

    shop_orders = conn.execute("""
        SELECT sh.id, COALESCE(sh.shop_name, sh.name) AS shop_name, COUNT(o.id) AS order_count
        FROM users sh
        LEFT JOIN orders o ON sh.id = o.shop_id
        WHERE sh.role='shopkeeper'
        GROUP BY sh.id
        ORDER BY order_count DESC
    """).fetchall()

    today = datetime.utcnow().date().isoformat()
    today_count = conn.execute(
        "SELECT COUNT(*) AS total FROM orders WHERE DATE(created_at)=?",
        (today,)
    ).fetchone()["total"]

    conn.close()

    return render_template(
        "dashboard_admin.html",
        user=user,
        shopkeepers=shopkeepers,
        customers=customers,
        shop_orders=shop_orders,
        daily_orders=today_count,
    )

@app.route("/admin/orders")
def admin_orders():
    user = current_user()
    if not user or user["role"] != "admin":
        flash("Admin access only.")
        return redirect(url_for("login"))

    conn = get_db()
    orders = conn.execute("""
        SELECT o.*,
               c.name AS customer_name,
               s.name AS service_name,
               sh.shop_name AS shop_name,
               sh.name AS shopkeeper_name
        FROM orders o
        LEFT JOIN users c ON o.customer_id = c.id
        LEFT JOIN services s ON o.service_id = s.id
        LEFT JOIN users sh ON o.shop_id = sh.id
        ORDER BY o.created_at DESC
    """).fetchall()
    conn.close()

    return render_template("admin_orders.html", user=user, orders=orders)

# ---------------- SHOPKEEPER ----------------
@app.route("/shop/dashboard")
def shop_dashboard():
    user = current_user()
    if not user or user["role"] != "shopkeeper":
        flash("Login as shopkeeper.")
        return redirect(url_for("login"))

    conn = get_db()

    services = conn.execute("SELECT * FROM services WHERE shop_id=?", (user["id"],)).fetchall()

    orders = conn.execute("""
        SELECT o.*, c.name AS customer_name, s.name AS service_name
        FROM orders o
        LEFT JOIN users c ON o.customer_id = c.id
        LEFT JOIN services s ON o.service_id = s.id
        WHERE o.shop_id=?
        ORDER BY o.created_at DESC
    """, (user["id"],)).fetchall()

    qr = conn.execute("SELECT * FROM qr WHERE shop_id=?", (user["id"],)).fetchone()

    conn.close()

    return render_template(
        "dashboard_shopkeeper.html",
        user=user,
        services=services,
        orders=orders,
        qr=qr,
    )

@app.route("/shop/add_service", methods=["POST"])
def add_service():
    user = current_user()
    if not user or user["role"] != "shopkeeper":
        return redirect(url_for("login"))

    name = request.form.get("name")
    cost = float(request.form.get("cost") or 0)

    conn = get_db()
    conn.execute("INSERT INTO services (shop_id,name,cost) VALUES (?,?,?)", 
                 (user["id"], name, cost))
    conn.commit()
    conn.close()

    flash("Service added.")
    return redirect(url_for("shop_dashboard"))

@app.route("/shop/upload_qr", methods=["POST"])
def upload_qr():
    user = current_user()
    if not user or user["role"] != "shopkeeper":
        return redirect(url_for("login"))

    file = request.files.get("qr")
    if not file or not file.filename:
        flash("No file selected.")
        return redirect(url_for("shop_dashboard"))

    filename = secure_filename(f"{user['id']}_qr.png")
    file.save(os.path.join(QR_FOLDER, filename))

    conn = get_db()
    exists = conn.execute(
        "SELECT * FROM qr WHERE shop_id=?", (user["id"],)
    ).fetchone()

    if exists:
        conn.execute("UPDATE qr SET qr_filename=? WHERE shop_id=?", 
                     (filename, user["id"]))
    else:
        conn.execute("INSERT INTO qr (shop_id,qr_filename) VALUES (?,?)", 
                     (user["id"], filename))

    conn.commit()
    conn.close()

    flash("QR uploaded.")
    return redirect(url_for("shop_dashboard"))

@app.route("/shop/update_order/<int:order_id>", methods=["POST"])
def update_order(order_id):
    user = current_user()
    if not user or user["role"] != "shopkeeper":
        return redirect(url_for("login"))

    status = request.form.get("status")

    conn = get_db()
    conn.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    conn.commit()
    conn.close()

    return redirect(url_for("shop_dashboard"))

# ---------------- CUSTOMER ----------------
@app.route("/customer/dashboard")
def customer_dashboard():
    user = current_user()
    if not user or user["role"] != "customer":
        return redirect(url_for("login"))

    conn = get_db()

    orders = conn.execute("""
        SELECT o.*, s.name AS service_name, sh.shop_name AS shop_name, q.qr_filename
        FROM orders o
        LEFT JOIN services s ON o.service_id = s.id
        LEFT JOIN users sh ON o.shop_id = sh.id
        LEFT JOIN qr q ON sh.id = q.shop_id
        WHERE o.customer_id=?
        ORDER BY o.created_at DESC
    """, (user["id"],)).fetchall()

    shops = conn.execute("SELECT * FROM users WHERE role='shopkeeper'").fetchall()
    conn.close()

    return render_template("dashboard_customer.html", user=user, orders=orders, shops=shops)

@app.route("/customer/new_order", methods=["GET", "POST"])
def new_order():
    user = current_user()
    if not user or user["role"] != "customer":
        return redirect(url_for("login"))

    conn = get_db()
    shops = conn.execute("SELECT * FROM users WHERE role='shopkeeper'").fetchall()

    if request.method == "POST":

        shop_id = request.form.get("shop_id")
        service_id = request.form.get("service_id")
        paper_size = request.form.get("paper_size")
        sides = request.form.get("sides")
        color = request.form.get("color") or "Not required"
        copies = int(request.form.get("copies") or 1)
        additional = request.form.get("additional") or ""

        file = request.files.get("document")
        filename = None

        if file and file.filename:
            filename = secure_filename(
                f"{user['id']}_{datetime.utcnow().timestamp()}_{file.filename}"
            )
            file.save(os.path.join(UPLOAD_FOLDER, filename))

        created_at = datetime.utcnow().isoformat()

        conn.execute("""
            INSERT INTO orders (customer_id,shop_id,service_id,doc_filename,
                                paper_size,sides,color,copies,additional,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (user["id"], shop_id, service_id, filename, paper_size, sides, color, copies, additional, created_at))

        conn.commit()
        conn.close()

        flash("Order placed.")
        return redirect(url_for("customer_dashboard"))

    return render_template("upload.html", user=user, shops=shops)

# ---------------- GET SERVICES ----------------
@app.route("/get_services/<int:shop_id>")
def get_services(shop_id):
    conn = get_db()
    services = conn.execute(
        "SELECT id, name, cost FROM services WHERE shop_id=?", 
        (shop_id,)
    ).fetchall()
    conn.close()
    return {
        "services": [
            {"id": s["id"], "name": s["name"], "cost": s["cost"]} 
            for s in services
        ]
    }

# ---------------- STATIC FILES ----------------
@app.route("/static/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/static/qr/<path:filename>")
def qr_file(filename):
    return send_from_directory(QR_FOLDER, filename)

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
