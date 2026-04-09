function toIntOrNull(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return null;
  }

  const parsed = Number.parseInt(raw, 10);
  return Number.isNaN(parsed) ? null : parsed;
}

function splitLines(value) {
  return String(value || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function buildPayload(form, primaryImageUrl) {
  const firstName = form.querySelector("#firstName").value.trim();
  const lastName = form.querySelector("#lastName").value.trim();
  const ageRaw = form.querySelector("#age").value.trim();
  const gender = form.querySelector("#gender").value.trim();
  const dateMissing = form.querySelector("#dateMissing").value;

  const state = form.querySelector("#state").value.trim();
  const city = form.querySelector("#city").value.trim();
  const neighborhood = form.querySelector("#neighborhood").value.trim();

  const heightCm = toIntOrNull(form.querySelector("#heightCm").value);
  const weightKg = toIntOrNull(form.querySelector("#weightKg").value);
  const clothingLastSeen = form.querySelector("#clothingLastSeen").value.trim();
  const identifyingMarks = splitLines(form.querySelector("#identifyingMarks").value);

  const officialCaseNumberRaw = form
    .querySelector("#officialCaseNumber")
    .value.trim();
  const officialCaseNumber = officialCaseNumberRaw || "N/D";
  const dnaSampleRegistered = form.querySelector("#dnaSampleRegistered").checked;
  const suspectedContext = form.querySelector("#suspectedContext").value.trim();
  const internalNotes = form.querySelector("#internalNotes").value.trim();

  return {
    status: "ACTIVE_SEARCH",
    public_ficha: {
      first_name: firstName,
      last_name: lastName,
      age_at_disappearance: Number.parseInt(ageRaw, 10),
      gender,
      date_missing: dateMissing,
      location_last_seen: {
        city,
        state,
        neighborhood,
      },
      physical_description: {
        height_cm: heightCm,
        weight_kg: weightKg,
        identifying_marks: identifyingMarks,
        clothing_last_seen: clothingLastSeen,
      },
      primary_image_url: primaryImageUrl,
    },
    private_dossier: {
      authorized_collective_ids: [],
      official_case_number: officialCaseNumber,
      dna_sample_registered: dnaSampleRegistered,
      suspected_context: suspectedContext,
      internal_notes: internalNotes,
    },
  };
}

async function uploadPrimaryImage(file) {
  const data = new FormData();
  data.append("image", file);

  const response = await fetch("/missing-persons/upload-image", {
    method: "POST",
    credentials: "same-origin",
    body: data,
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const details = payload.error || "No se pudo subir la imagen.";
    throw new Error(details);
  }

  return payload.url;
}

function setStatus(message, isError) {
  const status = document.getElementById("formStatus");
  status.textContent = message;
  status.style.color = isError ? "#b91c1c" : "#7f2d67";
}

async function submitPayload(payload) {
  const response = await fetch("/missing-persons/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(payload),
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const details = data.error || "No se pudo guardar el expediente.";
    throw new Error(details);
  }

  return data;
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("missingPersonForm");
  const privateAck = document.getElementById("ackPrivate");
  const privateFieldset = document.getElementById("privateFieldset");
  const output = document.getElementById("jsonOutput");

  privateAck.addEventListener("change", () => {
    privateFieldset.disabled = !privateAck.checked;
    if (!privateAck.checked) {
      setStatus("Activa la confirmacion de Nivel 2 para capturar datos privados.", true);
    } else {
      setStatus("", false);
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (!privateAck.checked) {
      setStatus(
        "Debes confirmar el aviso de seguridad para capturar y enviar Nivel 2.",
        true,
      );
      return;
    }

    if (!form.reportValidity()) {
      setStatus("Completa los campos obligatorios antes de enviar.", true);
      return;
    }

    const imageInput = form.querySelector("#primaryImageFile");
    const imageFile = imageInput && imageInput.files ? imageInput.files[0] : null;
    if (!imageFile) {
      setStatus("Selecciona una imagen principal para continuar.", true);
      return;
    }

    try {
      setStatus("Subiendo imagen al almacenamiento seguro...", false);
      const imageUrl = await uploadPrimaryImage(imageFile);

      const payload = buildPayload(form, imageUrl);
      output.textContent = JSON.stringify(payload, null, 2);

      setStatus("Cifrando y enviando expediente...", false);
      await submitPayload(payload);
      setStatus("Expediente guardado correctamente.", false);
      form.reset();
      privateFieldset.disabled = true;
    } catch (error) {
      setStatus(error.message || "Error de red", true);
    }
  });
});
