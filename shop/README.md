# My Shop – Flask + MySQL E-commerce

## Setup
1. Install and start MySQL. The database and tables are created automatically when you run the app (`schema.sql` is only a reference copy).
2. `python -m venv venv && source venv/bin/activate` (Windows: `venv\Scripts\activate`)
3. `pip install -r requirements.txt`
4. Set DB login if needed (defaults: root, empty password, db shop_db):
   `export DB_USER=root DB_PASS=yourpass SECRET_KEY=something-long`
5. `python app.py`  → open http://127.0.0.1:5000

Default admin: **admin@shop.com / admin123** (change via ADMIN_EMAIL / ADMIN_PASS env vars before first run).

## Flow
1. Admin uploads products (Admin → Products).
2. Customer registers, adds to cart, places order (status: pending).
3. Admin opens the order, approves it and types the payment details (Paybill/Till/instructions).
4. Customer sees the payment details, pays, and submits the M-Pesa code.
5. Admin checks the code against the M-Pesa message and confirms (paid) or rejects the payment.
Rejected orders return the stock automatically.
