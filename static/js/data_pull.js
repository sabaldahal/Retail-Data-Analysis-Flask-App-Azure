(function () {
  const page = document.getElementById("data-pull-page");
  if (!page) return;

  const form = document.getElementById("data-pull-form");
  const input = document.getElementById("data-pull-input");
  const loadingEl = document.getElementById("data-pull-loading");
  const errorEl = document.getElementById("data-pull-error");
  const contentEl = document.getElementById("data-pull-content");
  const quickPicks = Array.from(page.querySelectorAll(".js-quick-pick"));

  function normalizeHshdNum(value) {
    const parsed = Number.parseInt(String(value), 10);
    if (Number.isNaN(parsed) || parsed < 1) return 10;
    return parsed;
  }

  function normalizePage(value) {
    const parsed = Number.parseInt(String(value), 10);
    if (Number.isNaN(parsed) || parsed < 1) return 1;
    return parsed;
  }

  function updateQuickPickStyles(hshdNum) {
    for (const link of quickPicks) {
      const value = Number.parseInt(link.getAttribute("data-hshd-num") || "0", 10);
      if (value === hshdNum) {
        link.classList.remove("badge-gray");
        link.classList.add("badge-blue");
      } else {
        link.classList.remove("badge-blue");
        link.classList.add("badge-gray");
      }
    }
  }

  function loadContent(hshdNum, page, pushHistory) {
    const query = new URLSearchParams({ hshd_num: String(hshdNum), page: String(page) }).toString();

    input.value = String(hshdNum);
    updateQuickPickStyles(hshdNum);
    loadingEl.classList.remove("hidden");
    errorEl.classList.add("hidden");

    fetch("/data-pull/content?" + query)
      .then((resp) => {
        if (!resp.ok) throw new Error("Data Pull request failed");
        return resp.text();
      })
      .then((html) => {
        contentEl.innerHTML = html;
        loadingEl.classList.add("hidden");
        if (pushHistory) {
          window.history.pushState({}, "", "/data-pull?" + query);
        }
      })
      .catch((err) => {
        loadingEl.classList.add("hidden");
        errorEl.classList.remove("hidden");
        errorEl.textContent = "Unable to load household records right now. " + err.message;
      });
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const hshdNum = normalizeHshdNum(input.value);
    loadContent(hshdNum, 1, true);
  });

  for (const link of quickPicks) {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const hshdNum = normalizeHshdNum(link.getAttribute("data-hshd-num"));
      loadContent(hshdNum, 1, true);
    });
  }

  contentEl.addEventListener("click", (event) => {
    const link = event.target.closest(".js-page-link");
    if (!link) return;
    event.preventDefault();
    const hshdNum = normalizeHshdNum(input.value || page.getAttribute("data-hshd-num") || 10);
    const nextPage = normalizePage(link.getAttribute("data-page"));
    loadContent(hshdNum, nextPage, true);
  });

  window.addEventListener("popstate", () => {
    const params = new URLSearchParams(window.location.search);
    const hshdNum = normalizeHshdNum(params.get("hshd_num") || 10);
    const pageNum = normalizePage(params.get("page") || 1);
    loadContent(hshdNum, pageNum, false);
  });

  const initial = normalizeHshdNum(page.getAttribute("data-hshd-num") || 10);
  const initialPage = normalizePage(new URLSearchParams(window.location.search).get("page") || 1);
  loadContent(initial, initialPage, false);
})();
