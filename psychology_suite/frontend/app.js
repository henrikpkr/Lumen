const loginForm = document.querySelector("#login-form");
const API_BASE = window.location.port === "8010" ? "" : "http://127.0.0.1:8010";

function apiUrl(path) {
  if (path.startsWith("http")) return path;
  return `${API_BASE}${path}`;
}
const loginError = document.querySelector("#login-error");
const logoutBtn = document.querySelector("#logout-btn");
const profileName = document.querySelector("#profile-name");
const profileEmail = document.querySelector("#profile-email");
const refreshBtn = document.querySelector("#refresh-btn");
const patientForm = document.querySelector("#patient-form");
const patientList = document.querySelectorAll("#patient-list");
const patientDetailPanel = document.querySelector("#patient-detail-panel");
const patientDetailEmpty = document.querySelector("#patient-detail-empty");
const patientDetailBody = document.querySelector("#patient-detail-body");
const patientDetailForm = document.querySelector("#patient-detail-form");
const patientUpdateBtn = document.querySelector("#patient-update-btn");
const patientArchiveBtn = document.querySelector("#patient-archive-btn");
const patientDeleteBtn = document.querySelector("#patient-delete-btn");
const patientSessionList = document.querySelector("#patient-session-list");
const patientSessionEmpty = document.querySelector("#patient-session-empty");
const patientSessionDetail = document.querySelector("#patient-session-detail");
const patientSessionDetailEmpty = document.querySelector("#patient-session-detail-empty");
const patientSessionForm = document.querySelector("#patient-session-form");
const patientSessionSaveBtn = document.querySelector("#patient-session-save-btn");
const patientSessionArchiveBtn = document.querySelector("#patient-session-archive-btn");
const patientSessionDeleteBtn = document.querySelector("#patient-session-delete-btn");
const patientSessionTranscript = document.querySelector("#patient-session-transcript");
const patientSessionNote = document.querySelector("#patient-session-note");
const sessionForm = document.querySelector("#session-form");
const sessionList = document.querySelector("#session-list");
const transcribeForm = document.querySelector("#transcribe-form");
const transcriptPanel = document.querySelector("#transcript-panel");
const summarizeForm = document.querySelector("#summarize-form");
const noteBox = document.querySelector("#note-box");
const saveNoteBtn = document.querySelector("#save-note-btn");

let selectedPatientId = null;
let selectedSessionId = null;

async function api(path, options = {}) {
  const response = await fetch(apiUrl(path), options);
  const text = await response.text();
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }
  if (!response.ok) {
    const error = new Error(data.detail || "Request failed");
    error.status = response.status;
    throw error;
  }
  return data;
}

async function ensureAuth() {
  try {
    const me = await api("/me");
    return me;
  } catch {
    if (!loginForm) {
      window.location.href = `${API_BASE}/login`;
    }
    return null;
  }
}

async function loadProfile() {
  const me = await ensureAuth();
  if (!me) return;
  if (profileName) profileName.textContent = me.name;
  if (profileEmail) profileEmail.textContent = me.email;
  await loadPatients();
}

async function loadPatients() {
  const data = await api("/patients");
  patientList.forEach((list) => {
    list.innerHTML = "";
    (data.patients || []).forEach((patient) => {
      const item = document.createElement("div");
      item.className = "list-item";
      if (patient.id === selectedPatientId) {
        item.classList.add("is-selected");
      }
      item.innerHTML = `
        <strong>${patient.display_name}</strong>
        <div class="meta">${patient.contact_email || ""} ${patient.contact_phone || ""}</div>
        <div class="meta">ID: ${patient.id}</div>
        <div class="meta">Status: ${patient.active ? "Active" : "Archived"}</div>
      `;
      if (patientDetailPanel) {
        item.classList.add("is-clickable");
        item.addEventListener("click", () => {
          selectPatient(patient.id);
        });
      }
      list.appendChild(item);
    });
  });
}

function formatDateTime(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

async function selectPatient(patientId) {
  selectedPatientId = patientId;
  selectedSessionId = null;
  await loadPatients();
  await loadPatientDetail(patientId);
  await loadPatientSessions(patientId);
  if (patientSessionDetail) {
    patientSessionDetail.hidden = true;
  }
  if (patientSessionDetailEmpty) {
    patientSessionDetailEmpty.hidden = false;
  }
}

async function loadPatientDetail(patientId) {
  if (!patientDetailPanel) return;
  const data = await api(`/patients/${encodeURIComponent(patientId)}`);
  const patient = data.patient;
  if (!patient) return;
  if (patientDetailEmpty) patientDetailEmpty.hidden = true;
  if (patientDetailBody) patientDetailBody.hidden = false;
  if (patientDetailForm) {
    patientDetailForm.elements.patient_id.value = patient.id;
    patientDetailForm.elements.display_name.value = patient.display_name || "";
    patientDetailForm.elements.date_of_birth.value = patient.date_of_birth || "";
    patientDetailForm.elements.contact_email.value = patient.contact_email || "";
    patientDetailForm.elements.contact_phone.value = patient.contact_phone || "";
    patientDetailForm.elements.notes.value = patient.notes || "";
    patientDetailForm.elements.active.value = patient.active ? "true" : "false";
  }
  if (patientArchiveBtn) {
    patientArchiveBtn.textContent = patient.active ? "Archive patient" : "Restore patient";
  }
}

async function loadPatientSessions(patientId) {
  if (!patientSessionList) return;
  const data = await api(`/sessions?patient_id=${encodeURIComponent(patientId)}`);
  patientSessionList.innerHTML = "";
  const sessions = data.sessions || [];
  if (patientSessionEmpty) {
    patientSessionEmpty.hidden = sessions.length > 0;
  }
  sessions.forEach((session) => {
    const item = document.createElement("div");
    item.className = "list-item is-clickable";
    if (session.id === selectedSessionId) {
      item.classList.add("is-selected");
    }
    item.innerHTML = `
      <strong>Session ${session.id}</strong>
      <div class="meta">Date: ${formatDateTime(session.started_at)}</div>
      <div class="meta">Status: ${session.status}</div>
      <div class="meta">Transcript: ${session.transcript_text ? "yes" : "no"} · SOAP: ${session.note_text ? "yes" : "no"}</div>
    `;
    item.addEventListener("click", () => {
      selectSession(session.id);
    });
    patientSessionList.appendChild(item);
  });
}

async function selectSession(sessionId) {
  selectedSessionId = sessionId;
  await loadPatientSessions(selectedPatientId);
  await loadSessionDetail(sessionId);
}

async function loadSessionDetail(sessionId) {
  if (!patientSessionDetail) return;
  const data = await api(`/sessions/${encodeURIComponent(sessionId)}`);
  const session = data.session;
  if (!session) return;
  if (patientSessionDetailEmpty) patientSessionDetailEmpty.hidden = true;
  patientSessionDetail.hidden = false;
  if (patientSessionForm) {
    patientSessionForm.elements.session_id.value = session.id;
    patientSessionForm.elements.status.value = session.status || "draft";
    patientSessionForm.elements.started_at.value = formatDateTime(session.started_at);
    patientSessionForm.elements.note_format.value = session.note_format || "soap";
    patientSessionForm.elements.transcript_confirmed.value = session.transcript_confirmed ? "Yes" : "No";
    patientSessionForm.elements.low_confidence.value = session.low_confidence ? "Yes" : "No";
  }
  if (patientSessionTranscript) {
    patientSessionTranscript.value = session.transcript_text || "";
  }
  if (patientSessionNote) {
    patientSessionNote.value = session.note_text || "";
  }
}

async function loadSessions() {
  if (!sessionList) return;
  const data = await api("/sessions");
  sessionList.innerHTML = "";
  (data.sessions || []).forEach((session) => {
    const item = document.createElement("div");
    item.className = "list-item";
    item.innerHTML = `
      <strong>Session ${session.id}</strong>
      <div class="meta">Patient: ${session.patient_id}</div>
      <div class="meta">Status: ${session.status}</div>
      <div class="meta">Low confidence: ${session.low_confidence ? "yes" : "no"}</div>
    `;
    sessionList.appendChild(item);
  });
}

if (loginForm) {
  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    loginError.hidden = true;
    const formData = new FormData(loginForm);
    try {
      await api("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.fromEntries(formData.entries())),
      });
      window.location.href = `${API_BASE}/profile`;
    } catch (error) {
      loginError.textContent = error.message || "Login failed";
      loginError.hidden = false;
    }
  });
}

if (logoutBtn) {
  logoutBtn.addEventListener("click", async () => {
    await api("/auth/logout", { method: "POST" });
    window.location.href = `${API_BASE}/login`;
  });
}

if (refreshBtn) {
  refreshBtn.addEventListener("click", loadProfile);
}

if (patientForm) {
  patientForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(patientForm);
    await api("/patients", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.fromEntries(formData.entries())),
    });
    patientForm.reset();
    await loadPatients();
  });
}

if (patientUpdateBtn) {
  patientUpdateBtn.addEventListener("click", async () => {
    if (!patientDetailForm) return;
    const formData = new FormData(patientDetailForm);
    const patientId = formData.get("patient_id");
    if (!patientId) return;
    const payload = Object.fromEntries(formData.entries());
    delete payload.patient_id;
    payload.active = payload.active === "true";
    await api(`/patients/${encodeURIComponent(patientId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    await loadPatients();
    await loadPatientDetail(patientId);
  });
}

if (patientArchiveBtn) {
  patientArchiveBtn.addEventListener("click", async () => {
    if (!patientDetailForm) return;
    const patientId = patientDetailForm.elements.patient_id.value;
    if (!patientId) return;
    const currentActive = patientDetailForm.elements.active.value === "true";
    await api(`/patients/${encodeURIComponent(patientId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active: !currentActive }),
    });
    await loadPatients();
    await loadPatientDetail(patientId);
  });
}

if (patientDeleteBtn) {
  patientDeleteBtn.addEventListener("click", async () => {
    if (!patientDetailForm) return;
    const patientId = patientDetailForm.elements.patient_id.value;
    if (!patientId) return;
    const confirmed = window.confirm("Delete this patient and all sessions? This cannot be undone.");
    if (!confirmed) return;
    await api(`/patients/${encodeURIComponent(patientId)}`, {
      method: "DELETE",
    });
    selectedPatientId = null;
    selectedSessionId = null;
    if (patientDetailBody) patientDetailBody.hidden = true;
    if (patientDetailEmpty) patientDetailEmpty.hidden = false;
    if (patientSessionDetail) patientSessionDetail.hidden = true;
    if (patientSessionDetailEmpty) patientSessionDetailEmpty.hidden = false;
    if (patientSessionList) patientSessionList.innerHTML = "";
    if (patientSessionEmpty) patientSessionEmpty.hidden = false;
    await loadPatients();
  });
}

if (sessionForm) {
  sessionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(sessionForm);
    await api("/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.fromEntries(formData.entries())),
    });
    sessionForm.reset();
    await loadSessions();
  });
}

if (transcribeForm) {
  transcribeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(transcribeForm);
    const sessionId = formData.get("session_id");
    const audioFile = formData.get("audio");
    const payload = new FormData();
    payload.append("audio", audioFile);
    const response = await fetch(apiUrl(`/api/transcribe?session_id=${encodeURIComponent(sessionId)}`), {
      method: "POST",
      body: payload,
    });
    const data = await response.json();
    if (!response.ok) {
      window.alert(data.detail || "Transcription failed");
      return;
    }
    transcriptPanel.innerHTML = "";
    const warning = data.low_confidence
      ? "Low confidence detected. Please review transcript before summarizing."
      : "Transcription complete.";
    transcriptPanel.innerHTML = `
      <div class="list-item">
        <strong>${warning}</strong>
        <p class="meta">${data.transcript}</p>
      </div>
    `;
    await loadSessions();
  });
}

if (summarizeForm) {
  summarizeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(summarizeForm);
    const sessionId = formData.get("session_id");
    const confirmed = formData.get("transcript_confirmed") === "true";
    if (confirmed) {
    await api(`/sessions/${encodeURIComponent(sessionId)}/confirm-transcript`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmed: true }),
    });
    }
    const data = await api("/api/summarize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    });
    if (noteBox) noteBox.value = data.final_note || "";
  });
}

if (saveNoteBtn) {
  saveNoteBtn.addEventListener("click", async () => {
    const sessionId = document.querySelector("#summarize-form [name='session_id']")?.value;
    if (!sessionId) return;
    await api(`/api/sessions/${encodeURIComponent(sessionId)}/note`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note_text: noteBox.value, status: "draft" }),
    });
    await loadSessions();
  });
}

if (patientSessionSaveBtn) {
  patientSessionSaveBtn.addEventListener("click", async () => {
    if (!patientSessionForm) return;
    const formData = new FormData(patientSessionForm);
    const sessionId = formData.get("session_id");
    if (!sessionId) return;
    const payload = {
      status: formData.get("status"),
      note_format: formData.get("note_format"),
    };
    await api(`/sessions/${encodeURIComponent(sessionId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (patientSessionNote) {
      await api(`/api/sessions/${encodeURIComponent(sessionId)}/note`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note_text: patientSessionNote.value, status: payload.status }),
      });
    }
    await loadPatientSessions(selectedPatientId);
    await loadSessionDetail(sessionId);
  });
}

if (patientSessionArchiveBtn) {
  patientSessionArchiveBtn.addEventListener("click", async () => {
    if (!patientSessionForm) return;
    const sessionId = patientSessionForm.elements.session_id.value;
    if (!sessionId) return;
    await api(`/sessions/${encodeURIComponent(sessionId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "archived" }),
    });
    await loadPatientSessions(selectedPatientId);
    await loadSessionDetail(sessionId);
  });
}

if (patientSessionDeleteBtn) {
  patientSessionDeleteBtn.addEventListener("click", async () => {
    if (!patientSessionForm) return;
    const sessionId = patientSessionForm.elements.session_id.value;
    if (!sessionId) return;
    const confirmed = window.confirm("Delete this session? This cannot be undone.");
    if (!confirmed) return;
    await api(`/sessions/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    });
    selectedSessionId = null;
    if (patientSessionDetail) patientSessionDetail.hidden = true;
    if (patientSessionDetailEmpty) patientSessionDetailEmpty.hidden = false;
    await loadPatientSessions(selectedPatientId);
  });
}

if (profileName) {
  loadProfile();
}

if (sessionList) {
  ensureAuth().then(loadSessions);
}

if (patientForm) {
  ensureAuth().then(loadPatients);
}
