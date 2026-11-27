import os, uuid, pymysql
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret")
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
DB = dict(host=os.environ.get("DB_HOST", "localhost"), user=os.environ.get("DB_USER", "root"),
          password=os.environ.get("DB_PASS", ""), database=os.environ.get("DB_NAME", "shop_db"),
          cursorclass=pymysql.cursors.DictCursor, autocommit=True)
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@shop.com")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")
LOW = int(os.environ.get("LOW_STOCK", 5))  # stock at or below this = low
ALLOWED = {"png", "jpg", "jpeg", "gif", "webp"}

def q(sql, args=(), one=False):
    c = pymysql.connect(**DB)
    try:
        with c.cursor() as cur:
            cur.execute(sql, args)
            if sql.lstrip().upper().startswith("SELECT"):
                return cur.fetchone() if one else cur.fetchall()
            return cur.lastrowid
    finally:
        c.close()

def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if "uid" not in session:
            flash("Please log in first.", "error"); return redirect(url_for("login"))
        return f(*a, **k)
    return w

def admin_required(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get("admin"):
            flash("Admin access only.", "error"); return redirect(url_for("login"))
        return f(*a, **k)
    return w

def cart_items():
    items, total = [], 0
    for pid, qty in session.get("cart", {}).items():
        p = q("SELECT * FROM products WHERE id=%s", (pid,), one=True)
        if p:
            sub = p["price"] * qty; total += sub
            items.append(dict(p=p, qty=qty, sub=sub))
    return items, total

@app.context_processor
def inject():
    return dict(cart_count=sum(session.get("cart", {}).values()), LOW=LOW)

def save_image(f):
    if f and f.filename and f.filename.rsplit(".", 1)[-1].lower() in ALLOWED:
        name = uuid.uuid4().hex + "_" + secure_filename(f.filename)
        f.save(os.path.join(app.config["UPLOAD_FOLDER"], name)); return name
    return None

# ---------- shop ----------
@app.route("/")
def index():
    featured = q("SELECT * FROM products WHERE stock>0 ORDER BY id DESC LIMIT 8")
    return render_template("index.html", featured=featured)

@app.route("/shop")
def shop():
    s = request.args.get("q", "").strip()
    if s:
        prods = q("SELECT * FROM products WHERE name LIKE %s ORDER BY id DESC", ("%" + s + "%",))
    else:
        prods = q("SELECT * FROM products ORDER BY id DESC")
    return render_template("shop.html", products=prods, s=s)

@app.route("/product/<int:pid>")
def product(pid):
    p = q("SELECT * FROM products WHERE id=%s", (pid,), one=True)
    if not p: return redirect(url_for("index"))
    return render_template("product.html", p=p)

@app.route("/cart")
def cart():
    items, total = cart_items()
    return render_template("cart.html", items=items, total=total)

@app.route("/cart/add/<int:pid>", methods=["POST"])
def cart_add(pid):
    p = q("SELECT * FROM products WHERE id=%s", (pid,), one=True)
    if not p: return redirect(url_for("index"))
    c = session.get("cart", {})
    qty = max(1, int(request.form.get("qty", 1)))
    c[str(pid)] = min(c.get(str(pid), 0) + qty, p["stock"])
    session["cart"] = c
    flash("Added to cart.", "ok")
    return redirect(request.referrer or url_for("index"))

@app.route("/cart/update/<int:pid>", methods=["POST"])
def cart_update(pid):
    c = session.get("cart", {}); qty = int(request.form.get("qty", 1))
    if qty <= 0: c.pop(str(pid), None)
    else: c[str(pid)] = qty
    session["cart"] = c
    return redirect(url_for("cart"))

@app.route("/checkout", methods=["POST"])
@login_required
def checkout():
    items, total = cart_items()
    if not items:
        flash("Cart is empty.", "error"); return redirect(url_for("cart"))
    for i in items:
        if i["qty"] > i["p"]["stock"]:
            flash(f"Not enough stock for {i['p']['name']}.", "error"); return redirect(url_for("cart"))
    oid = q("INSERT INTO orders(user_id,total,phone,address) VALUES(%s,%s,%s,%s)",
            (session["uid"], total, request.form["phone"], request.form["address"]))
    for i in items:
        q("INSERT INTO order_items(order_id,product_id,name,price,qty) VALUES(%s,%s,%s,%s,%s)",
          (oid, i["p"]["id"], i["p"]["name"], i["p"]["price"], i["qty"]))
        q("UPDATE products SET stock=stock-%s WHERE id=%s", (i["qty"], i["p"]["id"]))
    session["cart"] = {}
    flash("Order placed. Wait for admin approval.", "ok")
    return redirect(url_for("order_detail", oid=oid))

@app.route("/orders")
@login_required
def my_orders():
    o = q("SELECT * FROM orders WHERE user_id=%s ORDER BY id DESC", (session["uid"],))
    return render_template("orders.html", orders=o)

@app.route("/orders/<int:oid>")
@login_required
def order_detail(oid):
    o = q("SELECT * FROM orders WHERE id=%s AND user_id=%s", (oid, session["uid"]), one=True)
    if not o: return redirect(url_for("my_orders"))
    items = q("SELECT * FROM order_items WHERE order_id=%s", (oid,))
    return render_template("order_detail.html", o=o, items=items)

@app.route("/orders/<int:oid>/pay", methods=["POST"])
@login_required
def submit_payment(oid):
    o = q("SELECT * FROM orders WHERE id=%s AND user_id=%s", (oid, session["uid"]), one=True)
    code = request.form["code"].strip().upper()
    if not o or o["status"] not in ("approved", "payment_rejected"):
        flash("Payment cannot be submitted for this order.", "error")
    elif len(code) < 8:
        flash("Enter a valid transaction code.", "error")
    elif q("SELECT id FROM orders WHERE mpesa_code=%s", (code,), one=True):
        flash("This code has already been submitted. Each transaction code can only be used once.", "error")
    else:
        try:
            q("UPDATE orders SET mpesa_code=%s,status='payment_submitted' WHERE id=%s", (code, oid))
            flash("Code sent. Admin will confirm shortly.", "ok")
        except pymysql.err.IntegrityError:  # two submissions at the same moment
            flash("This code has already been submitted. Each transaction code can only be used once.", "error")
    return redirect(url_for("order_detail", oid=oid))

# ---------- auth ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        if q("SELECT id FROM users WHERE email=%s", (f["email"],), one=True):
            flash("Email already registered.", "error")
        else:
            q("INSERT INTO users(name,email,phone,password) VALUES(%s,%s,%s,%s)",
              (f["name"], f["email"], f["phone"], generate_password_hash(f["password"])))
            flash("Account created. Please log in.", "ok"); return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = q("SELECT * FROM users WHERE email=%s", (request.form["email"],), one=True)
        if u and check_password_hash(u["password"], request.form["password"]):
            session.update(uid=u["id"], name=u["name"], admin=bool(u["is_admin"]))
            return redirect(url_for("admin_home") if u["is_admin"] else url_for("index"))
        flash("Wrong email or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("index"))

# ---------- admin ----------

def business_advice():
    """Rule-based advice for the shop owner: stock, orders and payments."""
    sold = {r["product_id"]: int(r["s"]) for r in q(
        "SELECT oi.product_id, SUM(oi.qty) s FROM order_items oi JOIN orders o ON o.id=oi.order_id "
        "WHERE o.status IN ('approved','payment_submitted','paid') AND o.created_at >= NOW() - INTERVAL 30 DAY "
        "GROUP BY oi.product_id")}
    adv, low = [], []
    for p in q("SELECT * FROM products ORDER BY stock"):
        s30 = sold.get(p["id"], 0); per_day = s30 / 30
        days = round(p["stock"] / per_day) if per_day else None
        if p["stock"] == 0 or p["stock"] <= LOW or (days is not None and days <= 7):
            need = max(s30 - p["stock"], LOW * 2)
            low.append(dict(p=p, sold=s30, days=days, restock=need, out=p["stock"] == 0))
    outs = [x for x in low if x["out"]]
    if outs:
        adv.append(("danger", "Out of stock: " + ", ".join(x["p"]["name"] for x in outs),
                    "Customers cannot buy these. Restock immediately or hide/remove them if discontinued."))
    lows = [x for x in low if not x["out"]]
    if lows:
        adv.append(("warn", f"{len(lows)} product(s) running low",
                    "Reorder soon, starting with the fastest sellers. See the restock table below for suggested quantities."))
    n = q("SELECT COUNT(*) n FROM orders WHERE status='pending'", one=True)["n"]
    if n:
        adv.append(("warn", f"{n} order(s) waiting for your approval",
                    "Open each one, approve it and enter your Paybill/Till details, or reject it. Slow replies lose customers."))
    n = q("SELECT COUNT(*) n FROM orders WHERE status='payment_submitted'", one=True)["n"]
    if n:
        adv.append(("danger", f"{n} payment code(s) to confirm",
                    "Check each code against your M-Pesa messages for the exact amount, then confirm or reject."))
    n = q("SELECT COUNT(*) n FROM orders WHERE status='approved' AND created_at < NOW() - INTERVAL 1 DAY", one=True)["n"]
    if n:
        adv.append(("info", f"{n} approved order(s) unpaid for over 24 hours",
                    "Call or message these customers to remind them to pay. If they don't, reject the order so the stock returns."))
    top = sorted(sold.items(), key=lambda x: -x[1])[:1]
    if top:
        p = q("SELECT name FROM products WHERE id=%s", (top[0][0],), one=True)
        if p:
            adv.append(("good", f"Best seller (30 days): {p['name']} - {top[0][1]} sold",
                        "Keep it well stocked, feature it on the home page and consider bundling it with slower items."))
    slow = [p["name"] for p in q("SELECT * FROM products WHERE stock >= %s AND created_at < NOW() - INTERVAL 30 DAY", (LOW * 3,))
            if sold.get(p["id"], 0) == 0]
    if slow:
        adv.append(("info", "No sales in 30 days: " + ", ".join(slow[:5]),
                    "Money is tied up in these. Try a discount, better photos/description, or a bundle offer."))
    if not adv:
        adv.append(("good", "All good", "No urgent actions. Stock levels and orders are healthy."))
    return adv, low

@app.route("/admin")
@admin_required
def admin_home():
    st = {r["status"]: r["n"] for r in q("SELECT status, COUNT(*) n FROM orders GROUP BY status")}
    adv, low = business_advice()
    return render_template("admin/dashboard.html", advice=adv, low=low, st=st, recent=q("SELECT * FROM products ORDER BY id DESC LIMIT 4"),
        np=q("SELECT COUNT(*) n FROM products", one=True)["n"],
        nu=q("SELECT COUNT(*) n FROM users WHERE is_admin=0", one=True)["n"],
        rev=q("SELECT COALESCE(SUM(total),0) s FROM orders WHERE status='paid'", one=True)["s"])

@app.route("/admin/products")
@admin_required
def admin_products():
    return render_template("admin/products.html", products=q("SELECT * FROM products ORDER BY id DESC"))

@app.route("/admin/products/new", methods=["GET", "POST"])
@app.route("/admin/products/<int:pid>/edit", methods=["GET", "POST"])
@admin_required
def product_form(pid=None):
    p = q("SELECT * FROM products WHERE id=%s", (pid,), one=True) if pid else None
    if request.method == "POST":
        f = request.form; img = save_image(request.files.get("image"))
        if p:
            q("UPDATE products SET name=%s,description=%s,price=%s,stock=%s,image=%s WHERE id=%s",
              (f["name"], f["description"], f["price"], f["stock"], img or p["image"], pid))
        else:
            q("INSERT INTO products(name,description,price,stock,image) VALUES(%s,%s,%s,%s,%s)",
              (f["name"], f["description"], f["price"], f["stock"], img))
        flash("Product saved.", "ok"); return redirect(url_for("admin_products"))
    return render_template("admin/product_form.html", p=p)

@app.route("/admin/products/<int:pid>/delete", methods=["POST"])
@admin_required
def product_delete(pid):
    q("DELETE FROM products WHERE id=%s", (pid,))
    flash("Product deleted.", "ok"); return redirect(url_for("admin_products"))

@app.route("/admin/orders")
@admin_required
def admin_orders():
    st = request.args.get("status")
    sql = "SELECT o.*, u.name uname FROM orders o JOIN users u ON u.id=o.user_id"
    o = q(sql + " WHERE o.status=%s ORDER BY o.id DESC", (st,)) if st else q(sql + " ORDER BY o.id DESC")
    return render_template("admin/orders.html", orders=o, st=st)

@app.route("/admin/orders/<int:oid>")
@admin_required
def admin_order(oid):
    o = q("SELECT o.*, u.name uname, u.email FROM orders o JOIN users u ON u.id=o.user_id WHERE o.id=%s", (oid,), one=True)
    items = q("SELECT * FROM order_items WHERE order_id=%s", (oid,))
    return render_template("admin/order_detail.html", o=o, items=items)

@app.route("/admin/orders/<int:oid>/<action>", methods=["POST"])
@admin_required
def order_action(oid, action):
    f = request.form
    if action == "approve":  # approve + upload payment details
        q("UPDATE orders SET status='approved', pay_instructions=%s, admin_note=NULL WHERE id=%s", (f["instructions"], oid))
    elif action == "reject":
        q("UPDATE orders SET status='rejected', admin_note=%s WHERE id=%s", (f.get("note", ""), oid))
        for i in q("SELECT * FROM order_items WHERE order_id=%s", (oid,)):
            q("UPDATE products SET stock=stock+%s WHERE id=%s", (i["qty"], i["product_id"]))
    elif action == "confirm":
        q("UPDATE orders SET status='paid' WHERE id=%s", (oid,))
    elif action == "badpay":
        q("UPDATE orders SET status='payment_rejected', admin_note=%s WHERE id=%s", (f.get("note", "Payment not found"), oid))
    flash("Order updated.", "ok")
    return redirect(url_for("admin_order", oid=oid))

TABLES = [
"""CREATE TABLE IF NOT EXISTS users(
  id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100), email VARCHAR(120) UNIQUE,
  phone VARCHAR(20), password VARCHAR(255), is_admin TINYINT DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
"""CREATE TABLE IF NOT EXISTS products(
  id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(150), description TEXT,
  price DECIMAL(10,2), stock INT DEFAULT 0, image VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
"""CREATE TABLE IF NOT EXISTS orders(
  id INT AUTO_INCREMENT PRIMARY KEY, user_id INT, total DECIMAL(10,2),
  phone VARCHAR(20), address VARCHAR(255),
  status ENUM('pending','approved','rejected','payment_submitted','paid','payment_rejected') DEFAULT 'pending',
  pay_instructions TEXT, mpesa_code VARCHAR(30) UNIQUE, admin_note VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(id))""",
"""CREATE TABLE IF NOT EXISTS order_items(
  id INT AUTO_INCREMENT PRIMARY KEY, order_id INT, product_id INT,
  name VARCHAR(150), price DECIMAL(10,2), qty INT,
  FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE)"""]

def setup():
    """Create the database, all tables and the default admin automatically."""
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    try:
        cfg = {k: v for k, v in DB.items() if k != "database"}
        c = pymysql.connect(**cfg)
        with c.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB['database']}` CHARACTER SET utf8mb4")
        c.close()
        for t in TABLES:
            q(t)
        try:  # older databases: make sure M-Pesa codes are unique
            q("ALTER TABLE orders ADD UNIQUE KEY uq_mpesa_code (mpesa_code)")
        except Exception:
            pass
        if not q("SELECT id FROM users WHERE is_admin=1", one=True):
            q("INSERT INTO users(name,email,password,is_admin) VALUES('Admin',%s,%s,1)",
              (ADMIN_EMAIL, generate_password_hash(ADMIN_PASS)))
        print("Database ready:", DB["database"])
    except Exception as e:
        print("!! Could not set up the database. Check MySQL is running and DB_USER/DB_PASS are correct.\n  ", e)

setup()

if __name__ == "__main__":
    app.run(debug=True)
