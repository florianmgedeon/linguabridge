/**
 * LinguaBridge – frontend audio setup (PR 1)
 *
 * Responsibilities:
 *  1. Request microphone permission via getUserMedia
 *  2. Enumerate audio input / output devices
 *  3. Allow the user to switch the audio output device (setSinkId)
 *
 * No translation or AI logic yet – that comes in a later PR.
 */

// Global handle to the active MediaStream.
// Stored here so future PRs can pipe it to the backend for transcription.
// To release the mic, call: activeStream.getTracks().forEach(t => t.stop())
let activeStream = null;

// ─── DOM references ─────────────────────────────────────────────────────────
const btnMic        = document.getElementById("btn-mic");
const statusEl      = document.getElementById("status");
const selectInput   = document.getElementById("select-input");
const selectOutput  = document.getElementById("select-output");
const sinkSupportMsg = document.getElementById("sink-support-msg");

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
