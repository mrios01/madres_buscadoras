document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.querySelector("input[name='search']");
  const logoutButton = document.querySelector("[data-logout-trigger]");
  if (!searchInput) {
    if (!logoutButton) {
      return;
    }
  }

  if (searchInput) {
    searchInput.addEventListener("focus", () => {
      searchInput.classList.add("shadow-sm");
    });

    searchInput.addEventListener("blur", () => {
      searchInput.classList.remove("shadow-sm");
    });
  }

  if (logoutButton) {
    logoutButton.addEventListener("click", async () => {
      await fetch("/auth/logout", { method: "POST" });
      window.location.href = "/login";
    });
  }
});
