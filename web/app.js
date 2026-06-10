const statusEl = document.getElementById("status");
const conversationEl = document.getElementById("conversation");
const recordBtn = document.getElementById("recordBtn");
const recordLabel = document.getElementById("recordLabel");
const resetBtn = document.getElementById("resetBtn");

let sessionId = window.crypto?.randomUUID?.() || String(Date.now());
let stream = null;
let recorder = null;
let chunks = [];
let busy = false;

function setStatus(text) {
  statusEl.textContent = text;
}

function addMessage(role, text) {
  const item = document.createElement("article");
  item.className = `message ${role}`;
  item.textContent = text;
  conversationEl.appendChild(item);
  conversationEl.scrollTop = conversationEl.scrollHeight;
}

function pickMimeType() {
  const options = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm"];
  return options.find((type) => window.MediaRecorder?.isTypeSupported?.(type)) || "";
}

async function startRecording() {
  stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  chunks = [];
  const mimeType = pickMimeType();
  recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  recorder.ondataavailable = (event) => {
    if (event.data.size > 0) chunks.push(event.data);
  };
  recorder.start();
  recordBtn.classList.add("recording");
  recordLabel.textContent = "Stop";
  setStatus("Listening");
}

async function stopRecording() {
  if (!recorder) return;
  busy = true;
  recordBtn.disabled = true;
  setStatus("Thinking");

  const stopped = new Promise((resolve) => {
    recorder.onstop = resolve;
  });
  recorder.stop();
  await stopped;

  stream?.getTracks().forEach((track) => track.stop());
  stream = null;

  const mimeType = recorder.mimeType || "audio/webm";
  const extension = mimeType.includes("mp4") ? "m4a" : "webm";
  const blob = new Blob(chunks, { type: mimeType });
  recorder = null;
  chunks = [];
  recordBtn.classList.remove("recording");
  recordLabel.textContent = "Start";

  await sendAudio(blob, extension);
  recordBtn.disabled = false;
  busy = false;
}

async function sendAudio(blob, extension) {
  const form = new FormData();
  form.append("session_id", sessionId);
  form.append("audio", blob, `speech.${extension}`);

  const response = await fetch("/api/voice", {
    method: "POST",
    body: form,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }

  const payload = await response.json();
  sessionId = payload.session_id || sessionId;
  addMessage("user", payload.transcript);
  addMessage("kimi", payload.reply);
  if (payload.timing?.total_seconds) {
    setStatus(`Speaking · ${payload.timing.total_seconds}s`);
  } else {
    setStatus("Speaking");
  }

  const audio = new Audio(`data:audio/wav;base64,${payload.audio_base64}`);
  await audio.play();
  audio.onended = () => setStatus("Ready");
}

recordBtn.addEventListener("click", async () => {
  if (busy) return;
  try {
    if (recorder && recorder.state === "recording") {
      await stopRecording();
    } else {
      await startRecording();
    }
  } catch (error) {
    recordBtn.disabled = false;
    recordBtn.classList.remove("recording");
    recordLabel.textContent = "Start";
    busy = false;
    setStatus("Ready");
    addMessage("error", error.message || String(error));
  }
});

resetBtn.addEventListener("click", () => {
  sessionId = window.crypto?.randomUUID?.() || String(Date.now());
  conversationEl.innerHTML = "";
  setStatus("Ready");
});
