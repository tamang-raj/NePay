/**
 * NepaPay — Main JavaScript
 * Handles: API calls, toasts, balance refresh, offline simulation, transfer forms
 */

// ─── Toast Notifications ──────────────────────────────────────────────────────

function showToast(message, type = "info") {
  const icons = { success: "✅", error: "❌", warning: "⚠️", info: "ℹ️" };
  const container = document.getElementById("toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${icons[type] || "ℹ️"}</span><span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 3200);
}

// ─── Balance Refresh ──────────────────────────────────────────────────────────

function refreshBalances() {
  fetch("/api/balance")
    .then(r => r.json())
    .then(data => {
      const onlineEl  = document.getElementById("online-balance-amount");
      const offlineEl = document.getElementById("offline-balance-amount");
      if (onlineEl)  onlineEl.textContent = "NPR " + formatAmount(data.online_balance);
      if (offlineEl) offlineEl.textContent = "NPR " + formatAmount(data.offline_balance);
      updateServerStatus(data.server_available);
      // Update progress bar
      const bar = document.getElementById("offline-progress");
      if (bar) {
        const pct = Math.min((data.offline_balance / 5000) * 100, 100);
        bar.style.width = pct + "%";
      }
    })
    .catch(() => {});
}

function formatAmount(n) {
  return parseFloat(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ─── Server Status ────────────────────────────────────────────────────────────

function updateServerStatus(available) {
  const bars = document.querySelectorAll(".server-status-bar");
  bars.forEach(bar => {
    bar.className = "server-status-bar " + (available ? "online" : "offline");
    const dot  = bar.querySelector(".status-dot");
    const text = bar.querySelector(".status-text");
    if (text) text.textContent = available
      ? "Server Online — All systems operational"
      : "⚠️  Server Overloaded — Use Offline Wallet";
  });
}

function checkServerStatus() {
  fetch("/api/server_status")
    .then(r => r.json())
    .then(data => {
      updateServerStatus(data.available);
      // If peak hours, show offline recommendation banner
      const banner = document.getElementById("offline-recommend-banner");
      if (banner) {
        banner.style.display = data.peak_hours ? "flex" : "none";
      }
    })
    .catch(() => {});
}

// ─── Form Helpers ─────────────────────────────────────────────────────────────

function setLoading(btn, loading) {
  if (loading) {
    btn.dataset.originalText = btn.innerHTML;
    btn.innerHTML = '<span class="spinner"></span> Processing...';
    btn.disabled = true;
  } else {
    btn.innerHTML = btn.dataset.originalText || btn.innerHTML;
    btn.disabled = false;
  }
}

function postForm(url, formData, btn, successCb, errorCb) {
  setLoading(btn, true);
  fetch(url, { method: "POST", body: formData })
    .then(r => r.json())
    .then(data => {
      setLoading(btn, false);
      if (data.success) {
        showToast(data.message, "success");
        refreshBalances();
        if (successCb) successCb(data);
      } else {
        showToast(data.message, data.use_offline ? "warning" : "error");
        if (errorCb) errorCb(data);
      }
    })
    .catch(err => {
      setLoading(btn, false);
      showToast("Network error. Please try again.", "error");
    });
}

// ─── Deposit ──────────────────────────────────────────────────────────────────

function handleDeposit(e) {
  e.preventDefault();
  const form = e.target;
  const btn  = form.querySelector("[type=submit]");
  const fd   = new FormData(form);
  postForm("/api/deposit", fd, btn, (data) => {
    form.reset();
    // Show tx id
    const txInfo = document.getElementById("deposit-tx-info");
    if (txInfo) {
      txInfo.textContent = "Transaction ID: " + data.tx_id;
      txInfo.style.display = "block";
    }
  });
}

// ─── Load Offline Wallet ──────────────────────────────────────────────────────

function handleLoadOffline(e) {
  e.preventDefault();
  const form = e.target;
  const btn  = form.querySelector("[type=submit]");
  const fd   = new FormData(form);
  postForm("/api/load_offline", fd, btn, (data) => {
    form.reset();
    const txInfo = document.getElementById("load-tx-info");
    if (txInfo) {
      txInfo.textContent = "Transaction ID: " + data.tx_id;
      txInfo.style.display = "block";
    }
  });
}

// ─── Online Transfer ──────────────────────────────────────────────────────────

function handleOnlineTransfer(e) {
  e.preventDefault();
  const form = e.target;
  const btn  = form.querySelector("[type=submit]");
  const fd   = new FormData(form);
  postForm("/api/online_transfer", fd, btn,
    (data) => {
      form.reset();
      appendTransactionResult("online-result", data);
    },
    (data) => {
      if (data.use_offline) {
        // Highlight the offline section
        const offlinePanel = document.querySelector(".offline-panel");
        if (offlinePanel) {
          offlinePanel.style.boxShadow = "0 0 0 2px rgba(155,89,182,0.6)";
          setTimeout(() => offlinePanel.style.boxShadow = "", 2000);
        }
      }
    }
  );
}

// ─── Offline Transfer ─────────────────────────────────────────────────────────

function handleOfflineTransfer(e) {
  e.preventDefault();
  const form = e.target;
  const btn  = form.querySelector("[type=submit]");
  const fd   = new FormData(form);
  postForm("/api/offline_transfer", fd, btn, (data) => {
    form.reset();
    appendTransactionResult("offline-result", data);
    // Update pending badge
    const badge = document.getElementById("pending-badge");
    if (badge) {
      const count = parseInt(badge.textContent || "0") + 1;
      badge.textContent = count;
      badge.style.display = "inline";
    }
    showToast("Transaction saved locally — will sync when server is available", "info");
  });
}

function appendTransactionResult(containerId, data) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = `
    <div class="alert alert-success" style="margin-top:1rem">
      <span>✅</span>
      <div>
        <div>${data.message}</div>
        <div class="monospace" style="margin-top:0.25rem; font-size:0.72rem">${data.tx_id}</div>
      </div>
    </div>`;
}

// ─── Sync Offline ─────────────────────────────────────────────────────────────

function handleSync(e) {
  const btn = e.currentTarget;
  setLoading(btn, true);
  fetch("/api/sync", { method: "POST" })
    .then(r => r.json())
    .then(data => {
      setLoading(btn, false);
      if (data.success) {
        showToast(data.message, "success");
        refreshBalances();
        if (data.synced_count > 0) {
          setTimeout(() => location.reload(), 1200);
        }
      } else {
        showToast(data.message, "error");
      }
    })
    .catch(() => {
      setLoading(btn, false);
      showToast("Sync failed. Check connection.", "error");
    });
}

// ─── Transfer Mode Toggle ─────────────────────────────────────────────────────

function initTransferToggle() {
  const onlineBtn  = document.getElementById("toggle-online");
  const offlineBtn = document.getElementById("toggle-offline");
  const onlineForm = document.getElementById("online-transfer-section");
  const offlineForm= document.getElementById("offline-transfer-section");
  if (!onlineBtn) return;

  onlineBtn.addEventListener("click", () => {
    onlineBtn.className  = "mode-btn active-online";
    offlineBtn.className = "mode-btn";
    if (onlineForm)  onlineForm.style.display  = "block";
    if (offlineForm) offlineForm.style.display = "none";
  });

  offlineBtn.addEventListener("click", () => {
    offlineBtn.className = "mode-btn active-offline";
    onlineBtn.className  = "mode-btn";
    if (offlineForm) offlineForm.style.display = "block";
    if (onlineForm)  onlineForm.style.display  = "none";
  });
}

// ─── Transaction Filter ───────────────────────────────────────────────────────

function initHistoryFilters() {
  const filterBtns = document.querySelectorAll(".filter-btn");
  const txItems    = document.querySelectorAll(".tx-item[data-type]");
  filterBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      filterBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const filter = btn.dataset.filter;
      txItems.forEach(item => {
        if (filter === "all" || item.dataset.type === filter) {
          item.style.display = "";
        } else {
          item.style.display = "none";
        }
      });
    });
  });
}

// ─── Offline Mode Simulation Toggle ──────────────────────────────────────────

function initOfflineSimToggle() {
  const toggle = document.getElementById("offline-sim-toggle");
  if (!toggle) return;
  toggle.addEventListener("change", () => {
    const simActive = toggle.checked;
    showToast(
      simActive ? "Offline mode simulated — online features disabled" : "Online mode restored",
      simActive ? "warning" : "success"
    );
    // Disable online transfer button if simulating offline
    const onlineTransferBtn = document.getElementById("online-transfer-btn");
    if (onlineTransferBtn) {
      onlineTransferBtn.disabled = simActive;
      onlineTransferBtn.title = simActive ? "Server unavailable (simulated)" : "";
    }
    const depositBtn = document.getElementById("deposit-btn");
    if (depositBtn) {
      depositBtn.disabled = simActive;
    }
    // Update status bar
    updateServerStatus(!simActive);
  });
}

// ─── Amount Formatter on Input ────────────────────────────────────────────────

function initAmountInputs() {
  document.querySelectorAll(".amount-input").forEach(input => {
    input.addEventListener("input", () => {
      const val = parseFloat(input.value);
      const preview = document.getElementById(input.dataset.preview);
      if (preview && !isNaN(val)) {
        preview.textContent = "NPR " + formatAmount(val);
      }
    });
  });
}

// ─── Init ─────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  // Bind forms
  const depositForm = document.getElementById("deposit-form");
  if (depositForm) depositForm.addEventListener("submit", handleDeposit);

  const loadForm = document.getElementById("load-offline-form");
  if (loadForm) loadForm.addEventListener("submit", handleLoadOffline);

  const onlineTxForm = document.getElementById("online-transfer-form");
  if (onlineTxForm) onlineTxForm.addEventListener("submit", handleOnlineTransfer);

  const offlineTxForm = document.getElementById("offline-transfer-form");
  if (offlineTxForm) offlineTxForm.addEventListener("submit", handleOfflineTransfer);

  const syncBtn = document.getElementById("sync-btn");
  if (syncBtn) syncBtn.addEventListener("click", handleSync);

  // Sidebar mobile
  const menuToggle = document.getElementById("menu-toggle");
  const sidebar = document.getElementById("sidebar");
  if (menuToggle && sidebar) {
    menuToggle.addEventListener("click", () => sidebar.classList.toggle("open"));
    document.addEventListener("click", (e) => {
      if (!sidebar.contains(e.target) && !menuToggle.contains(e.target)) {
        sidebar.classList.remove("open");
      }
    });
  }

  // Periodic updates
  refreshBalances();
  checkServerStatus();
  setInterval(checkServerStatus, 15000);
  setInterval(refreshBalances, 30000);

  // Inits
  initTransferToggle();
  initHistoryFilters();
  initOfflineSimToggle();
  initAmountInputs();
});
