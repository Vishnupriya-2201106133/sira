import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename

# ======================
# APP CONFIG
# ======================
app = Flask(__name__)
app.secret_key = "sira_secret_key"

# ======================
# DATABASE CONFIG
# ======================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = "/tmp/database.db" if os.environ.get("RENDER") else os.path.join(BASE_DIR, "database.db")

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ======================
# DATABASE CONNECTION
# ======================
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ======================
# INIT DATABASE + DEMO DATA
# ======================
def init_db():
    conn = get_db_connection()

    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        role TEXT
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id INTEGER,
        name TEXT,
        price INTEGER
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        shop_id INTEGER,
        service_id INTEGER,
        file_name TEXT,
        status TEXT
    )
    """)

    # Demo shopkeeper
    shop = conn.execute(
        "SELECT * FROM users WHERE email=?",
        ("demo@shop.com",)
    ).fetchone()

    if not shop:
        conn.execute(
            "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
            ("Demo Shopkeeper", "demo@shop.com", "demo123", "shopkeeper")
        )
        conn.commit()

    shop = conn.execute(
        "SELECT * FROM users WHERE email=?",
        ("demo@shop.com",)
    ).fetchone()

    # Demo service
    service = conn.execute(
        "SELECT * FROM services WHERE shop_id=?",
        (shop["id"],)
    ).fetchone()

    if not service:
        conn.execute(
            "INSERT INTO services (shop_id, name, price) VALUES (?, ?, ?)",
            (shop["id"], "Black & White Print", 2)
        )
        conn.commit()

    conn.close()

init_db()

# ======================
# HOME
# ======================
@app.route("/")
def index():
    return render_template("index.html")

# ======================
# REGISTER
# ======================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
                (
                    request.form["name"],
                    request.form["email"],
                    request.form["password"],
                    request.form["role"]
                )
            )
            conn.commit()
            flash("Account created! Please login.")
            return redirect(url_for("login"))
        except:
            flash("Email already exists")
        finally:
            conn.close()

    return render_template("register.html")

# ======================
# LOGIN
# ======================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE email=? AND password=?",
            (request.form["email"], request.form["password"])
        ).fetchone()
        conn.close()

        if user:
            session["user"] = dict(user)
            if user["role"] == "customer":
                return redirect(url_for("customer_dashboard"))
            else:
                return redirect(url_for("shopkeeper_dashboard"))
        else:
            flash("Invalid credentials")

    return render_template("login.html")

# ======================
# LOGOUT
# ======================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ======================
# CUSTOMER DASHBOARD
# ======================
@app.route("/customer/dashboard")
def customer_dashboard():
    if "user" not in session or session["user"]["role"] != "customer":
        return redirect(url_for("login"))

    conn = get_db_connection()

    shops = conn.execute(
        "SELECT * FROM users WHERE role='shopkeeper'"
    ).fetchall()

    orders = conn.execute("""
        SELECT orders.*, services.name AS service_name
        FROM orders
        JOIN services ON orders.service_id = services.id
        WHERE customer_id=?
    """, (session["user"]["id"],)).fetchall()

    conn.close()

    return render_template(
        "dashboard_customer.html",
        shops=shops,
        orders=orders
    )

# ======================
# NEW ORDER
# ======================
@app.route("/customer/new_order", methods=["POST"])
def customer_new_order():
    if "user" not in session or session["user"]["role"] != "customer":
        return redirect(url_for("login"))

    shop_id = request.form.get("shop_id")
    service_id = request.form.get("service_id")
    file = request.files.get("document")

    if not shop_id or not service_id or not file:
        flash("All fields required")
        return redirect(url_for("customer_dashboard"))

    filename = secure_filename(file.filename)
    file.save(os.path.join(UPLOAD_FOLDER, filename))

    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO orders (customer_id, shop_id, service_id, file_name, status)
        VALUES (?, ?, ?, ?, 'Pending')
        """,
        (session["user"]["id"], shop_id, service_id, filename)
    )
    conn.commit()
    conn.close()

    flash("Order placed successfully!")
    return redirect(url_for("customer_dashboard"))

# ======================
# SHOPKEEPER DASHBOARD
# ======================
@app.route("/shopkeeper/dashboard")
def shopkeeper_dashboard():
    if "user" not in session or session["user"]["role"] != "shopkeeper":
        return redirect(url_for("login"))

    conn = get_db_connection()

    services = conn.execute(
        "SELECT * FROM services WHERE shop_id=?",
        (session["user"]["id"],)
    ).fetchall()

    orders = conn.execute("""
        SELECT orders.*, users.name AS customer_name, services.name AS service_name
        FROM orders
        JOIN users ON orders.customer_id = users.id
        JOIN services ON orders.service_id = services.id
        WHERE orders.shop_id=?
    """, (session["user"]["id"],)).fetchall()

    conn.close()

    return render_template(
        "dashboard_shopkeeper.html",
        services=services,
        orders=orders
    )

# ======================
# RUN (LOCAL ONLY)
# ======================
if __name__ == "__main__":
    app.run(debug=True)
