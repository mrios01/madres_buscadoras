const termsCheckbox = document.getElementById("accept_terms");
const privacyCheckbox = document.getElementById("accept_privacy");
const gsiContainer = document.getElementById("gsiContainer");
const recaptchaSiteKey = window.APP_RECAPTCHA_SITE_KEY || "";

const AUTH_ERROR_MESSAGES = {
  legal_consent_required:
    "Debes aceptar Terminos de Uso y Aviso de Privacidad para continuar.",
  recaptcha_token_required:
    "No se pudo validar Recaptcha. Intenta nuevamente.",
  recaptcha_not_configured:
    "Recaptcha no esta configurado en el servidor.",
  recaptcha_project_not_configured:
    "Recaptcha Enterprise requiere proyecto configurado en el servidor.",
  recaptcha_site_key_not_configured:
    "Falta la llave publica de Recaptcha en el servidor.",
  recaptcha_enterprise_auth_failed:
    "No se pudo autenticar Recaptcha Enterprise en el servidor.",
  recaptcha_verification_failed:
    "No fue posible validar Recaptcha. Intenta en unos segundos.",
  recaptcha_enterprise_verification_failed:
    "No fue posible validar Recaptcha Enterprise. Intenta en unos segundos.",
  recaptcha_failed:
    "Recaptcha detecto actividad de riesgo. Vuelve a intentar.",
  recaptcha_action_mismatch:
    "Recaptcha no coincide con la accion esperada. Recarga la pagina.",
  recaptcha_low_score:
    "No se pudo validar seguridad de acceso. Intenta de nuevo.",
  invalid_google_token:
    "Google no pudo validar tu sesion. Intenta iniciar sesion otra vez.",
  id_token_required: "Falta la credencial de Google.",
};

function getAuthErrorMessage(errorCode) {
  if (!errorCode) {
    return "No se pudo iniciar sesion";
  }
  return AUTH_ERROR_MESSAGES[errorCode] || "No se pudo iniciar sesion";
}

function hasRequiredConsent() {
  return Boolean(
    termsCheckbox &&
      termsCheckbox.checked &&
      privacyCheckbox &&
      privacyCheckbox.checked,
  );
}

function updateAuthInterlock() {
  if (!gsiContainer) {
    return;
  }
  const isBlocked = !hasRequiredConsent();
  gsiContainer.classList.toggle("is-blocked", isBlocked);
}

if (termsCheckbox) {
  termsCheckbox.addEventListener("change", updateAuthInterlock);
}
if (privacyCheckbox) {
  privacyCheckbox.addEventListener("change", updateAuthInterlock);
}
updateAuthInterlock();

async function onGoogleCredential(response) {
  const statusEl = document.getElementById("status");

  if (!hasRequiredConsent()) {
    statusEl.textContent = "Debes aceptar Terminos y Privacidad para continuar.";
    updateAuthInterlock();
    return;
  }

  if (!recaptchaSiteKey || !window.grecaptcha) {
    statusEl.textContent = "Recaptcha no esta disponible. Intenta mas tarde.";
    return;
  }

  statusEl.textContent = "Validando credenciales...";

  try {
    const recaptchaToken = await window.grecaptcha.execute(recaptchaSiteKey, {
      action: "auth_login",
    });

    const res = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id_token: response.credential,
        accept_terms: termsCheckbox.checked,
        accept_privacy: privacyCheckbox.checked,
        acceptTerms: termsCheckbox.checked,
        acceptPrivacy: privacyCheckbox.checked,
        recaptcha_token: recaptchaToken,
      }),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      statusEl.textContent = getAuthErrorMessage(data.error);
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
