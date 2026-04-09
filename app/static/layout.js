document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.querySelector("input[name='search']");
  if (!searchInput) {
    return;
  }

  searchInput.addEventListener("focus", () => {
    searchInput.classList.add("shadow-sm");
  });

  searchInput.addEventListener("blur", () => {
    searchInput.classList.remove("shadow-sm");
  });
});
