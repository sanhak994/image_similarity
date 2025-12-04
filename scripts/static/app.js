const progressEl = document.getElementById("progress");
const pairMetaEl = document.getElementById("pair-meta");
const infoEl = document.getElementById("info");

const stepButtons = document.querySelectorAll(".step-button");
let currentStep = "setup";
const jumpInput = document.getElementById("jump-index");
const jumpButton = document.getElementById("jump-button");

const leftLib = document.getElementById("left-library");
const leftFile = document.getElementById("left-filename");
const leftUuid = document.getElementById("left-uuid");
const leftImg = document.getElementById("left-image");

const rightLib = document.getElementById("right-library");
const rightFile = document.getElementById("right-filename");
const rightUuid = document.getElementById("right-uuid");
const rightImg = document.getElementById("right-image");

const btnKeepLeft = document.getElementById("keep-left");
const btnKeepRight = document.getElementById("keep-right");
const btnKeepBoth = document.getElementById("keep-both");
const btnDeleteBoth = document.getElementById("delete-both");
const btnKeepPrimary = document.getElementById("keep-primary");
const btnSkip = document.getElementById("skip");
const btnPrev = document.getElementById("prev");

const primarySelect = document.getElementById("primary-select");
const savePrimary = document.getElementById("save-primary");
const extraExportMissing = document.getElementById("extra-export-missing");
const extraExportKeepers = document.getElementById("extra-export-keepers");
const extraExportSrc = document.getElementById("extra-export-src");
const extraExportOther = document.getElementById("extra-export-other");
const extraExportDest = document.getElementById("extra-export-dest");
const extraBatchToggle = document.getElementById("extra-batch-toggle");
const extraBatchStatus = document.getElementById("extra-batch-status");
const extraLogMain = document.getElementById("extra-log-main");

const scanPhotosLib = document.getElementById("scan-photos-lib");
const scanIphotoLib = document.getElementById("scan-iphoto-lib");
const scanHashMethod = document.getElementById("scan-hash-method");
const scanHashSize = document.getElementById("scan-hash-size");
const scanThrDupes = document.getElementById("scan-thr-dupes");
const scanThrCross = document.getElementById("scan-thr-cross");
const scanWorkers = document.getElementById("scan-workers");
const scanPreferEdited = document.getElementById("scan-prefer-edited");
const startScan = document.getElementById("start-scan");
const scanProgress = document.getElementById("scan-progress");
const scanLog = document.getElementById("scan-log");

const statsProgress = document.getElementById("progress");
const statsMeta = document.getElementById("pair-meta");

const albumName = document.getElementById("album-name");
const albumDryRun = document.getElementById("album-dry-run");
const startAlbum = document.getElementById("start-album");
const albumProgress = document.getElementById("album-progress");
const albumLog = document.getElementById("album-log");

let scanTaskId = null;
let albumTaskId = null;

let pairs = [];
let index = 0;

function showStep(step) {
  currentStep = step;
  document.querySelectorAll(".step").forEach((el) => {
    el.classList.toggle("hidden", el.dataset.step !== step);
  });
  stepButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.step === step);
  });
  if (step === "review" && pairs.length === 0) {
    loadPairs();
  }
}

stepButtons.forEach((btn) => {
  btn.addEventListener("click", () => showStep(btn.dataset.step));
});

function updateUI() {
  if (!pairs.length) return;
  const pair = pairs[index];
  progressEl.textContent = `${index + 1} / ${pairs.length}`;
  pairMetaEl.textContent = `${pair.pair_type} • dist ${pair.distance} • ${pair.hash_method}`;

  leftLib.textContent = pair.left.library;
  leftFile.textContent = pair.left.filename;
  leftUuid.textContent = pair.left.uuid;
  leftImg.src = pair.left.url;
  leftImg.alt = pair.left.path;
  leftImg.classList.toggle("missing", !pair.left.exists);

  rightLib.textContent = pair.right.library;
  rightFile.textContent = pair.right.filename;
  rightUuid.textContent = pair.right.uuid;
  rightImg.src = pair.right.url;
  rightImg.alt = pair.right.path;
  rightImg.classList.toggle("missing", !pair.right.exists);

  if (pair.decision) {
    infoEl.textContent = `Decision saved: ${pair.decision}`;
  } else {
    infoEl.textContent = "No decision yet.";
  }
}

async function loadPairs() {
  const res = await fetch("/api/pairs");
  const data = await res.json();
  pairs = data.pairs;
  index = pairs.findIndex((p) => !p.decision);
  if (index === -1) index = 0;
  if (pairs.length) {
    statsProgress.textContent = `${index + 1} / ${pairs.length}`;
    statsMeta.textContent = `${pairs[index].pair_type} • dist ${pairs[index].distance} • ${pairs[index].hash_method}`;
  }
  updateUI();
}

async function sendDecision(decision) {
  const pair = pairs[index];
  if (!pair) return;
  const res = await fetch("/api/decision", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pair_id: pair.pair_id, decision }),
  });
  if (!res.ok) {
    infoEl.textContent = "Failed to save decision.";
    return;
  }
  const data = await res.json();
  pairs[index] = data.pair;
  infoEl.textContent = `Decision saved: ${decision}`;
  goNext();
}

function goNext() {
  if (index < pairs.length - 1) {
    index += 1;
    updateUI();
  }
}

function goPrev() {
  if (index > 0) {
    index -= 1;
    updateUI();
  }
}

function jumpTo(idx) {
  if (!pairs.length) return;
  const clamped = Math.max(0, Math.min(pairs.length - 1, idx - 1));
  index = clamped;
  updateUI();
}

jumpButton?.addEventListener("click", () => {
  const val = parseInt(jumpInput.value, 10);
  if (!isNaN(val)) jumpTo(val);
});

btnKeepLeft.onclick = () => sendDecision("keep_left");
btnKeepRight.onclick = () => sendDecision("keep_right");
btnKeepBoth.onclick = () => sendDecision("keep_both");
btnDeleteBoth.onclick = () => sendDecision("delete_both");
btnKeepPrimary.onclick = () => sendDecision("keep_primary");
btnSkip.onclick = () => sendDecision("skip");
btnPrev.onclick = () => goPrev();

document.addEventListener("keydown", (e) => {
  if (e.key === "l" || e.key === "L") sendDecision("keep_left");
  if (e.key === "r" || e.key === "R") sendDecision("keep_right");
  if (e.key === "b" || e.key === "B") sendDecision("keep_both");
  if (e.key === "d" || e.key === "D") sendDecision("delete_both");
  if (e.key === "k" || e.key === "K") sendDecision("keep_primary");
  if (e.key === "n" || e.key === "N" || e.key === "s" || e.key === "S") sendDecision("skip");
  if (e.key === "p" || e.key === "P" || e.key === "ArrowLeft") goPrev();
  if (e.key === "ArrowRight") goNext();
});

// Debug hook: ensure startScan is bound
window.__debugStartScanBound = !!startScan;

leftImg.onload = () => leftImg.classList.remove("missing");
leftImg.onerror = () => leftImg.classList.add("missing");
rightImg.onload = () => rightImg.classList.remove("missing");
rightImg.onerror = () => rightImg.classList.add("missing");

async function loadSettings() {
  const res = await fetch("/api/settings");
  const data = await res.json();
  primarySelect.value = data.primary_library || "photos";
}

savePrimary.onclick = async () => {
  const res = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ primary_library: primarySelect.value }),
  });
  if (res.ok) {
    batchStatus.textContent = `Primary set to ${primarySelect.value}`;
  } else {
    batchStatus.textContent = "Failed to save primary.";
  }
};

async function pollTask(taskId, logEl, progressEl) {
  progressEl.hidden = false;
  const interval = setInterval(async () => {
    const res = await fetch(`/api/task/status?task_id=${taskId}`);
    if (!res.ok) return;
    const data = await res.json();
    const lines = (data.output || "").trim().split("\n").filter(Boolean);
    const filtered = lines.filter((line) => !/^PROGRESS\s+\d+\/\d+/i.test(line));
    logEl.textContent = filtered.join("\n") || data.error || "";

    // try to parse progress: expect "PROGRESS current/total" in output
    const lastLine = lines[lines.length - 1] || "";
    const match = lastLine.match(/PROGRESS\s+(\d+)\/(\d+)/i);
    if (match) {
      const current = Number(match[1]);
      const total = Number(match[2]);
      if (total > 0) {
        progressEl.max = total;
        progressEl.value = current;
      }
    }

    if (data.status === "finished" || data.status === "failed") {
      clearInterval(interval);
      progressEl.hidden = true;
      if (data.status === "finished") {
        await loadPairs();
        showStep("review");
      }
    }
  }, 1000);
}


startScan.onclick = async () => {
  if (!scanPhotosLib.value) {
    scanLog.textContent = "Please enter a Photos library path.";
    return;
  }
  // toggle stop if running
  if (scanRunning && scanTaskId) {
    await fetch("/api/task/stop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: scanTaskId }),
    });
    scanLog.textContent = "Scan stopped.";
    scanRunning = false;
    startScan.textContent = "Start similarity scan";
    scanProgress.hidden = true;
    return;
  }
  scanLog.textContent = "Starting scan...";
  scanProgress.hidden = false;
  scanProgress.removeAttribute("value");
  const payload = {
    task: "scan",
    params: {
      photos_lib: scanPhotosLib.value.trim(),
      iphoto_lib: scanIphotoLib.value.trim(),
      hash_method: scanHashMethod.value,
      hash_size: Number(scanHashSize.value || 16),
      threshold_dupes: Number(scanThrDupes.value || 5),
      threshold_cross: Number(scanThrCross.value || 8),
      workers: Number(scanWorkers.value || 4),
      prefer_edited: scanPreferEdited.checked,
    },
  };
  try {
    const res = await fetch("/api/task/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      scanLog.textContent = `Failed to start scan: ${err.error || res.status}`;
      scanProgress.hidden = true;
      return;
    }
    const data = await res.json();
    scanTaskId = data.task_id;
    scanRunning = true;
    startScan.textContent = "Stop";
    scanLog.textContent = `Scan task started (id: ${scanTaskId})...`;
    pollTask(scanTaskId, scanLog, scanProgress);
  } catch (e) {
    scanLog.textContent = `Failed to start scan: ${e}`;
    scanProgress.hidden = true;
  }
};

if (extraExportMissing) {
  extraExportMissing.onclick = async () => {
    extraLogMain.textContent = "Starting export of photos in source not in other...";
    const payload = {
      task: "export_missing",
      params: {
        source_lib: extraExportSrc.value,
        other_lib: extraExportOther.value,
        dest: extraExportDest.value,
      },
    };
    const res = await fetch("/api/task/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      extraLogMain.textContent = `Failed: ${err.error || res.status}`;
      return;
    }
    const data = await res.json();
    pollTask(data.task_id, extraLogMain, albumProgress);
  };
}

if (extraExportKeepers) {
  extraExportKeepers.onclick = async () => {
    extraLogMain.textContent = "Starting export of keepers from primary...";
    const payload = {
      task: "export_keepers",
      params: {
        source_lib: extraExportSrc.value,
        dest: extraExportDest.value,
      },
    };
    const res = await fetch("/api/task/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      extraLogMain.textContent = `Failed: ${err.error || res.status}`;
      return;
    }
    const data = await res.json();
    pollTask(data.task_id, extraLogMain, albumProgress);
  };
}

if (extraBatchToggle) {
  extraBatchToggle.addEventListener("change", async () => {
    if (extraBatchToggle.checked) {
      const res = await fetch("/api/batch/keep_primary", { method: "POST" });
      if (!res.ok) {
        extraBatchStatus.textContent = "Batch action failed.";
        return;
      }
      const data = await res.json();
      extraBatchStatus.textContent = `Updated ${data.result.updated} pairs.`;
      await loadPairs();
    } else {
      const res = await fetch("/api/batch/keep_primary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "clear" }),
      });
      if (!res.ok) {
        extraBatchStatus.textContent = "Clear action failed.";
        return;
      }
      const data = await res.json();
      extraBatchStatus.textContent = `Cleared ${data.result.cleared} pairs.`;
      await loadPairs();
    }
  });
}

startAlbum.onclick = async () => {
  albumLog.textContent = "Starting album creation...";
  const payload = {
    task: "album",
    params: {
      album_name: albumName.value,
      dry_run: albumDryRun.checked,
    },
  };
  try {
    const res = await fetch("/api/task/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      albumLog.textContent = `Failed to start album: ${err.error || res.status}`;
      return;
    }
    const data = await res.json();
    albumTaskId = data.task_id;
    albumLog.textContent = `Album task started (id: ${albumTaskId})...`;
    pollTask(albumTaskId, albumLog, albumProgress);
  } catch (e) {
    albumLog.textContent = `Failed to start album: ${e}`;
  }
};

Promise.all([loadSettings(), loadPairs()]).catch(() => {
  infoEl.textContent = "Failed to load pairs or settings.";
});
let scanRunning = false;
