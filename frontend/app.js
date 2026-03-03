/**
 * LinguaBridge – frontend audio setup (PR 1 + PR 2 + PR 3)
 *
 * PR 1 responsibilities:
 *  1. Request microphone permission via getUserMedia
 *  2. Enumerate audio input / output devices
 *  3. Allow the user to switch the audio output device (setSinkId)
 *
 * PR 2 additions:
 *  4. Open a WebSocket connection to the FastAPI backend
 *  5. Stream raw mic audio chunks to the backend in real-time
 *  6. Display live debug counters (chunks sent, bytes sent)
 *
 * PR 3 additions:
 *  7. Language selector (EN / DE) passed to the backend as ?lang=
 *  8. Display live transcripts sent back by the backend (partial + final)
 *
 * No translation or TTS yet – that comes in a later PR.
 */

// Global handle to the active MediaStream.
// Stored here so future PRs can pipe it to the backend for transcription.
// To release the mic, call: activeStream.getTracks().forEach(t => t.stop())
let activeStream = null;

// WebSocket and MediaRecorder used for audio streaming (PR 2)
let socket        = null;   // the WebSocket connection
let mediaRecorder = null;   // records mic audio and fires ondataavailable

// Generation counter — incremented each time a new connection is started.
// Every event handler captures its own generation at creation time so that
// stale handlers from a previous (failed/closed) socket are discarded even
// if they fire after a new connection has already been initiated.
let wsGeneration = 0;

// Running counters shown in the UI
let chunksSent  = 0;
let bytesSent   = 0;

// ─── DOM references ─────────────────────────────────────────────────────────
const btnMic        = document.getElementById("btn-mic");
const statusEl      = document.getElementById("status");
const selectInput   = document.getElementById("select-input");
const selectOutput  = document.getElementById("select-output");
const sinkSupportMsg = document.getElementById("sink-support-msg");

const btnStart          = document.getElementById("btn-start");
const btnStop           = document.getElementById("btn-stop");
const wsStatusEl        = document.getElementById("ws-status");
const streamStatusEl    = document.getElementById("stream-status");
const cntChunks         = document.getElementById("cnt-chunks");
const cntBytes          = document.getElementById("cnt-bytes");
const selectLang        = document.getElementById("select-lang");

// Transcript display elements (PR 3)
const transcriptFinalEl   = document.getElementById("transcript-final");
const transcriptInterimEl = document.getElementById("transcript-interim");
const transcriptPlaceholder = document.getElementById("transcript-placeholder");

// Accumulated final-transcript text for the current session.
let finalTranscript = "";

// ─── Microphone permission ───────────────────────────────────────────────────

/**
 * Called when the user clicks "Enable Microphone".
 * Asks the browser for mic access, then populates the device dropdowns.
 */
async function enableMicrophone() {
  setStatus("waiting", "Mic: requesting permission…");
  btnMic.disabled = true;

  try {
    // Request audio-only access. The browser will show its native permission
    // dialog if this is the first time.
    activeStream = await navigator.mediaDevices.getUserMedia({ audio: true });

    setStatus("granted", "Mic: granted ✓");

    // Now that the user has granted access we can enumerate real device labels.
    await populateDevices();

    // Enable the Start Streaming button now that we have a mic stream
    btnStart.disabled = false;
  } catch (err) {
    // The user denied the request, or the device is unavailable.
    setStatus("denied", `Mic: denied – ${err.message}`);
    btnMic.disabled = false; // Let them try again
  }
}

btnMic.addEventListener("click", enableMicrophone);

// ─── Device enumeration ──────────────────────────────────────────────────────

/**
 * Reads all available media devices and populates the two dropdowns.
 * Must be called *after* getUserMedia so device labels are visible.
 */
async function populateDevices() {
  const devices = await navigator.mediaDevices.enumerateDevices();

  const inputs  = devices.filter(d => d.kind === "audioinput");
  const outputs = devices.filter(d => d.kind === "audiooutput");

  populateSelect(selectInput,  inputs,  "input");
  populateSelect(selectOutput, outputs, "output");

  // Show a note if setSinkId is not supported (e.g. Firefox)
  if (typeof HTMLAudioElement.prototype.setSinkId === "undefined") {
    sinkSupportMsg.textContent =
      "ℹ️ Your browser does not support output device selection (setSinkId). " +
      "Try Chrome or Edge.";
  }
}

/**
 * Fills a <select> element with a list of MediaDeviceInfo objects.
 *
 * @param {HTMLSelectElement} selectEl  - The dropdown to populate
 * @param {MediaDeviceInfo[]} deviceList - Filtered list of devices
 * @param {string}            type      - "input" or "output" (for fallback labels)
 */
function populateSelect(selectEl, deviceList, type) {
  // Remove old options
  selectEl.innerHTML = "";

  if (deviceList.length === 0) {
    const opt = document.createElement("option");
    opt.textContent = `No ${type} devices found`;
    selectEl.appendChild(opt);
    return;
  }

  deviceList.forEach((device, index) => {
    const opt = document.createElement("option");
    opt.value = device.deviceId;
    // Device labels are only available after permission is granted.
    opt.textContent = device.label || `${type} device ${index + 1}`;
    selectEl.appendChild(opt);
  });
}

// ─── Output device switching ─────────────────────────────────────────────────

/**
 * When the user picks a different output device, route future audio there.
 * HTMLAudioElement.setSinkId() is used to redirect audio output.
 */
selectOutput.addEventListener("change", async () => {
  const deviceId = selectOutput.value;
  if (!deviceId) return;

  // setSinkId is only supported in Chrome / Edge (and Chromium-based browsers).
  if (typeof HTMLAudioElement.prototype.setSinkId === "undefined") {
    sinkSupportMsg.textContent =
      "⚠️ Output device switching is not supported in this browser.";
    return;
  }

  try {
    // Create a silent audio element just to test that setSinkId works.
    // In a later PR this element will be replaced by the TTS output player.
    const testAudio = new Audio();
    await testAudio.setSinkId(deviceId);
    sinkSupportMsg.textContent = `✓ Output switched to: ${selectOutput.options[selectOutput.selectedIndex].text}`;
  } catch (err) {
    sinkSupportMsg.textContent = `⚠️ Could not switch output device: ${err.message}`;
  }
});

// ─── WebSocket URL helper ────────────────────────────────────────────────────

/**
 * Builds the WebSocket URL for the backend, including the language parameter.
 *
 * - On localhost  → ws://localhost:8000/ws/audio?lang=en
 * - In Codespaces → wss://<codespace-name>-8000.app.github.dev/ws/audio?lang=en
 *   (GitHub Codespaces forwards each port as its own subdomain; we swap
 *   the frontend port in the hostname for the backend port 8000)
 *
 * @param {string} lang - "en" or "de"
 * @returns {string} The full WebSocket URL to connect to.
 */
function buildWsUrl(lang = "en") {
  const host     = window.location.hostname;
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const query    = `?lang=${encodeURIComponent(lang)}`;

  // Local development
  if (host === "localhost" || host === "127.0.0.1") {
    return `ws://localhost:8000/ws/audio${query}`;
  }

  // GitHub Codespaces — replace the frontend port number in the subdomain
  // with the backend port (8000).  The frontend is typically served on port
  // 3000, producing a hostname like "<name>-3000.app.github.dev".
  const wsHost = host.replace(/(-\d+)(\.app\.github\.dev)$/, "-8000$2");
  return `${protocol}//${wsHost}/ws/audio${query}`;
}

// ─── Transcript display (PR 3) ───────────────────────────────────────────────

/**
 * Called each time the backend forwards a Deepgram transcript event.
 *
 * Deepgram sends two kinds of results:
 *  - Interim (is_final = false): words recognised so far; may change.
 *    → shown in grey/italic as the user speaks.
 *  - Final   (is_final = true):  a stable chunk of speech.
 *    → appended to the permanent transcript in black text.
 *
 * @param {{ type: string, text: string, is_final: boolean }} msg
 */
function handleTranscript(msg) {
  // Hide the placeholder hint once we get real text.
  transcriptPlaceholder.style.display = "none";

  if (msg.is_final) {
    // Append the finalised text (add a space separator if needed).
    if (finalTranscript && !finalTranscript.endsWith(" ")) {
      finalTranscript += " ";
    }
    finalTranscript += msg.text;
    transcriptFinalEl.textContent   = finalTranscript + " ";
    transcriptInterimEl.textContent = "";
  } else {
    // Show the partial recognition in italics beside the stable text.
    transcriptInterimEl.textContent = msg.text;
  }
}

// ─── Streaming (PR 2) ────────────────────────────────────────────────────────

/**
 * Opens the WebSocket connection and starts the MediaRecorder.
 * Called when the user clicks "Start Streaming".
 */
function startStreaming() {
  if (!activeStream) {
    alert("Please enable the microphone first.");
    return;
  }

  // Reset counters
  chunksSent = 0;
  bytesSent  = 0;
  updateCounters();

  // Reset transcript display for the new session.
  finalTranscript = "";
  transcriptFinalEl.textContent   = "";
  transcriptFinalEl.style.color   = "";
  transcriptInterimEl.textContent = "";
  transcriptPlaceholder.style.display = "none";

  // Read the selected language and append it as a query parameter so the
  // backend knows which language to tell Deepgram to transcribe.
  const wsUrl = buildWsUrl(selectLang ? selectLang.value : "en");
  setWsStatus("waiting", `WS: connecting to ${wsUrl}…`);

  // Stamp this connection attempt; stale handlers from the previous socket
  // will see a different generation and exit early.
  wsGeneration++;
  const myGen = wsGeneration;

  socket = new WebSocket(wsUrl);
  socket.binaryType = "arraybuffer";

  socket.addEventListener("open", () => {
    if (wsGeneration !== myGen) return;
    setWsStatus("granted", "WS: connected ✓");
    startMediaRecorder();
    btnStart.disabled = true;
    btnStop.disabled  = false;
  });

  socket.addEventListener("close", () => {
    if (wsGeneration !== myGen) return;
    setWsStatus("waiting", "WS: disconnected");
    stopMediaRecorder();
    btnStart.disabled = false;
    btnStop.disabled  = true;
  });

  socket.addEventListener("error", () => {
    if (wsGeneration !== myGen) return;
    setWsStatus("denied", "WS: error — check backend is running");
    stopMediaRecorder();
    btnStart.disabled = false;
    btnStop.disabled  = true;
  });

  // Handle messages sent back by the backend (transcripts from Deepgram)
  socket.addEventListener("message", (event) => {
    if (wsGeneration !== myGen) return;
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "transcript") {
        handleTranscript(msg);
      } else if (msg.type === "error") {
        // Show backend errors (e.g. missing API key) in the transcript panel
        transcriptPlaceholder.style.display = "none";
        transcriptInterimEl.textContent = "";
        transcriptFinalEl.textContent   = msg.message || "Unknown server error";
        transcriptFinalEl.style.color   = "#b00020";
      }
    } catch (err) {
      console.warn("Failed to parse WebSocket message:", err);
    }
  });
}

/**
 * Creates and starts a MediaRecorder that fires every 250 ms.
 * Each audio chunk (a Blob) is sent to the backend as binary data.
 */
function startMediaRecorder() {
  mediaRecorder = new MediaRecorder(activeStream);

  mediaRecorder.addEventListener("dataavailable", async (event) => {
    if (!event.data || event.data.size === 0) return;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;

    // Convert the Blob to an ArrayBuffer so we can send raw bytes
    const buffer = await event.data.arrayBuffer();
    socket.send(buffer);

    chunksSent++;
    bytesSent += buffer.byteLength;
    updateCounters();
  });

  // timeslice = 250 ms → we get a chunk four times per second
  mediaRecorder.start(250);
  setStreamStatus("granted", "Streaming: on 🔴");
}

/**
 * Stops the MediaRecorder if it is currently recording.
 */
function stopMediaRecorder() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }
  mediaRecorder = null;
  setStreamStatus("waiting", "Streaming: off");
}

/**
 * Closes the WebSocket and stops the MediaRecorder.
 * Called when the user clicks "Stop Streaming".
 */
function stopStreaming() {
  wsGeneration++;   // invalidate any pending close/error handlers from the current socket
  stopMediaRecorder();
  if (socket) {
    socket.close();
    socket = null;
  }
  setWsStatus("waiting", "WS: disconnected");
  btnStart.disabled = false;
  btnStop.disabled  = true;

  // Clear the interim text; keep the final transcript visible.
  transcriptInterimEl.textContent = "";
  if (!finalTranscript) {
    transcriptPlaceholder.style.display = "";
  }
}

btnStart.addEventListener("click", startStreaming);
btnStop.addEventListener("click",  stopStreaming);

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Updates the status indicator element.
 *
 * @param {"granted"|"denied"|"waiting"} state
 * @param {string} message
 */
function setStatus(state, message) {
  statusEl.className = `status-${state}`;
  statusEl.textContent = message;
}

/** Updates the WebSocket status badge. */
function setWsStatus(state, message) {
  wsStatusEl.className = `status-${state}`;
  wsStatusEl.textContent = message;
}

/** Updates the Streaming on/off badge. */
function setStreamStatus(state, message) {
  streamStatusEl.className = `status-${state}`;
  streamStatusEl.textContent = message;
}

/** Refreshes the chunks/bytes counters in the UI. */
function updateCounters() {
  cntChunks.textContent = chunksSent;
  cntBytes.textContent  = bytesSent;
}
