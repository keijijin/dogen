(() => {
  const roots = document.querySelectorAll("[data-reading-toggle]");
  for (const root of roots) {
    const article = root.closest("article");
    if (!article) continue;
    const buttons = root.querySelectorAll("[data-reading-tab]");
    const panels = article.querySelectorAll("[data-reading-panel]");
    const setActive = (name) => {
      for (const btn of buttons) {
        const active = btn.getAttribute("data-reading-tab") === name;
        btn.classList.toggle("is-active", active);
        btn.setAttribute("aria-selected", active ? "true" : "false");
      }
      for (const panel of panels) {
        const active = panel.getAttribute("data-reading-panel") === name;
        panel.hidden = !active;
      }
    };
    for (const btn of buttons) {
      btn.addEventListener("click", () => {
        const name = btn.getAttribute("data-reading-tab");
        if (!name) return;
        setActive(name);
      });
    }
    setActive("original");
  }
})();
