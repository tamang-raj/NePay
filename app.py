"""
NepaPay - Hybrid Digital Payment System for Nepal
Flask Backend: app.py
Handles all routes, authentication, wallet operations, and offline sync.
Data stored in plain .txt files as structured records.
"""

from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import hashlib
import os
import uuid
from datetime import datetime
import time
import random

app = Flask(__name__)
app.secret_key = "nepapay_secret_key_2024"  # In production, use env variable

# ─── File Paths ───────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

USERS_FILE         = os.path.join(DATA_DIR, "users.txt")
BALANCES_FILE      = os.path.join(DATA_DIR, "balances.txt")
TRANSACTIONS_FILE  = os.path.join(DATA_DIR, "transactions.txt")
OFFLINE_TX_FILE    = os.path.join(DATA_DIR, "offline_transactions.txt")

# ─── Constants ────────────────────────────────────────────────────────────────
MAX_OFFLINE_BALANCE = 5000.0   # Max NPR allowed in offline wallet
MIN_TRANSFER_AMOUNT = 1.0
MAX_TRANSFER_AMOUNT = 100000.0

# ─── Helpers: File I/O ────────────────────────────────────────────────────────

def ensure_files():
    """Create data files if they don't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)
    for f in [USERS_FILE, BALANCES_FILE, TRANSACTIONS_FILE, OFFLINE_TX_FILE]:
        if not os.path.exists(f):
            open(f, 'w').close()


def read_lines(filepath):
    """Read all non-empty lines from a file."""
    try:
        with open(filepath, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []


def append_line(filepath, line):
    """Append a line to a file."""
    with open(filepath, 'a') as f:
        f.write(line + "\n")


def write_lines(filepath, lines):
    """Overwrite file with given lines."""
    with open(filepath, 'w') as f:
        for line in lines:
            f.write(line + "\n")

# ─── Helpers: User Operations ─────────────────────────────────────────────────

def hash_password(password):
    """SHA-256 password hashing."""
    return hashlib.sha256(password.encode()).hexdigest()


def user_exists(username):
    """Check if username already registered."""
    for line in read_lines(USERS_FILE):
        parts = line.split("|")
        if parts[0] == username:
            return True
    return False


def get_user(username):
    """Return user dict or None. Format: username|password_hash|email|phone|created_at"""
    for line in read_lines(USERS_FILE):
        parts = line.split("|")
        if len(parts) >= 5 and parts[0] == username:
            return {
                "username": parts[0],
                "password_hash": parts[1],
                "email": parts[2],
                "phone": parts[3],
                "created_at": parts[4]
            }
    return None


def create_user(username, password, email, phone):
    """Register a new user and initialise balances."""
    if user_exists(username):
        return False, "Username already exists"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{username}|{hash_password(password)}|{email}|{phone}|{timestamp}"
    append_line(USERS_FILE, line)
    # Initialise balances: online_balance|offline_balance
    append_line(BALANCES_FILE, f"{username}|0.0|0.0")
    return True, "User created successfully"

# ─── Helpers: Balance Operations ──────────────────────────────────────────────

def get_balance(username):
    """Return (online_balance, offline_balance) tuple."""
    for line in read_lines(BALANCES_FILE):
        parts = line.split("|")
        if parts[0] == username:
            return float(parts[1]), float(parts[2])
    return 0.0, 0.0


def update_balance(username, online_delta=0.0, offline_delta=0.0):
    """
    Atomically update a user's balances.
    Returns (success, message).
    """
    lines = read_lines(BALANCES_FILE)
    updated = False
    new_lines = []
    for line in lines:
        parts = line.split("|")
        if parts[0] == username:
            new_online  = round(float(parts[1]) + online_delta, 2)
            new_offline = round(float(parts[2]) + offline_delta, 2)
            # Safety checks
            if new_online < 0:
                return False, "Insufficient online balance"
            if new_offline < 0:
                return False, "Insufficient offline balance"
            if new_offline > MAX_OFFLINE_BALANCE:
                return False, f"Offline wallet limit is NPR {MAX_OFFLINE_BALANCE}"
            new_lines.append(f"{username}|{new_online}|{new_offline}")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        return False, "User balance record not found"
    write_lines(BALANCES_FILE, new_lines)
    return True, "Balance updated"

# ─── Helpers: Transaction Logging ─────────────────────────────────────────────

def generate_tx_id():
    """Generate a unique transaction ID."""
    return "TXN" + uuid.uuid4().hex[:10].upper()


def log_transaction(tx_id, sender, receiver, amount, tx_type, status, note=""):
    """
    Append a transaction record.
    Format: tx_id|timestamp|sender|receiver|amount|type|status|note
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{tx_id}|{timestamp}|{sender}|{receiver}|{amount}|{tx_type}|{status}|{note}"
    append_line(TRANSACTIONS_FILE, line)


def log_offline_transaction(tx_id, sender, receiver, amount, note=""):
    """
    Store an offline transaction (pending sync).
    Format: tx_id|timestamp|sender|receiver|amount|offline|pending|note
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{tx_id}|{timestamp}|{sender}|{receiver}|{amount}|offline|pending|{note}"
    append_line(OFFLINE_TX_FILE, line)


def get_user_transactions(username, limit=20):
    """Return last N transactions for a user (newest first)."""
    txs = []
    for line in read_lines(TRANSACTIONS_FILE):
        parts = line.split("|")
        if len(parts) >= 7 and (parts[2] == username or parts[3] == username):
            txs.append({
                "tx_id":     parts[0],
                "timestamp": parts[1],
                "sender":    parts[2],
                "receiver":  parts[3],
                "amount":    float(parts[4]),
                "type":      parts[5],
                "status":    parts[6],
                "note":      parts[7] if len(parts) > 7 else ""
            })
    return list(reversed(txs))[:limit]


def get_pending_offline_transactions(username):
    """Return pending offline transactions for a user."""
    txs = []
    for line in read_lines(OFFLINE_TX_FILE):
        parts = line.split("|")
        if len(parts) >= 7 and parts[2] == username and parts[6] == "pending":
            txs.append({
                "tx_id":     parts[0],
                "timestamp": parts[1],
                "sender":    parts[2],
                "receiver":  parts[3],
                "amount":    float(parts[4]),
                "note":      parts[7] if len(parts) > 7 else ""
            })
    return txs


def sync_offline_transactions(username):
    """
    Mark pending offline transactions as synced and move to main log.
    Returns count of synced transactions.
    """
    lines = read_lines(OFFLINE_TX_FILE)
    new_lines = []
    synced = 0
    for line in lines:
        parts = line.split("|")
        if len(parts) >= 7 and parts[2] == username and parts[6] == "pending":
            # Move to main transaction log as synced
            tx_id    = parts[0]
            receiver = parts[3]
            amount   = parts[4]
            note     = parts[7] if len(parts) > 7 else ""
            log_transaction(tx_id, username, receiver, amount, "offline", "synced", note)
            # Mark as synced in offline file
            parts[6] = "synced"
            new_lines.append("|".join(parts))
            synced += 1
        else:
            new_lines.append(line)
    write_lines(OFFLINE_TX_FILE, new_lines)
    return synced


def simulate_server_load():
    """
    Simulate peak-hour server load (demo feature).
    Returns True if server is "available".
    """
    hour = datetime.now().hour
    # Evening peak hours: 6PM - 10PM (18-22)
    if 18 <= hour <= 22:
        # 40% chance of failure during peak hours
        return random.random() > 0.4
    return True  # Always available off-peak

# ─── Auth Decorator ───────────────────────────────────────────────────────────

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "username" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")
        email    = request.form.get("email", "").strip()
        phone    = request.form.get("phone", "").strip()

        # Validation
        if not all([username, password, confirm, email, phone]):
            error = "All fields are required"
        elif len(username) < 3:
            error = "Username must be at least 3 characters"
        elif len(password) < 6:
            error = "Password must be at least 6 characters"
        elif password != confirm:
            error = "Passwords do not match"
        elif user_exists(username):
            error = "Username already taken"
        else:
            ok, msg = create_user(username, password, email, phone)
            if ok:
                session["username"] = username
                return redirect(url_for("dashboard"))
            else:
                error = msg
    return render_template("register.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = get_user(username)
        if user and user["password_hash"] == hash_password(password):
            session["username"] = username
            return redirect(url_for("dashboard"))
        else:
            error = "Invalid username or password"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    username = session["username"]
    online_bal, offline_bal = get_balance(username)
    recent_txs = get_user_transactions(username, limit=5)
    pending_count = len(get_pending_offline_transactions(username))
    server_ok = simulate_server_load()
    return render_template("dashboard.html",
        username=username,
        online_balance=online_bal,
        offline_balance=offline_bal,
        recent_txs=recent_txs,
        pending_count=pending_count,
        server_available=server_ok
    )


@app.route("/wallet")
@login_required
def wallet():
    username = session["username"]
    online_bal, offline_bal = get_balance(username)
    server_ok = simulate_server_load()
    return render_template("wallet.html",
        username=username,
        online_balance=online_bal,
        offline_balance=offline_bal,
        max_offline=MAX_OFFLINE_BALANCE,
        server_available=server_ok
    )


@app.route("/transfer")
@login_required
def transfer():
    username = session["username"]
    online_bal, offline_bal = get_balance(username)
    server_ok = simulate_server_load()
    return render_template("transfer.html",
        username=username,
        online_balance=online_bal,
        offline_balance=offline_bal,
        server_available=server_ok
    )


@app.route("/history")
@login_required
def history():
    username = session["username"]
    txs = get_user_transactions(username, limit=50)
    offline_txs = get_pending_offline_transactions(username)
    return render_template("history.html",
        username=username,
        transactions=txs,
        offline_transactions=offline_txs
    )


# ─── API Endpoints ─────────────────────────────────────────────────────────────

@app.route("/api/deposit", methods=["POST"])
@login_required
def api_deposit():
    """Deposit money into online wallet."""
    username = session["username"]
    if not simulate_server_load():
        return jsonify({"success": False, "message": "Server overloaded. Try offline wallet."})
    try:
        amount = float(request.form.get("amount", 0))
    except ValueError:
        return jsonify({"success": False, "message": "Invalid amount"})
    if amount < MIN_TRANSFER_AMOUNT:
        return jsonify({"success": False, "message": f"Minimum deposit is NPR {MIN_TRANSFER_AMOUNT}"})
    if amount > MAX_TRANSFER_AMOUNT:
        return jsonify({"success": False, "message": f"Maximum deposit is NPR {MAX_TRANSFER_AMOUNT}"})

    ok, msg = update_balance(username, online_delta=amount)
    if ok:
        tx_id = generate_tx_id()
        log_transaction(tx_id, "SYSTEM", username, amount, "deposit", "completed", "Bank deposit")
        online_bal, offline_bal = get_balance(username)
        return jsonify({"success": True, "message": f"Deposited NPR {amount:.2f}", "tx_id": tx_id,
                        "online_balance": online_bal, "offline_balance": offline_bal})
    return jsonify({"success": False, "message": msg})


@app.route("/api/load_offline", methods=["POST"])
@login_required
def api_load_offline():
    """Move funds from online wallet to offline wallet."""
    username = session["username"]
    if not simulate_server_load():
        return jsonify({"success": False, "message": "Server unavailable. Cannot load offline wallet right now."})
    try:
        amount = float(request.form.get("amount", 0))
    except ValueError:
        return jsonify({"success": False, "message": "Invalid amount"})
    if amount < MIN_TRANSFER_AMOUNT:
        return jsonify({"success": False, "message": f"Minimum is NPR {MIN_TRANSFER_AMOUNT}"})
    _, current_offline = get_balance(username)
    if current_offline + amount > MAX_OFFLINE_BALANCE:
        return jsonify({"success": False, "message": f"Offline wallet limit is NPR {MAX_OFFLINE_BALANCE}. Current: NPR {current_offline}"})

    ok, msg = update_balance(username, online_delta=-amount, offline_delta=amount)
    if ok:
        tx_id = generate_tx_id()
        log_transaction(tx_id, username, username, amount, "online_to_offline", "completed", "Loaded offline wallet")
        online_bal, offline_bal = get_balance(username)
        return jsonify({"success": True, "message": f"Loaded NPR {amount:.2f} to offline wallet", "tx_id": tx_id,
                        "online_balance": online_bal, "offline_balance": offline_bal})
    return jsonify({"success": False, "message": msg})


@app.route("/api/online_transfer", methods=["POST"])
@login_required
def api_online_transfer():
    """Transfer online balance to another user."""
    username = session["username"]
    if not simulate_server_load():
        return jsonify({"success": False, "message": "Server overloaded! Use offline transfer instead.", "use_offline": True})
    try:
        amount = float(request.form.get("amount", 0))
    except ValueError:
        return jsonify({"success": False, "message": "Invalid amount"})
    receiver = request.form.get("receiver", "").strip().lower()
    note = request.form.get("note", "")

    if receiver == username:
        return jsonify({"success": False, "message": "Cannot transfer to yourself"})
    if not user_exists(receiver):
        return jsonify({"success": False, "message": "Recipient not found"})
    if amount < MIN_TRANSFER_AMOUNT:
        return jsonify({"success": False, "message": f"Minimum transfer is NPR {MIN_TRANSFER_AMOUNT}"})

    online_bal, _ = get_balance(username)
    if amount > online_bal:
        return jsonify({"success": False, "message": "Insufficient online balance"})

    # Deduct from sender
    ok, msg = update_balance(username, online_delta=-amount)
    if not ok:
        return jsonify({"success": False, "message": msg})
    # Credit to receiver
    ok2, msg2 = update_balance(receiver, online_delta=amount)
    if not ok2:
        # Rollback sender
        update_balance(username, online_delta=amount)
        return jsonify({"success": False, "message": msg2})

    tx_id = generate_tx_id()
    log_transaction(tx_id, username, receiver, amount, "online", "completed", note)
    online_bal, offline_bal = get_balance(username)
    return jsonify({"success": True, "message": f"Sent NPR {amount:.2f} to {receiver}", "tx_id": tx_id,
                    "online_balance": online_bal, "offline_balance": offline_bal})


@app.route("/api/offline_transfer", methods=["POST"])
@login_required
def api_offline_transfer():
    """Transfer offline balance (works without server)."""
    username = session["username"]
    try:
        amount = float(request.form.get("amount", 0))
    except ValueError:
        return jsonify({"success": False, "message": "Invalid amount"})
    receiver = request.form.get("receiver", "").strip().lower()
    note = request.form.get("note", "Offline payment")

    if receiver == username:
        return jsonify({"success": False, "message": "Cannot transfer to yourself"})
    if amount < MIN_TRANSFER_AMOUNT:
        return jsonify({"success": False, "message": f"Minimum is NPR {MIN_TRANSFER_AMOUNT}"})

    _, offline_bal = get_balance(username)
    if amount > offline_bal:
        return jsonify({"success": False, "message": f"Insufficient offline balance (NPR {offline_bal:.2f})"})

    # Deduct immediately from offline wallet (anti-double-spend)
    ok, msg = update_balance(username, offline_delta=-amount)
    if not ok:
        return jsonify({"success": False, "message": msg})

    tx_id = generate_tx_id()
    log_offline_transaction(tx_id, username, receiver, amount, note)

    online_bal, offline_bal = get_balance(username)
    return jsonify({"success": True,
                    "message": f"Offline transfer of NPR {amount:.2f} to {receiver} queued",
                    "tx_id": tx_id,
                    "online_balance": online_bal,
                    "offline_balance": offline_bal,
                    "pending": True})


@app.route("/api/sync", methods=["POST"])
@login_required
def api_sync():
    """Sync pending offline transactions to the server."""
    username = session["username"]
    if not simulate_server_load():
        return jsonify({"success": False, "message": "Server still unavailable. Try again later."})
    count = sync_offline_transactions(username)
    return jsonify({"success": True, "message": f"Synced {count} offline transaction(s)", "synced_count": count})


@app.route("/api/balance")
@login_required
def api_balance():
    """Get current balances."""
    username = session["username"]
    online_bal, offline_bal = get_balance(username)
    return jsonify({
        "online_balance": online_bal,
        "offline_balance": offline_bal,
        "server_available": simulate_server_load()
    })


@app.route("/api/server_status")
def api_server_status():
    """Check simulated server status."""
    available = simulate_server_load()
    hour = datetime.now().hour
    return jsonify({
        "available": available,
        "peak_hours": 18 <= hour <= 22,
        "message": "Server available" if available else "High traffic — server temporarily overloaded"
    })


# ─── Admin Dashboard ──────────────────────────────────────────────────────────

@app.route("/admin")
@login_required
def admin():
    """Simple admin view (any logged-in user can view for demo)."""
    # Load all users
    users = []
    for line in read_lines(USERS_FILE):
        parts = line.split("|")
        if len(parts) >= 5:
            online, offline = get_balance(parts[0])
            users.append({
                "username": parts[0],
                "email": parts[2],
                "phone": parts[3],
                "created_at": parts[4],
                "online_balance": online,
                "offline_balance": offline
            })
    # Count pending offline tx
    all_pending = []
    for line in read_lines(OFFLINE_TX_FILE):
        parts = line.split("|")
        if len(parts) >= 7 and parts[6] == "pending":
            all_pending.append({
                "tx_id": parts[0], "timestamp": parts[1],
                "sender": parts[2], "receiver": parts[3], "amount": float(parts[4])
            })
    total_tx_count = len(read_lines(TRANSACTIONS_FILE))
    return render_template("admin.html",
        username=session["username"],
        users=users,
        pending_offline=all_pending,
        total_tx_count=total_tx_count,
        server_available=simulate_server_load()
    )


# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ensure_files()
    print("=" * 60)
    print("  NepaPay - Hybrid Digital Payment System")
    print("  Running at http://127.0.0.1:5000")
    print("=" * 60)
    app.run(debug=True, port=5000)
