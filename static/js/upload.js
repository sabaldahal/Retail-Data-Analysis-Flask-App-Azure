(function () {
  const button = document.getElementById("upload-btn");
  if (!button) return;

  const fileInputs = [
    document.getElementById("f-transactions"),
    document.getElementById("f-households"),
    document.getElementById("f-products")
  ].filter(Boolean);

  function allFilesSelected() {
    return fileInputs.length === 3 && fileInputs.every((input) => input.files && input.files[0]);
  }

  function syncUploadState() {
    button.disabled = !allFilesSelected();
  }

  fileInputs.forEach((input) => input.addEventListener("change", syncUploadState));
  syncUploadState();

  button.addEventListener("click", doUpload);

  function formatEta(seconds) {
    if (seconds === null || seconds === undefined) return "";
    const total = Math.max(0, Math.floor(seconds));
    const minutes = Math.floor(total / 60);
    const remainingSeconds = total % 60;
    if (minutes > 0) {
      return `${minutes}m ${String(remainingSeconds).padStart(2, "0")}s`;
    }
    return `${remainingSeconds}s`;
  }

  async function doUpload() {
    const uploadId = (window.crypto && window.crypto.randomUUID)
      ? window.crypto.randomUUID()
      : String(Date.now());

    const mode = document.getElementById("upload-mode")?.value || "upsert";
    const files = {
      transactions: document.getElementById("f-transactions").files[0],
      households: document.getElementById("f-households").files[0],
      products: document.getElementById("f-products").files[0]
    };

    const hasAllFiles = Object.values(files).every(Boolean);
    if (!hasAllFiles) {
      alert("Please select all three files before uploading.");
      return;
    }

    if (mode === "clear_load") {
      const proceed = window.confirm(
        "This will clear all existing rows in transactions, households, and products before loading the uploaded files. Continue?"
      );
      if (!proceed) return;
    }

    const uploadProgress = document.getElementById("upload-progress");
    const results = document.getElementById("upload-results");
    const bar = document.getElementById("prog-bar");
    const statusText = document.getElementById("upload-status-text");

    button.disabled = true;
    uploadProgress.classList.remove("hidden");
    results.classList.add("hidden");
    results.innerHTML = "";
    statusText.textContent = "Preparing upload...";

    const fd = new FormData();
    fd.append("mode", mode);
    fd.append("upload_id", uploadId);
    for (const [key, value] of Object.entries(files)) {
      if (value) fd.append(key, value);
    }

    bar.style.width = "2%";

    let polling = true;
    const pollProgress = async () => {
      while (polling) {
        try {
          const resp = await fetch("/upload/progress?upload_id=" + encodeURIComponent(uploadId));
          if (resp.ok) {
            const p = await resp.json();
            if (typeof p.percent === "number") {
              bar.style.width = Math.max(2, Math.min(100, p.percent)) + "%";
            }
            if (p.message) {
              let extra = "";
              if (typeof p.eta_seconds === "number" && p.eta_seconds > 0) {
                extra = ` - ETA ${formatEta(p.eta_seconds)}`;
              }
              if (p.table && p.total) {
                statusText.textContent = `${p.message} (${p.processed || 0}/${p.total})${extra}`;
              } else {
                statusText.textContent = `${p.message}${extra}`;
              }
            }
            if (p.status === "completed" || p.status === "failed") {
              break;
            }
          }
        } catch (_e) {
          // Ignore polling hiccups; final request result is authoritative.
        }
        await new Promise((resolve) => setTimeout(resolve, 700));
      }
    };

    const pollTask = pollProgress();

    try {
      const resp = await fetch("/upload", { method: "POST", body: fd });
      bar.style.width = "100%";
      const data = await resp.json();
      results.classList.remove("hidden");

      if (data.status === "ok") {
        const modeLabel = data.mode === "clear_load"
          ? "Clear database then load"
          : "Append + replace (upsert)";
        statusText.textContent = "Upload completed.";
        results.innerHTML = '<div class="alert alert-success">' +
          "✓ Upload complete (mode: " + modeLabel + ")<br>" +
          data.results.map((r) => "&nbsp;&nbsp;• " + r).join("<br>") +
          '</div><a href="/data-pull" class="btn btn-info">View Data Pull →</a>';
      } else {
        statusText.textContent = "Upload failed.";
        results.innerHTML = '<div class="alert alert-danger">Upload failed: ' + JSON.stringify(data) + "</div>";
      }
    } catch (e) {
      results.classList.remove("hidden");
      statusText.textContent = "Upload failed.";
      results.innerHTML = '<div class="alert alert-danger">Error: ' + e.message + "</div>";
    } finally {
      polling = false;
      await pollTask;
      button.disabled = false;
    }
  }
})();
