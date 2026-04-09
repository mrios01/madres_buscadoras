document.addEventListener("DOMContentLoaded", () => {
  const tabs = document.querySelectorAll(".missing-tabs .nav-link");
  tabs.forEach((tab) => {
    tab.addEventListener("shown.bs.tab", () => {
      const name = tab.textContent ? tab.textContent.trim() : "tab";
      console.debug("Active tab:", name);
    });
  });
});
