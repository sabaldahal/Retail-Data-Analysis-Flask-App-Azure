(function () {
  const page = document.getElementById("ml-basket-page");
  if (!page || typeof Chart === "undefined") return;

  const loadingEl = document.getElementById("ml-basket-loading");
  const errorEl = document.getElementById("ml-basket-error");
  const contentEl = document.getElementById("ml-basket-content");

  fetch("/ml/basket/content")
    .then((resp) => {
      if (!resp.ok) throw new Error("Basket request failed");
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
      errorEl.textContent = "Unable to load basket results right now. " + err.message;
    });

  function hydrateCharts(root) {
    const dataHost = root.querySelector("#ml-basket-data");
    if (!dataHost) return;

    for (const el of root.querySelectorAll(".js-progress-fill")) {
      const pct = Number(el.getAttribute("data-pct") || 0);
      el.style.width = pct + "%";
    }

    const topItemsRaw = dataHost.getAttribute("data-top-items");
    if (!topItemsRaw) return;

    const topItems = JSON.parse(topItemsRaw);

    new Chart(document.getElementById("topItemsChart"), {
    type: "bar",
    data: {
      labels: topItems.map((d) => d.item),
      datasets: [{ data: topItems.map((d) => d.count), backgroundColor: "#4f8ef799", borderColor: "#4f8ef7", borderWidth: 1 }]
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

    const hasRf = dataHost.getAttribute("data-has-rf") === "1";
    if (!hasRf) return;

    const rfFeatRaw = dataHost.getAttribute("data-rf-features") || "[]";
    const rfFeat = JSON.parse(rfFeatRaw);

    new Chart(document.getElementById("rfFeatChart"), {
    type: "bar",
    data: {
      labels: rfFeat.map((d) => d.item),
      datasets: [{ data: rfFeat.map((d) => d.importance), backgroundColor: "#ff5e3a99", borderColor: "#ff5e3a", borderWidth: 1 }]
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
  }
})();
