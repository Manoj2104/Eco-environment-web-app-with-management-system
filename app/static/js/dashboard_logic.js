// ═══════════════════════════════════════════════════════════
// dashboard_logic.js — Re-Earth  |  Full Merged Version
// ═══════════════════════════════════════════════════════════

// ── State ────────────────────────────────────────────────────
let currentCheckinEventId = null;
let currentEventLat       = null;
let currentEventLon       = null;

let currentTaskEventId    = null;
let currentTaskId         = null;
let allTasks              = [];

let isGoalFlow            = false;
let currentGoalId         = null;
let currentGoalTaskId     = null;

// ═══════════════════════════════════════════════════════════
// 1. BOOKING MODAL
// ═══════════════════════════════════════════════════════════
function showBookingModal(eventId, eventTime) {
  const modalEl = document.getElementById("confirmModal");
  const form = document.getElementById("bookForm");
  if (!modalEl || !form) return;

  const submitBtn = form.querySelector('button[type="submit"]');
  const initialText = submitBtn ? submitBtn.innerHTML : "Join Mission Now";

  form.onsubmit = function (e) {
    e.preventDefault();
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span> Joining...`;
    }

    fetch(`/book_event/${eventId}`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: `appointment_time=${encodeURIComponent(eventTime)}`
    })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          const container = document.getElementById(`btn-container-${eventId}`);
          if (container) {
            container.innerHTML = `<button class="btn btn-warning rounded-pill btn-sm fw-bold px-3 py-1 shadow-sm" disabled>📌 Booked</button>`;
          }
          const instance = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
          instance.hide();
          showToast("🎉 Mission joined successfully!");
        } else {
          showToast("❌ Booking failed: " + (data.message || ""), "danger");
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = initialText;
          }
        }
      })
      .catch(err => {
        console.error("Booking error:", err);
        showToast("⚠️ Network error during booking.", "danger");
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = initialText;
        }
      });
  };

  document.getElementById("appointment_time").value = eventTime;
  const modalInstance = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
  modalInstance.show();
}

// ═══════════════════════════════════════════════════════════
// 2. LOCATION DETECTION
// ═══════════════════════════════════════════════════════════
function setUserLocation() {
  const statusEl = document.getElementById("location-status");
  if (statusEl) statusEl.innerText = "📡 Detecting your location...";

  navigator.geolocation.getCurrentPosition(
    pos => {
      fetch("/update_location", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          latitude:  pos.coords.latitude,
          longitude: pos.coords.longitude
        })
      })
        .then(res => res.json())
        .then(data => {
          const ok = data.success || data.status === "success";
          if (statusEl) statusEl.innerText = ok
            ? "✅ Location updated! Reloading..."
            : "❌ Failed to update.";
          if (ok) setTimeout(() => location.reload(), 1500);
        });
    },
    () => { if (statusEl) statusEl.innerText = "❌ Location access denied."; }
  );
}

// ═══════════════════════════════════════════════════════════
// 3. CHECK-IN
// ═══════════════════════════════════════════════════════════
function verifyCheckInPrompt(eventId, lat, lon) {
  currentCheckinEventId = eventId;
  currentEventLat = lat;
  currentEventLon = lon;
  new bootstrap.Modal(document.getElementById("verifyModal")).show();
}

function verifyCheckIn() {
  const passcode = document.getElementById("passcodeInput").value.trim();
  const qr       = document.getElementById("qrInput").files[0];

  if (!passcode && !qr) {
    alert("❌ Please enter a passcode or upload a QR image.");
    return;
  }

  navigator.geolocation.getCurrentPosition(
    pos => {
      const dist = getDistance(
        pos.coords.latitude, pos.coords.longitude,
        currentEventLat, currentEventLon
      );
      if (dist > 0.3) {
        alert("🚫 You are too far from the event location.");
        return;
      }

      const formData = new FormData();
      formData.append("event_id", currentCheckinEventId);
      if (passcode) formData.append("passcode", passcode);
      if (qr)       formData.append("qr", qr);

      fetch("/verify-checkin-alt", { method: "POST", body: formData })
        .then(res => res.json())
        .then(data => {
          if (data.success) {
            const container = document.getElementById(`btn-container-${currentCheckinEventId}`);
            if (container) {
              container.innerHTML = `<button class="btn btn-outline-primary btn-sm w-100 fw-bold rounded-pill" 
                                             onclick="launchTaskModal(${currentCheckinEventId})">🧠 Start Task</button>`;
            }
            bootstrap.Modal.getInstance(document.getElementById("verifyModal")).hide();
          } else {
            alert(data.message || "Check-in failed");
          }
        });
    },
    () => alert("❌ Location fetch failed.")
  );
}

// ═══════════════════════════════════════════════════════════
// 4. DISTANCE HELPERS
// ═══════════════════════════════════════════════════════════
function getDistance(lat1, lon1, lat2, lon2) {
  const R    = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a    = Math.sin(dLat / 2) ** 2 +
               Math.cos(lat1 * Math.PI / 180) *
               Math.cos(lat2 * Math.PI / 180) *
               Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function calculateDistance(lat1, lon1, lat2, lon2, elementId) {
  const el = document.getElementById(elementId);
  if (!el) return;
  if (!lat1 || !lon1 || !lat2 || !lon2) {
    el.innerText = "📍 Location unavailable";
    return;
  }
  const d = getDistance(parseFloat(lat1), parseFloat(lon1),
                        parseFloat(lat2), parseFloat(lon2));
  el.innerText = `📍 ${d.toFixed(1)} km away`;
}

// ═══════════════════════════════════════════════════════════
// 5. TASK AUTO-START COUNTDOWN  (after check-in)
// ═══════════════════════════════════════════════════════════
function showAssigningTask(eventId) {
  const btnContainer = document.getElementById(`btn-container-${eventId}`);
  let countdown = 15;

  const countdownBtn = document.createElement("button");
  countdownBtn.className = "btn btn-info btn-sm w-100";
  countdownBtn.disabled  = true;
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

function startTask(eventId) {
  fetch(`/start-task/${eventId}`, { method: "POST" })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        document.getElementById(`btn-container-${eventId}`).innerHTML =
          `<button class="btn btn-outline-primary btn-sm w-100"
                   onclick="launchTaskModal(${eventId})">🧠 Start Task</button>`;
      } else {
        alert(data.message || "Task could not be started.");
      }
    })
    .catch(() => alert("Failed to start task. Please try again."));
}

// ═══════════════════════════════════════════════════════════
// 6. PRO TASK MODAL
// ═══════════════════════════════════════════════════════════
function launchTaskModal(eventIdOrGoalId) {
  // If we didn't come from launchGoalTaskModal, ensure isGoalFlow is false
  if (typeof isGoalFlow === 'undefined' || !isGoalFlow) {
      isGoalFlow = false;
      currentTaskEventId = eventIdOrGoalId;
  } else {
      currentGoalId = eventIdOrGoalId;
  }
  
  allTasks = [];

  const loadingEl  = document.getElementById("task-loading");
  const cardsEl    = document.getElementById("task-cards-container");
  const listView   = document.getElementById("task-list-view");
  const detailView = document.getElementById("task-detail-view");
  const progressBar= document.getElementById("task-progress-bar");
  const progressTxt= document.getElementById("task-progress-text");

  if (loadingEl)   { loadingEl.style.display = "block";
                     loadingEl.innerHTML = `<div class="text-center py-4">
                       <div class="spinner-border text-success"></div>
                       <p class="mt-2 text-muted small">Loading your tasks...</p>
                     </div>`; }
  if (cardsEl)     cardsEl.innerHTML  = "";
  if (listView)    listView.style.display   = "block";
  if (detailView)  detailView.style.display = "none";
  if (progressBar) progressBar.style.width  = "0%";
  if (progressTxt) progressTxt.innerText    = "Loading...";

  new bootstrap.Modal(document.getElementById("taskModal")).show();
  loadTasks(eventIdOrGoalId);
}

function loadTasks(id) {
  const url = isGoalFlow ? `/my_goal_tasks/${id}` : `/my_tasks/${id}`;
  fetch(url)
    .then(r => r.json())
    .then(data => {
      allTasks = data.tasks || [];
      const titleEl   = document.getElementById("task-event-title");
      const loadingEl = document.getElementById("task-loading");
      if (titleEl)   titleEl.innerText        = `${allTasks.length} tasks assigned`;
      if (loadingEl) loadingEl.style.display  = "none";
      renderTaskCards(allTasks);
    })
    .catch(() => {
      const loadingEl = document.getElementById("task-loading");
      if (loadingEl) loadingEl.innerHTML =
        `<div class="alert alert-danger m-3">Failed to load tasks. Please try again.</div>`;
    });
}

function renderTaskCards(tasks) {
  const container   = document.getElementById("task-cards-container");
  const progressBar = document.getElementById("task-progress-bar");
  const progressTxt = document.getElementById("task-progress-text");
  if (!container) return;

  const completed = tasks.filter(t => t.status === "verified").length;
  const total     = tasks.length;
  const pct       = total > 0 ? Math.round((completed / total) * 100) : 0;

  if (progressBar) progressBar.style.width = `${pct}%`;
  if (progressTxt) progressTxt.innerText   = `${completed} / ${total} tasks verified`;
  
  const pctDisplay = document.getElementById("task-pct-display");
  if (pctDisplay) pctDisplay.innerText = `${pct}%`;

  if (!tasks.length) {
    container.innerHTML = `<div class="alert alert-warning text-center">No tasks found.</div>`;
    return;
  }

  container.innerHTML = tasks.map((t, idx) => {
    const isDone   = t.status === "verified";
    const isLocked = idx > 0 && tasks[idx - 1].status !== "verified";
    return `
      <div class="epic-card-sm ${isDone ? "completed" : ""} ${isLocked ? "locked" : ""}"
           onclick="${isDone || isLocked ? "" : `openTaskDetail(${t.id})`}">
        
        <div class="card-index-sm shadow-sm"
             style="background:${isDone ? "#10b981" : isLocked ? "#f1f5f9" : "#10b981"};">
          ${isDone ? '<i class="bi bi-patch-check-fill fs-6"></i>' : isLocked ? '<i class="bi bi-lock-fill"></i>' : t.order}
        </div>

        <div class="flex-grow-1 overflow-hidden pe-5">
          <div class="fw-bold text-dark ${isDone ? "text-decoration-line-through opacity-50" : ""}" style="font-size: 0.95rem; letter-spacing: -0.2px;">
            ${t.title}
          </div>
          <div class="text-muted text-truncate" style="font-size: 0.75rem; max-width: 320px;">${t.description}</div>
        </div>

        ${isLocked ? "" : `
        <div class="task-xp-badge-sm">⭐ ${t.xp_reward}</div>
        `}
      </div>`;
  }).join("");
}

function openTaskDetail(taskId) {
  const task = allTasks.find(t => t.id === taskId);
  if (!task) return;
  
  if (isGoalFlow) {
      currentGoalTaskId = taskId;
  } else {
      currentTaskId = taskId;
  }

  const get = id => document.getElementById(id);
  if (get("detail-task-order")) get("detail-task-order").innerText = `TASK ${task.order}`;
  if (get("detail-task-xp"))    get("detail-task-xp").innerText    = `⭐ ${task.xp_reward} XP`;
  if (get("detail-task-title"))get("detail-task-title").innerText  = task.title;
  if (get("detail-task-desc")) get("detail-task-desc").innerText   = task.description;

  if (get("proof-section"))    get("proof-section").style.display  = "block";
  if (get("upload-default-state")) get("upload-default-state").style.display = "block";
  if (get("questions-section"))get("questions-section").style.display = "none";
  if (get("ai-status"))        get("ai-status").style.display      = "none";
  if (get("ai-result"))        get("ai-result").style.display      = "none";
  if (get("taskProofPreviewContainer")) get("taskProofPreviewContainer").style.display = "none";
  if (get("taskProofPreview")) get("taskProofPreview").style.display= "none";
  if (get("taskProofFile"))    get("taskProofFile").value           = "";
  if (get("uploadProofBtn"))   { get("uploadProofBtn").disabled = false;
                                  get("uploadProofBtn").innerText = "Request Verify"; }

  window.currentTaskQuestions = task.questions || [];

  if (get("task-list-view"))   get("task-list-view").style.display   = "none";
  if (get("task-detail-view")) get("task-detail-view").style.display = "block";
}

function showTaskList() {
  const get = id => document.getElementById(id);
  if (get("task-list-view"))   get("task-list-view").style.display   = "block";
  if (get("task-detail-view")) get("task-detail-view").style.display = "none";
  loadTasks(currentTaskEventId);
}

// Image preview
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("taskProofFile")?.addEventListener("change", function () {
    if (!this.files[0]) return;
    const reader = new FileReader();
    reader.onload = e => {
      const img = document.getElementById("taskProofPreview");
      const container = document.getElementById("taskProofPreviewContainer");
      if (img) { 
        img.src = e.target.result; 
        img.style.display = "inline-block"; 
        if (container) container.style.display = "block";
      }
    };
    reader.readAsDataURL(this.files[0]);
  });
});

function uploadTaskProof() {
  const file = document.getElementById("taskProofFile")?.files[0];
  if (!file) { showToast("Please select a photo first!", "warning"); return; }

  const get = id => document.getElementById(id);
  const btn = get("uploadProofBtn");
  if (btn) { btn.disabled = true; btn.innerText = "⏳ Verifying..."; }
  if (get("ai-status")) get("ai-status").style.display = "flex";
  if (get("ai-result")) get("ai-result").style.display = "none";

  const formData = new FormData();
  formData.append("proof", file);

  const taskId = isGoalFlow ? currentGoalTaskId : currentTaskId;
  const url = isGoalFlow ? `/submit_goal_task_proof/${taskId}` : `/submit_task_proof/${taskId}`;

  fetch(url, { method: "POST", body: formData })
    .then(r => r.json())
    .then(data => {
      if (get("ai-status")) get("ai-status").style.display = "none";
      if (get("ai-result")) get("ai-result").style.display = "block";

      if (data.success && data.ai_verified) {
        get("ai-result").innerHTML = `
          <div class="p-3 bg-success bg-opacity-10 border border-success border-opacity-25 rounded-4 mb-3">
            <div class="d-flex align-items-center gap-2 text-success fw-bold mb-1">
              <i class="bi bi-shield-fill-check"></i> RAFAEL AI Verified
            </div>
            <div class="small text-secondary">
              Analyzed with <strong>${data.confidence}% confidence</strong>. 
              Mission objectives detected. 🌟 <strong>+${data.xp_earned} XP</strong> awarded.
            </div>
          </div>`;
        showToast(`✅ RAFAEL AI: +${data.xp_earned} XP earned!`);
        setTimeout(() => showQuestions(window.currentTaskQuestions), 800);
      } else {
        get("ai-result").innerHTML = `
          <div class="alert alert-warning rounded-3 py-2 small">
            ⚠️ Could not verify. Please upload a clearer photo.
          </div>`;
        if (btn) { btn.disabled = false; btn.innerText = "📤 Try Again"; }
      }
    })
    .catch(() => {
      if (get("ai-status")) get("ai-status").style.display = "none";
      if (get("ai-result")) {
        get("ai-result").style.display = "block";
        get("ai-result").innerHTML = `<div class="alert alert-danger py-2 small">❌ Server error.</div>`;
      }
      if (btn) { btn.disabled = false; btn.innerText = "📤 Try Again"; }
    });
}

function showQuestions(questions) {
  if (!questions || !questions.length) { showTaskList(); checkEventCompletion(); return; }

  const get = id => document.getElementById(id);
  if (get("proof-section"))     get("proof-section").style.display     = "none";
  if (get("questions-section")) get("questions-section").style.display = "block";

  const container = get("questions-container");
  if (!container) return;

  container.innerHTML = questions.map((q, i) => `
    <div class="mb-4 p-3 rounded-3 bg-light">
      <p class="fw-semibold mb-2">Q${i+1}. ${q.question}
        <span class="badge bg-warning text-dark ms-1 small">+5 XP</span>
      </p>
      ${q.type === "mcq"
        ? q.options.map(opt => `
          <div class="form-check">
            <input class="form-check-input" type="radio"
                   name="q_${q.id}" value="${opt}"
                   id="opt_${q.id}_${opt.replace(/\W/g,"_")}">
            <label class="form-check-label small"
                   for="opt_${q.id}_${opt.replace(/\W/g,"_")}">${opt}</label>
          </div>`).join("")
        : `<input type="text" class="form-control form-control-sm mt-1"
                  id="text_ans_${q.id}" placeholder="Type your answer...">`}
    </div>`).join("");
}

function submitAnswers() {
  const questions = window.currentTaskQuestions || [];
  const answers   = {};
  let allAnswered  = true;

  questions.forEach(q => {
    if (q.type === "mcq") {
      const sel = document.querySelector(`input[name="q_${q.id}"]:checked`);
      if (sel) answers[q.id] = sel.value; else allAnswered = false;
    } else {
      const inp = document.getElementById(`text_ans_${q.id}`);
      if (inp?.value.trim()) answers[q.id] = inp.value.trim(); else allAnswered = false;
    }
  });

  if (!allAnswered) { showToast("Please answer all questions!", "warning"); return; }

  fetch(`/submit_task_answers/${currentTaskId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answers })
  })
    .then(r => r.json())
    .then(data => {
      if (data.score > 0) showToast(`🧠 +${data.score} bonus XP!`);
      if (data.awarded?.length) setTimeout(() =>
        showToast(`🏅 New badge: ${data.awarded.join(", ")}!`), 1200);
      setTimeout(() => { showTaskList(); setTimeout(checkEventCompletion, 800); }, 1000);
    })
    .catch(() => showToast("Error submitting answers", "danger"));
}

function checkEventCompletion() {
  const id = isGoalFlow ? currentGoalId : currentTaskEventId;
  const url = isGoalFlow ? `/check_goal_completion/${id}` : `/check_event_completion/${id}`;
  
  fetch(url)
    .then(r => r.json())
    .then(data => {
      loadTasks(id);
      if (!data.complete) return;

      bootstrap.Modal.getInstance(document.getElementById("taskModal"))?.hide();

      const get = id => document.getElementById(id);
      if (get("celebrate-xp"))    get("celebrate-xp").innerText    = data.total_xp || 0;
      if (get("celebrate-total-xp")) get("celebrate-total-xp").innerText = data.grand_total_xp || data.total_xp || 0;
      if (get("celebrate-level")) get("celebrate-level").innerText = data.level || 1;
      if (get("cert-download-btn") && data.certificate_url)
        get("cert-download-btn").href = data.certificate_url;
      if (get("celebrate-badges") && data.awarded?.length)
        get("celebrate-badges").innerHTML = `
          <div class="alert alert-warning py-2 small">
            🏅 New Badge: <strong>${data.awarded.join(", ")}</strong>
          </div>`;

      const btnContainer = get(`btn-container-${currentTaskEventId}`);
      if (btnContainer)
        btnContainer.innerHTML =
          `<button class="btn btn-outline-success btn-sm w-100" disabled>✅ Completed</button>`;

      setTimeout(() =>
        new bootstrap.Modal(get("xpCelebrationModal")).show(), 400);
    });
}

// ═══════════════════════════════════════════════════════════
// 7. COUNTDOWN TIMER + EVENT CARD AUTO-UPDATE
// ═══════════════════════════════════════════════════════════
document.addEventListener("DOMContentLoaded", () => {

  const span = document.getElementById("user-location-name");
  if (span?.dataset.lat && span?.dataset.lon) {
    fetch(`https://nominatim.openstreetmap.org/reverse?lat=${span.dataset.lat}&lon=${span.dataset.lon}&format=json`)
      .then(res => res.json())
      .then(data => { span.innerText = data.display_name || "Location found"; })
      .catch(() => { span.innerText = "Location found"; });
  }

  setInterval(() => fetch("/update-status-timers", { method: "POST" }).catch(() => {}), 60000);

  document.querySelectorAll(".countdown-btn").forEach(button => {
    const eventId   = button.dataset.eventId;
    const eventTime = new Date(button.dataset.eventTime);
    const lat       = parseFloat(button.dataset.lat);
    const lon       = parseFloat(button.dataset.lon);
    const container = document.getElementById(`btn-container-${eventId}`);
    const card      = container?.closest(".event-card");

    const interval = setInterval(() => {
      const now        = new Date();
      const diffMs     = eventTime - now;
      const minsBefore = diffMs / 60000;
      const minsAfter  = (now - eventTime) / 60000;

      if (minsBefore > 0 && minsBefore <= 30) {
        const mins = String(Math.floor(minsBefore)).padStart(2, "0");
        const secs = String(Math.floor((diffMs % 60000) / 1000)).padStart(2, "0");
        button.innerHTML = `⏳ ${mins}:${secs}`;
        button.className = "btn btn-secondary btn-sm w-100";
        button.disabled  = true;

      } else if (minsAfter >= 0 && minsAfter <= 15) {
        button.innerHTML = "🕑 Check-In";
        button.className = "btn btn-success btn-sm w-100";
        button.disabled  = false;
        button.onclick   = () => verifyCheckInPrompt(eventId, lat, lon);

      } else if (minsAfter > 15 && minsAfter <= 25) {
        button.innerHTML = "⚠️ Last Check-In";
        button.className = "btn btn-warning btn-sm w-100";
        button.disabled  = false;
        button.onclick   = () => verifyCheckInPrompt(eventId, lat, lon);

      } else if (minsAfter > 25 && minsAfter <= 45) {
        button.innerHTML = "🕒 Marked as Past";
        button.className = "btn btn-dark btn-sm w-100";
        button.disabled  = true;

      } else if (minsAfter > 45) {
        if (card) card.remove();
        clearInterval(interval);
      }
    }, 1000);
  });
});

// ═══════════════════════════════════════════════════════════
// 8. TOAST
// ═══════════════════════════════════════════════════════════
function showToast(msg, type = "success") {
  const t = document.createElement("div");
  t.className = `alert alert-${type} position-fixed bottom-0 end-0 m-3 shadow rounded-3`;
  t.style.cssText = "z-index:99999;min-width:260px;font-size:0.9rem;";
  t.innerText = msg;
  document.body.appendChild(t);
  setTimeout(() => {
    t.style.transition = "opacity 0.4s";
    t.style.opacity    = "0";
    setTimeout(() => t.remove(), 400);
  }, 2800);
}