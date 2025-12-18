from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
import sqlite3, os
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime

# ---------------- SAFE PATH (RENDER + LOCAL) ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "sira.db")

UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
QR_FOLDER = os.path.join(BASE_DIR, "static", "qr")

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

# ---------------- DEMO DATA ----------------
def create_demo_data():
    conn = get_db()

    # Demo shopkeeper
    shop = conn.execute(
        "SELECT id FROM users WHERE email='shopkeeper@sira.com'"
    ).fetchone()

    if not shop:
        conn.execute("""
            INSERT INTO users (name,email,password,role,shop_name)
            VALUES (?,?,?,?,?)
        """, (
            "Demo Shopkeeper",
            "shopkeeper@sira.com",
            generate_password_hash("demo123"),
            "shopkeeper",
            "SIRA Demo Print Shop"
        ))
        conn.commit()
        shop = conn.execute(
            "SELECT id FROM users WHERE email='shopkeeper@sira.com'"
        ).fetchone()

    shop_id = shop["id"]

    # Demo customer
    customer = conn.execute(
        "SELECT id FROM users WHERE email='customer@sira.com'"
    ).fetchone()

    if not customer:
        conn.execute("""
            INSERT INTO users (name,email,password,role)
            VALUES (?,?,?,?)
        """, (
            "Demo Customer",
            "customer@sira.com",
            generate_password_hash("demo123"),
            "customer"
        ))
        conn.commit()
        customer = conn.execute(
            "SELECT id FROM users WHERE email='customer@sira.com'"
        ).fetchone()

    customer_id = customer["id"]

    # Demo service
    service = conn.execute(
        "SELECT id FROM services WHERE shop_id=?",
        (shop_id,)
    ).fetchone()

    if not service:
        conn.execute("""
            INSERT INTO services (shop_id,name,cost)
            VALUES (?,?,?)
        """, (shop_id, "Black & White Printing", 2))
        conn.commit()
        service = conn.execute(
            "SELECT id FROM services WHERE shop_id=?",
            (shop_id,)
        ).fetchone()

    service_id = service["id"]

    # Demo order
    order = conn.execute("SELECT id FROM orders").fetchone()
    if not order:
        conn.execute("""
            INSERT INTO orders (
                customer_id, shop_id, service_id,
                paper_size, sides, color, copies,
                additional, created_at
            )
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            customer_id,
            shop_id,
            service_id,
            "A4",
            "Single Side",
            "Black & White",
            1,
            "Demo order for testing",
            datetime.utcnow().isoformat()
        ))
        conn.commit()

    conn.close()

init_db()
create_demo_data()

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

        if not email or not password or role not in ["customer", "shopkeeper", "admin"]:
            flash("Fill all fields properly.")
            return redirect(url_for("register"))

        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users (name,email,password,role,shop_name) VALUES (?,?,?,?,?)",
                (name, email, generate_password_hash(password), role, shop_name),
            )
            conn.commit()
        except:
            flash("Email already exists.")
        finally:
            conn.close()

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
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ---------------- CUSTOMER ----------------
@app.route("/customer/dashboard")
def customer_dashboard():
    user = current_user()
    if not user or user["role"] != "customer":
        return redirect(url_for("login"))

    conn = get_db()
    orders = conn.execute("""
    SELECT o.*, 
           s.name AS service_name, 
           sh.shop_name AS shop_name, 
           COALESCE(q.qr_filename, '') AS qr_filename
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

# ---------------- SHOPKEEPER ----------------
@app.route("/shop/dashboard")
def shop_dashboard():
    user = current_user()
    if not user or user["role"] != "shopkeeper":
        return redirect(url_for("login"))

    conn = get_db()
    orders = conn.execute("""
        SELECT o.*, c.name AS customer_name, s.name AS service_name
        FROM orders o
        LEFT JOIN users c ON o.customer_id = c.id
        LEFT JOIN services s ON o.service_id = s.id
        WHERE o.shop_id=?
    """, (user["id"],)).fetchall()
    conn.close()

    return render_template("dashboard_shopkeeper.html", user=user, orders=orders)

# ---------------- STATIC ----------------
@app.route("/static/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/static/qr/<path:filename>")
def qr_file(filename):
    return send_from_directory(QR_FOLDER, filename)

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
