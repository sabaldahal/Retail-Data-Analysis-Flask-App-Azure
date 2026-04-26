(function () {
  const page = document.getElementById("ml-churn-page");
  if (!page || typeof Chart === "undefined") return;

  const loadingEl = document.getElementById("ml-churn-loading");
  const errorEl = document.getElementById("ml-churn-error");
  const contentEl = document.getElementById("ml-churn-content");

  fetch("/ml/churn/content")
    .then((resp) => {
      if (!resp.ok) throw new Error("Churn request failed");
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
      errorEl.textContent = "Unable to load churn results right now. " + err.message;
    });

  function hydrateCharts(root) {
    const dataHost = root.querySelector("#ml-churn-data");
    if (!dataHost) return;

    for (const el of root.querySelectorAll(".js-progress-fill")) {
      const pct = Number(el.getAttribute("data-pct") || 0);
      el.style.width = pct + "%";
    }

    const featRaw = dataHost.getAttribute("data-feature-importances");
    const incomeRaw = dataHost.getAttribute("data-churn-income");
    if (!featRaw || !incomeRaw) return;

    const feat = JSON.parse(featRaw);
    const ic = JSON.parse(incomeRaw);

    new Chart(document.getElementById("featChart"), {
    type: "bar",
    data: {
      labels: feat.map((d) => d.feature),
      datasets: [{ data: feat.map((d) => d.importance), backgroundColor: "#f8717199", borderColor: "#f87171", borderWidth: 1 }]
    },
    options: {
      indexAxis: "y",
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#7a8099", font: { size: 10 } }, grid: { color: "#2a2f3f" } },
        y: { ticks: { color: "#7a8099", font: { size: 10 } }, grid: { color: "#2a2f3f" } }
      }
    }
  });

    new Chart(document.getElementById("incomeChurnChart"), {
    type: "bar",
    data: {
      labels: ic.map((d) => d.income),
      datasets: [{
        label: "Churn Rate",
        data: ic.map((d) => +(d.churn_rate * 100).toFixed(1)),
        backgroundColor: "#4f8ef799",
        borderColor: "#4f8ef7",
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#7a8099", font: { size: 9 } }, grid: { color: "#2a2f3f" } },
        y: { ticks: { color: "#7a8099", callback: (v) => v + "%" }, grid: { color: "#2a2f3f" } }
      }
    }
  });
  }
})();
