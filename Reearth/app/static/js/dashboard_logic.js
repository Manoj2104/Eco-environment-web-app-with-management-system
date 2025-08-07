let currentCheckinEventId = null;
let currentEventLat = null;
let currentEventLon = null;

// 📌 Booking modal
function showBookingModal(eventId, eventTime) {
  const form = document.getElementById("bookForm");
  form.onsubmit = function (e) {
    e.preventDefault();
    fetch(`/book_event/${eventId}`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: `appointment_time=${encodeURIComponent(eventTime)}`
    }).then(res => res.json()).then(data => {
      if (data.success) {
        document.getElementById(`btn-container-${eventId}`).innerHTML =
          `<button class="btn btn-warning btn-sm w-100" disabled>📌 Booked</button>`;
        bootstrap.Modal.getInstance(document.getElementById("confirmModal")).hide();
      } else {
        alert("Booking failed.");
      }
    });
  };
  document.getElementById("appointment_time").value = eventTime;
  new bootstrap.Modal(document.getElementById("confirmModal")).show();
}

// 📍 Location detection
function setUserLocation() {
  const statusEl = document.getElementById("location-status");
  statusEl.innerText = "📡 Detecting your location...";
  navigator.geolocation.getCurrentPosition(pos => {
    fetch("/update_location", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ latitude: pos.coords.latitude, longitude: pos.coords.longitude })
    }).then(res => res.json()).then(data => {
      statusEl.innerText = data.status === "success" ? "✅ Location updated! Reloading..." : "❌ Failed to update.";
      if (data.status === "success") setTimeout(() => location.reload(), 1500);
    });
  }, () => statusEl.innerText = "❌ Location access denied.");
}

// 🕑 Check-In prompt modal
function verifyCheckInPrompt(eventId, lat, lon) {
  currentCheckinEventId = eventId;
  currentEventLat = lat;
  currentEventLon = lon;
  new bootstrap.Modal(document.getElementById("verifyModal")).show();
}

// ✅ Check-in logic
function verifyCheckIn() {
  const passcode = document.getElementById("passcodeInput").value.trim();
  const qr = document.getElementById("qrInput").files[0];

  if (!passcode && !qr) {
    alert("❌ Please enter a passcode or upload a QR image.");
    return;
  }

  navigator.geolocation.getCurrentPosition(pos => {
    const dist = getDistance(pos.coords.latitude, pos.coords.longitude, currentEventLat, currentEventLon);
    if (dist > 0.3) {
      alert("🚫 Too far from event location.");
      return;
    }

    const formData = new FormData();
    formData.append("event_id", currentCheckinEventId);
    if (passcode) formData.append("passcode", passcode);
    if (qr) formData.append("qr", qr);

    fetch("/verify-checkin-alt", {
      method: "POST",
      body: formData
    }).then(res => res.json()).then(data => {
      if (data.success) {
        document.getElementById(`btn-container-${currentCheckinEventId}`).innerHTML =
          `<button class="btn btn-outline-success btn-sm w-100" disabled>✅ Checked In</button>`;
        bootstrap.Modal.getInstance(document.getElementById("verifyModal")).hide();
      } else {
        alert(data.message || "Check-in failed");
      }
    });
  }, () => alert("❌ Location fetch failed."));
}

// 📏 Distance Calculation
function getDistance(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// 🌀 Task auto start with timer
function showAssigningTask(eventId) {
  const btnContainer = document.getElementById(`btn-container-${eventId}`);
  let countdown = 15;

  const countdownBtn = document.createElement("button");
  countdownBtn.className = "btn btn-info btn-sm w-100";
  countdownBtn.disabled = true;
  countdownBtn.id = `start-task-btn-${eventId}`;
  countdownBtn.innerHTML = `🌀 Starting Task in ${countdown}s...`;
  btnContainer.innerHTML = "";
  btnContainer.appendChild(countdownBtn);

  const interval = setInterval(() => {
    countdown--;
    if (countdown > 0) {
      countdownBtn.innerHTML = `🌀 Starting Task in ${countdown}s...`;
    } else {
      clearInterval(interval);
      startTask(eventId);
    }
  }, 1000);
}

// 🧠 Start Task Button
function startTask(eventId) {
  fetch(`/start-task/${eventId}`, {
    method: "POST"
  })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        const btnContainer = document.getElementById(`btn-container-${eventId}`);
        btnContainer.innerHTML =
          `<button class="btn btn-outline-primary btn-sm w-100" onclick="launchTaskModal(${eventId})">🧠 Start Task</button>`;
      } else {
        alert(data.message || "Task could not be started.");
      }
    }).catch(() => alert("Failed to start task. Please try again."));
}

// 🎯 MCQ Modal logic
let completedTasks = 0;
function launchTaskModal(eventId) {
  const tabBar = document.getElementById("taskTabs");
  const contentArea = document.getElementById("taskContent");
  const finalSubmit = document.getElementById("finalSubmitBtn");
  tabBar.innerHTML = "";
  contentArea.innerHTML = "";
  finalSubmit.classList.add("d-none");

  tasks.forEach((task, idx) => {
    const tabId = `task-tab-${idx}`;
    tabBar.innerHTML += `
      <li class="nav-item" role="presentation">
        <button class="nav-link ${idx === 0 ? 'active' : ''}" id="${tabId}" data-bs-toggle="pill" data-bs-target="#task-${idx}" type="button" role="tab">
          ${task.title}
        </button>
      </li>
    `;
    const questionsHtml = task.questions.map((q, qidx) => {
      const opts = q.opts.map(opt =>
        `<button class="btn btn-light btn-sm m-1" data-answer="${q.a}" onclick="checkAnswer(this, '${opt}')">${opt}</button>`
      ).join("");
      return `<div class="mb-3"><strong>Q${qidx + 1}: ${q.q}</strong><div>${opts}</div></div>`;
    }).join("");

    contentArea.innerHTML += `
      <div class="tab-pane fade ${idx === 0 ? 'show active' : ''}" id="task-${idx}" role="tabpanel">
        <div class="border rounded p-3 mb-3">${questionsHtml}</div>
        <div class="mb-3">
          <label>📸 Upload Proof 1</label>
          <input type="file" class="form-control mb-2" name="proof1-${idx}" required>
          <label>📸 Upload Proof 2</label>
          <input type="file" class="form-control" name="proof2-${idx}" required>
        </div>
        <div class="text-end">
          <button class="btn btn-success" onclick="markTaskComplete(${idx})" id="submit-btn-${idx}">✅ Submit ${task.title}</button>
        </div>
      </div>
    `;
  });

  new bootstrap.Modal(document.getElementById("taskModal")).show();
}

function checkAnswer(btn, selected) {
  const correct = btn.dataset.answer;
  if (selected === correct) {
    btn.classList.remove('btn-light');
    btn.classList.add('btn-success');
  } else {
    btn.classList.remove('btn-light');
    btn.classList.add('btn-danger');
  }
  btn.disabled = true;
}

function markTaskComplete(idx) {
  const tab = document.getElementById(`task-${idx}`);
  const inputs = tab.querySelectorAll("input[type='file']");
  if ([...inputs].some(input => !input.files[0])) {
    alert("❗ Please upload both proofs before submitting.");
    return;
  }

  document.getElementById(`submit-btn-${idx}`).disabled = true;
  document.getElementById(`submit-btn-${idx}`).innerText = "✅ Submitted";

  completedTasks++;
  if (completedTasks === tasks.length) {
    document.getElementById("finalSubmitBtn").classList.remove("d-none");
  }
}

function submitAllTasks() {
  alert("🎉 All tasks submitted! XP awarded.");
  bootstrap.Modal.getInstance(document.getElementById("taskModal")).hide();
}

// 🌍 Reverse geolocation & timer logic
document.addEventListener("DOMContentLoaded", () => {
  const span = document.getElementById("user-location-name");
  fetch(`https://nominatim.openstreetmap.org/reverse?lat=${span.dataset.lat}&lon=${span.dataset.lon}&format=json`)
    .then(res => res.json())
    .then(data => span.innerText = data.display_name || "Location found")
    .catch(() => span.innerText = "Location found");

  setInterval(() => {
    fetch('/update-status-timers', { method: 'POST' });
  }, 60000);

  document.querySelectorAll('.countdown-btn').forEach(button => {
    const eventId = button.dataset.eventId;
    const eventTime = new Date(button.dataset.eventTime);
    const lat = parseFloat(button.dataset.lat);
    const lon = parseFloat(button.dataset.lon);
    const container = document.getElementById(`btn-container-${eventId}`);
    const card = container.closest('.event-card');

    const interval = setInterval(() => {
      const now = new Date();
      const diffMs = eventTime - now;
      const minsBefore = diffMs / 60000;
      const minsAfter = (now - eventTime) / 60000;

      if (minsBefore > 0 && minsBefore <= 30) {
        const mins = String(Math.floor(minsBefore)).padStart(2, '0');
        const secs = String(Math.floor((diffMs % 60000) / 1000)).padStart(2, '0');
        button.innerHTML = `⏳ ${mins}:${secs}`;
        button.className = "btn btn-secondary btn-sm w-100";
        button.disabled = true;
      } else if (minsAfter >= 0 && minsAfter <= 15) {
        button.innerHTML = "🕑 Check-In";
        button.className = "btn btn-success btn-sm w-100";
        button.disabled = false;
        button.onclick = () => verifyCheckInPrompt(eventId, lat, lon);
      } else if (minsAfter > 15 && minsAfter <= 25) {
        button.innerHTML = "⚠️ Last Check-In";
        button.className = "btn btn-warning btn-sm w-100";
        button.disabled = false;
        button.onclick = () => verifyCheckInPrompt(eventId, lat, lon);
      } else if (minsAfter > 25 && minsAfter <= 45) {
        button.innerHTML = "🕒 Marked as Past";
        button.className = "btn btn-dark btn-sm w-100";
        button.disabled = true;
      } else if (minsAfter > 45) {
        card.remove();
        clearInterval(interval);
      }
    }, 1000);
  });
});

// 🧩 Task question bank
const tasks = [
  {
    title: "Task 1",
    questions: [
      { q: "What is compost made from?", opts: ["Plastic", "Kitchen waste", "Glass"], a: "Kitchen waste" },
      { q: "Best waste management method?", opts: ["Burning", "Recycling", "Dumping"], a: "Recycling" },
      { q: "Biodegradable item?", opts: ["Plastic bag", "Banana Peel", "Can"], a: "Banana Peel" },
      { q: "Color for recyclable bin?", opts: ["Blue", "Green", "Red"], a: "Blue" }
    ]
  },
  {
    title: "Task 2",
    questions: [
      { q: "Which gas causes global warming?", opts: ["CO2", "H2O", "O2"], a: "CO2" },
      { q: "Best transport to reduce pollution?", opts: ["Car", "Bike", "Cycle"], a: "Cycle" },
      { q: "E-waste item?", opts: ["Plastic bottle", "TV remote", "Banana"], a: "TV remote" },
      { q: "Ocean animal hurt by plastic?", opts: ["Turtle", "Lion", "Cat"], a: "Turtle" }
    ]
  }
];
