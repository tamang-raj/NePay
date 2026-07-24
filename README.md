# NepaPay — Hybrid Digital Payment System 🇳🇵

A prototype of a hybrid online/offline digital wallet designed to solve Nepal's peak-hour payment failures.

---

## 📁 Project Structure

```
nepalpay/
├── app.py                    ← Flask backend (all routes + logic)
├── requirements.txt
├── data/
│   ├── users.txt             ← User accounts (pipe-delimited)
│   ├── balances.txt          ← Online + Offline balances
│   ├── transactions.txt      ← Completed transactions
│   └── offline_transactions.txt ← Queued offline tx (pending sync)
├── static/
│   ├── css/style.css         ← All styles
│   └── js/app.js             ← Frontend logic
└── templates/
    ├── base.html             ← Sidebar layout template
    ├── login.html
    ├── register.html
    ├── dashboard.html
    ├── wallet.html
    ├── transfer.html
    ├── history.html
    └── admin.html
```

---

## 🚀 Setup & Run

### 1. Install Python (3.8+)
```bash
python --version   # should be 3.8 or higher
```

### 2. Install Flask
```bash
pip install flask
# or
pip install -r requirements.txt
```

### 3. Run the App
```bash
cd nepalpay
python app.py
```

### 4. Open Browser
Visit: **http://127.0.0.1:5000**

---

## 📋 .txt File Formats

### users.txt
```
username|sha256_password_hash|email|phone|created_at
alice|5e884898da...|alice@email.com|9800000001|2024-01-15 10:30:00
```

### balances.txt
```
username|online_balance|offline_balance
alice|1500.00|500.00
```

### transactions.txt
```
tx_id|timestamp|sender|receiver|amount|type|status|note
TXN3A4B2C1D0E|2024-01-15 10:35:00|SYSTEM|alice|2000.0|deposit|completed|Bank deposit
TXNF1E2D3C4B|2024-01-15 10:40:00|alice|bob|500.0|online|completed|For lunch
```

### offline_transactions.txt
```
tx_id|timestamp|sender|receiver|amount|type|status|note
TXN9A8B7C6D5|2024-01-15 18:30:00|alice|bob|200.0|offline|pending|Offline payment
TXN1A2B3C4D5|2024-01-15 18:35:00|alice|charlie|150.0|offline|synced|Synced tx
```

---

## 🔄 Offline Sync Logic

1. User loads offline wallet: `online_balance -= X`, `offline_balance += X`
2. User makes offline transfer: `offline_balance -= amount`, tx saved to `offline_transactions.txt` with `status=pending`
3. Balance deducted IMMEDIATELY (anti-double-spend protection)
4. When server is available, user clicks "Sync":
   - All `pending` records in `offline_transactions.txt` are moved to `transactions.txt` with `status=synced`
   - Receiver's online balance is credited
   - Offline records updated to `status=synced`

---

## ⏰ Peak Hour Simulation

The `simulate_server_load()` function in `app.py` mimics real-world behavior:
- **6 PM – 10 PM**: 40% chance of server failure on each request
- **Other hours**: Always available

This demonstrates the problem: users experience random failures during peak hours, but offline wallet transactions always succeed.

---

## 🔐 Security Features

| Feature | Implementation |
|---|---|
| Password hashing | SHA-256 via `hashlib` |
| Session auth | Flask sessions with secret key |
| Double-spend prevention | Balance deducted before writing offline tx |
| Offline overspend prevention | Balance check before any deduction |
| Route protection | `@login_required` decorator |
| Offline balance cap | Max NPR 5,000 enforced server-side |

---

## 🧪 Test Walkthrough

1. Register two accounts: `alice` and `bob`
2. Log in as `alice`, deposit NPR 2000
3. Load NPR 500 to offline wallet
4. Make an online transfer to `bob` (NPR 100)
5. Enable "Simulate Offline" toggle on Transfer page
6. Make an offline transfer to `bob` (NPR 50)
7. Check History — offline tx shows as "PENDING"
8. Disable simulate toggle, click "Sync" — tx becomes "SYNCED"
9. Log in as `bob` — balance reflects both transfers

---

## 💡 Architecture Notes

- **No database**: All data in plain `.txt` files using `|` as delimiter
- **Atomic balance updates**: File read → modify → write prevents corruption
- **Stateless API**: Each request re-reads files (suitable for prototype scale)
- **Production path**: Replace `.txt` I/O with PostgreSQL, add Redis for sessions, deploy with gunicorn + nginx
