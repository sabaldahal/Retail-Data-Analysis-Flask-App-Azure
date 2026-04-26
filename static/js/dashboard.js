(function () {
  const page = document.getElementById("dashboard-page");
  if (!page || typeof Chart === "undefined") return;

  const loadingEl = document.getElementById("dashboard-loading");
  const errorEl = document.getElementById("dashboard-error");

  const cfg = {
    responsive: true,
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { color: "#7a8099", font: { size: 10 }, maxTicksLimit: 8 }, grid: { color: "#2a2f3f" } },
      y: { ticks: { color: "#7a8099", font: { size: 10 } }, grid: { color: "#2a2f3f" } }
    }
  };

  function asNumber(value) {
    if (value === null || value === undefined || value === "") return 0;
    if (typeof value === "number") return Number.isFinite(value) ? value : 0;
    const normalized = Number(String(value).replace(/,/g, ""));
    return Number.isFinite(normalized) ? normalized : 0;
  }

  function money(value, digits = 2) {
    return "$" + asNumber(value).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }

  fetch("/api/dashboard-data")
    .then((resp) => {
      if (!resp.ok) throw new Error("Dashboard request failed");
      return resp.json();
    })
    .then((DATA) => {
      loadingEl.classList.add("hidden");
      const kpis = DATA.kpis || {};

      document.getElementById("kpi-hh").textContent = (kpis.households || 0).toLocaleString();
      document.getElementById("kpi-tx").textContent = (kpis.transactions || 0).toLocaleString();
      document.getElementById("kpi-spend").textContent = money(kpis.total_spend, 0);
      document.getElementById("kpi-avg").textContent = money(kpis.avg_spend, 2);

      const st = DATA.spend_time || [];
      new Chart(document.getElementById("spendTimeChart"), {
        type: "line",
        data: {
          labels: st.map((d) => d.year_week),
          datasets: [{ data: st.map((d) => asNumber(d.total_spend)), borderColor: "#4f8ef7", backgroundColor: "#4f8ef720", fill: true, tension: 0.4, pointRadius: 0 }]
        },
        options: {
          ...cfg,
          scales: {
            ...cfg.scales,
            x: { ...cfg.scales.x, title: { display: true, text: "Year-Week", color: "#7a8099" } },
            y: {
              ...cfg.scales.y,
              title: { display: true, text: "Total Spend ($)", color: "#7a8099" },
              ticks: { ...cfg.scales.y.ticks, callback: (v) => "$" + Number(v).toLocaleString() }
            }
          }
        }
      });

      const ds = DATA.dept_spend || [];
      new Chart(document.getElementById("deptChart"), {
        type: "bar",
        data: {
          labels: ds.map((d) => d.DEPARTMENT),
          datasets: [{ data: ds.map((d) => asNumber(d.total)), backgroundColor: "#ff5e3a99", borderColor: "#ff5e3a", borderWidth: 1 }]
        },
        options: {
          ...cfg,
          indexAxis: "y",
          scales: {
            ...cfg.scales,
            x: {
              ...cfg.scales.x,
              title: { display: true, text: "Total Spend ($)", color: "#7a8099" },
              ticks: { ...cfg.scales.x.ticks, callback: (v) => "$" + Number(v).toLocaleString() }
            },
            y: { ...cfg.scales.y, title: { display: true, text: "Department", color: "#7a8099" } }
          }
        }
      });

      const ib = DATA.income_basket || [];
      new Chart(document.getElementById("incomeChart"), {
        type: "bar",
        data: {
          labels: ib.map((d) => d.INCOME_RANGE),
          datasets: [{ data: ib.map((d) => asNumber(d.avg_basket)), backgroundColor: "#34d39999", borderColor: "#34d399", borderWidth: 1 }]
        },
        options: {
          ...cfg,
          scales: {
            ...cfg.scales,
            x: { ...cfg.scales.x, title: { display: true, text: "Income Range", color: "#7a8099" } },
            y: {
              ...cfg.scales.y,
              title: { display: true, text: "Avg Basket Spend ($)", color: "#7a8099" },
              ticks: { ...cfg.scales.y.ticks, callback: (v) => "$" + Number(v).toLocaleString() }
            }
          }
        }
      });

      const rg = DATA.regional || [];
      new Chart(document.getElementById("regionChart"), {
        type: "doughnut",
        data: {
          labels: rg.map((d) => d.STORE_REGION),
          datasets: [{ data: rg.map((d) => asNumber(d.total)), backgroundColor: ["#c084fc", "#4f8ef7", "#34d399", "#ff5e3a"] }]
        },
        options: { responsive: true, plugins: { legend: { display: true, labels: { color: "#7a8099", font: { size: 11 } } } } }
      });

      const bp = DATA.brand_pref || [];
      new Chart(document.getElementById("brandChart"), {
        type: "doughnut",
        data: {
          labels: bp.map((d) => d.BRAND_TY),
          datasets: [{ data: bp.map((d) => asNumber(d.total)), backgroundColor: ["#ff5e3a", "#4f8ef7", "#34d399"] }]
        },
        options: { responsive: true, plugins: { legend: { display: true, labels: { color: "#7a8099", font: { size: 11 } } } } }
      });

      const og = DATA.organic || [];
      new Chart(document.getElementById("organicChart"), {
        type: "doughnut",
        data: {
          labels: og.map((d) => {
            if (d.NATURAL_ORGANIC_FLAG === "Y") return "Organic";
            if (d.NATURAL_ORGANIC_FLAG === "N") return "Conventional";
            return "Unknown";
          }),
          datasets: [{ data: og.map((d) => asNumber(d.total)), backgroundColor: ["#34d399", "#7a8099", "#f59e0b"] }]
        },
        options: { responsive: true, plugins: { legend: { display: true, labels: { color: "#7a8099", font: { size: 11 } } } } }
      });

      const hs = DATA.hh_spend || [];
      new Chart(document.getElementById("hhsizeChart"), {
        type: "bar",
        data: {
          labels: hs.map((d) => (d.HH_SIZE === "UNKNOWN" ? "Unknown" : "Size " + d.HH_SIZE)),
          datasets: [{ data: hs.map((d) => asNumber(d.avg_spend)), backgroundColor: "#4f8ef799", borderColor: "#4f8ef7", borderWidth: 1 }]
        },
        options: {
          ...cfg,
          scales: {
            ...cfg.scales,
            x: { ...cfg.scales.x, title: { display: true, text: "Household Size", color: "#7a8099" } },
            y: {
              ...cfg.scales.y,
              title: { display: true, text: "Avg Household Spend ($)", color: "#7a8099" },
              ticks: { ...cfg.scales.y.ticks, callback: (v) => "$" + Number(v).toLocaleString() }
            }
          }
        }
      });
    })
    .catch((err) => {
      loadingEl.classList.add("hidden");
      errorEl.classList.remove("hidden");
      errorEl.textContent = "Unable to load dashboard data right now. " + err.message;
    });
})();
