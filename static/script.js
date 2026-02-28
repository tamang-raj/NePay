// ---------------------------
// Offline Mode Simulation
// ---------------------------

let offlineMode = false;

function toggleOfflineMode() {
    offlineMode = !offlineMode;

    const badge = document.getElementById("offlineBadge");

    if (offlineMode) {
        badge.style.display = "block";
        alert("Offline Mode Activated.\nOnline transfers disabled.");
    } else {
        badge.style.display = "none";
        alert("Back Online.");
    }
}

// ---------------------------
// Peak Load Simulation
// ---------------------------

function simulatePeakLoad() {
    const hour = new Date().getHours();

    // Simulate peak between 6PM - 9PM
    if (hour >= 18 && hour <= 21) {
        alert("⚠ Peak Hour Simulation: Online services may be slow.");
    }
}

window.onload = function() {
    simulatePeakLoad();
};


// ---------------------------
// Basic Validation
// ---------------------------

document.addEventListener("submit", function(e) {
    const amountField = document.querySelector("input[name='amount']");
    if (amountField) {
        if (parseFloat(amountField.value) <= 0) {
            alert("Amount must be greater than zero.");
            e.preventDefault();
        }
    }
});