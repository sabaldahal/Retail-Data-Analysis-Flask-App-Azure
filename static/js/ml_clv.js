(function () {
  const page = document.getElementById("ml-clv-page");
  if (!page || typeof Chart === "undefined") return;

  const loadingEl = document.getElementById("ml-clv-loading");
  const errorEl = document.getElementById("ml-clv-error");
  const contentEl = document.getElementById("ml-clv-content");

  fetch("/ml/clv/content")
    .then((resp) => {
      if (!resp.ok) throw new Error("CLV request failed");
      return resp.text();
    })
    .then((html) => {
      contentEl.innerHTML = html;
      loadingEl.classList.add("hidden");
      hydrateCharts(contentEl);
    })
    .catch((err) => {
      loadingEl.classList.add("hidden");
      errorEl.classList.remove("hidden");
      errorEl.textContent = "Unable to load CLV results right now. " + err.message;
    });

  function hydrateCharts(root) {
    const dataHost = root.querySelector("#ml-clv-data");
    if (!dataHost) return;

    const featRaw = dataHost.getAttribute("data-feature-names");
    const impRaw = dataHost.getAttribute("data-importances");
    const distRaw = dataHost.getAttribute("data-score-distribution");
    if (!featRaw || !impRaw || !distRaw) return;

    const feat = JSON.parse(featRaw);
    const imp = JSON.parse(impRaw);
    const dist = JSON.parse(distRaw);

    new Chart(document.getElementById("featChart"), {
    type: "bar",
    data: {
      labels: feat,
      datasets: [{ data: imp, backgroundColor: "#ff5e3a99", borderColor: "#ff5e3a", borderWidth: 1 }]
    },
    options: {
      indexAxis: "y",
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#7a8099", font: { size: 10 } }, grid: { color: "#2a2f3f" } },
        y: { ticks: { color: "#7a8099", font: { size: 11 } }, grid: { color: "#2a2f3f" } }
      }
    }
  });

    new Chart(document.getElementById("distChart"), {
    type: "bar",
    data: {
      labels: Object.keys(dist),
      datasets: [{ data: Object.values(dist), backgroundColor: "#4f8ef799", borderColor: "#4f8ef7", borderWidth: 1 }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#7a8099" }, grid: { color: "#2a2f3f" } },
        y: { ticks: { color: "#7a8099" }, grid: { color: "#2a2f3f" } }
      }
    }
  });
  }
})();
