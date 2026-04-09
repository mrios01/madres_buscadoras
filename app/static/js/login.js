async function onGoogleCredential(response) {
  const statusEl = document.getElementById("status");
  statusEl.textContent = "Validando credenciales...";

  try {
    const res = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: response.credential }),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      statusEl.textContent = data.error || "No se pudo iniciar sesion";
      return;
    }

    window.location.href = "/missing-profiles";
  } catch (_err) {
    statusEl.textContent = "Error de red. Intenta de nuevo.";
  }
}

window.onGoogleCredential = onGoogleCredential;

const previewButton = document.getElementById("previewButton");
if (previewButton) {
  previewButton.addEventListener("click", () => {
    window.location.href = "/missing-profiles";
  });
}
