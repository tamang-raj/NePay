from flask import Flask, render_template, request, redirect, session, url_for
import hashlib
import os
from datetime import datetime
import uuid

app = Flask(__name__)
app.secret_key = "super_secret_key"

# FILES
USERS_FILE = "users.txt"
BALANCES_FILE = "balances.txt"
TRANSACTIONS_FILE = "transactions.txt"
OFFLINE_FILE = "offline_transactions.txt"

OFFLINE_LIMIT = 5000  # Max offline wallet amount


# -----------------------
# Utility Functions
# -----------------------

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def generate_tx_id():
    return str(uuid.uuid4())[:8]


def user_exists(username):
    if not os.path.exists(USERS_FILE):
        return False
    with open(USERS_FILE, "r") as f:
        for line in f:
            if line.split("|")[0] == username:
                return True
    return False


def get_balance(username):
    with open(BALANCES_FILE, "r") as f:
        for line in f:
            data = line.strip().split("|")
            if data[0] == username:
                return float(data[1]), float(data[2])
    return 0, 0


def update_balance(username, online, offline):
    lines = []
    with open(BALANCES_FILE, "r") as f:
        lines = f.readlines()

    with open(BALANCES_FILE, "w") as f:
        for line in lines:
            data = line.strip().split("|")
            if data[0] == username:
                f.write(f"{username}|{online}|{offline}\n")
            else:
                f.write(line)


def log_transaction(tx_id, sender, receiver, amount, tx_type, status):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(TRANSACTIONS_FILE, "a") as f:
        f.write(f"{tx_id}|{timestamp}|{sender}|{receiver}|{amount}|{tx_type}|{status}\n")


def log_offline_transaction(tx_id, sender, receiver, amount):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(OFFLINE_FILE, "a") as f:
        f.write(f"{tx_id}|{timestamp}|{sender}|{receiver}|{amount}|pending\n")


# -----------------------
# Routes
# -----------------------

@app.route("/")
def home():
    if "username" in session:
        return redirect("/dashboard")
    return redirect("/login")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = hash_password(request.form["password"])

        if user_exists(username):
            return "User already exists"

        with open(USERS_FILE, "a") as f:
            f.write(f"{username}|{password}\n")

        with open(BALANCES_FILE, "a") as f:
            f.write(f"{username}|0|0\n")

        return redirect("/login")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = hash_password(request.form["password"])

        with open(USERS_FILE, "r") as f:
            for line in f:
                data = line.strip().split("|")
                if data[0] == username and data[1] == password:
                    session["username"] = username
                    return redirect("/dashboard")

        return "Invalid credentials"

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect("/login")

    online, offline = get_balance(session["username"])
    return render_template("dashboard.html", online=online, offline=offline)


# -----------------------
# Deposit & Withdraw
# -----------------------

@app.route("/deposit", methods=["POST"])
def deposit():
    if "username" not in session:
        return redirect("/login")

    amount = float(request.form["amount"])
    username = session["username"]

    online, offline = get_balance(username)
    online += amount
    update_balance(username, online, offline)

    tx_id = generate_tx_id()
    log_transaction(tx_id, "BANK", username, amount, "deposit", "completed")

    return redirect("/dashboard")


@app.route("/withdraw", methods=["POST"])
def withdraw():
    if "username" not in session:
        return redirect("/login")

    amount = float(request.form["amount"])
    username = session["username"]

    online, offline = get_balance(username)

    if online < amount:
        return "Insufficient Balance"

    online -= amount
    update_balance(username, online, offline)

    tx_id = generate_tx_id()
    log_transaction(tx_id, username, "BANK", amount, "withdraw", "completed")

    return redirect("/dashboard")


# -----------------------
# Online Transfer
# -----------------------

@app.route("/transfer", methods=["GET", "POST"])
def transfer():
    if "username" not in session:
        return redirect("/login")

    if request.method == "POST":
        sender = session["username"]
        receiver = request.form["receiver"]
        amount = float(request.form["amount"])

        if not user_exists(receiver):
            return "Receiver not found"

        s_online, s_offline = get_balance(sender)
        r_online, r_offline = get_balance(receiver)

        if s_online < amount:
            return "Insufficient Online Balance"

        s_online -= amount
        r_online += amount

        update_balance(sender, s_online, s_offline)
        update_balance(receiver, r_online, r_offline)

        tx_id = generate_tx_id()
        log_transaction(tx_id, sender, receiver, amount, "online", "completed")

        return redirect("/dashboard")

    return render_template("transfer.html")


# -----------------------
# Move Online → Offline
# -----------------------

@app.route("/move_offline", methods=["POST"])
def move_offline():
    if "username" not in session:
        return redirect("/login")

    amount = float(request.form["amount"])
    username = session["username"]

    online, offline = get_balance(username)

    if online < amount:
        return "Not enough online balance"

    if offline + amount > OFFLINE_LIMIT:
        return "Offline limit exceeded"

    online -= amount
    offline += amount

    update_balance(username, online, offline)

    tx_id = generate_tx_id()
    log_transaction(tx_id, username, username, amount, "online_to_offline", "completed")

    return redirect("/dashboard")


# -----------------------
# Offline Transfer
# -----------------------

@app.route("/offline_transfer", methods=["POST"])
def offline_transfer():
    if "username" not in session:
        return redirect("/login")

    sender = session["username"]
    receiver = request.form["receiver"]
    amount = float(request.form["amount"])

    s_online, s_offline = get_balance(sender)

    if s_offline < amount:
        return "Insufficient Offline Balance"

    s_offline -= amount
    update_balance(sender, s_online, s_offline)

    tx_id = generate_tx_id()
    log_offline_transaction(tx_id, sender, receiver, amount)

    return redirect("/dashboard")


# -----------------------
# Sync Offline
# -----------------------

@app.route("/sync")
def sync():
    if "username" not in session:
        return redirect("/login")

    if not os.path.exists(OFFLINE_FILE):
        return redirect("/dashboard")

    lines = []
    with open(OFFLINE_FILE, "r") as f:
        lines = f.readlines()

    remaining = []

    for line in lines:
        data = line.strip().split("|")
        tx_id, timestamp, sender, receiver, amount, status = data
        amount = float(amount)

        if status == "pending":
            if user_exists(receiver):
                r_online, r_offline = get_balance(receiver)
                r_online += amount
                update_balance(receiver, r_online, r_offline)

                log_transaction(tx_id, sender, receiver, amount, "offline", "synced")
            else:
                remaining.append(line)

    with open(OFFLINE_FILE, "w") as f:
        for line in remaining:
            f.write(line)

    return redirect("/dashboard")


# -----------------------
# Transaction History
# -----------------------

@app.route("/history")
def history():
    if "username" not in session:
        return redirect("/login")

    username = session["username"]
    records = []

    if os.path.exists(TRANSACTIONS_FILE):
        with open(TRANSACTIONS_FILE, "r") as f:
            for line in f:
                data = line.strip().split("|")
                if username in data:
                    records.append(data)

    return render_template("history.html", records=records)


# -----------------------
# Run App
# -----------------------

if __name__ == "__main__":
    app.run(debug=True)