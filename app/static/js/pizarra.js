const CHANNEL = "general";
let socket = null;
let replyTarget = null;
let pendingImage = null;

function setStatus(message, isError = false) {
  const el = document.getElementById("chatStatus");
  el.textContent = message;
  el.style.color = isError ? "#9b1c1c" : "#6f5564";
}

function formatTime(isoValue) {
  if (!isoValue) {
    return "";
  }
  const date = new Date(isoValue);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleString("es-MX", {
    hour12: false,
    year: "2-digit",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function showReplyBanner(target) {
  const banner = document.getElementById("replyBanner");
  const preview = document.getElementById("replyPreview");
  replyTarget = target;
  preview.textContent = target.reply_to_preview || target.text || "Mensaje";
  banner.classList.remove("is-hidden");
}

function clearReplyBanner() {
  replyTarget = null;
  document.getElementById("replyBanner").classList.add("is-hidden");
  document.getElementById("replyPreview").textContent = "";
}

function messageHtml(item) {
  const replyBlock = item.reply_to_preview
    ? `<div class="msg-reply">${escapeHtml(item.reply_to_preview)}</div>`
    : "";

  const imageBlock = item.image_url
    ? `<img class="msg-image" src="${encodeURI(item.image_url)}" alt="Imagen adjunta" loading="lazy" onerror="this.onerror=null;this.src='/static/img/profile-placeholder.svg';" />`
    : "";

  return `
    <article class="msg" data-message-id="${item.id}">
      <div class="msg-head">
        <span class="msg-user">${escapeHtml(item.user_display_name || "Busqueda")}</span>
        <span class="msg-time">${escapeHtml(formatTime(item.created_at))}</span>
      </div>
      ${replyBlock}
      <div class="msg-text">${escapeHtml(item.text || "")}</div>
      ${imageBlock}
      <div class="msg-actions">
        <button type="button" data-reply-id="${item.id}">Responder</button>
      </div>
    </article>
  `;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function appendMessage(item) {
  const container = document.getElementById("chatMessages");
  container.insertAdjacentHTML("beforeend", messageHtml(item));
  container.scrollTop = container.scrollHeight;
}

function wireReplyButtons() {
  const container = document.getElementById("chatMessages");
  container.querySelectorAll("[data-reply-id]").forEach((button) => {
    if (button.dataset.bound === "1") {
      return;
    }
    button.dataset.bound = "1";
    button.addEventListener("click", () => {
      const card = button.closest(".msg");
      const text = card ? card.querySelector(".msg-text")?.textContent : "";
      showReplyBanner({
        id: button.dataset.replyId,
        text: text || "",
      });
    });
  });
}

async function fetchHistory() {
  const response = await fetch(`/chat/messages?channel=${CHANNEL}&limit=80`, {
    credentials: "same-origin",
  });
  if (!response.ok) {
    throw new Error("No se pudo cargar el historial de chat.");
  }

  const payload = await response.json();
  const items = Array.isArray(payload.items) ? payload.items : [];
  const container = document.getElementById("chatMessages");
  container.innerHTML = items.map(messageHtml).join("");
  wireReplyButtons();
  container.scrollTop = container.scrollHeight;
}

function connectSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const url = `${protocol}://${window.location.host}/chat/ws?channel=${CHANNEL}`;
  socket = new WebSocket(url);

  socket.addEventListener("open", () => {
    setStatus("Conectado al canal general.");
  });

  socket.addEventListener("message", (event) => {
    let payload = null;
    try {
      payload = JSON.parse(event.data);
    } catch (_error) {
      return;
    }

    if (payload.type === "error") {
      setStatus(payload.error || "Error en chat", true);
      return;
    }

    if (payload.type === "message" && payload.item) {
      appendMessage(payload.item);
      wireReplyButtons();
      return;
    }
  });

  socket.addEventListener("close", () => {
    setStatus("Conexion cerrada. Reintentando...", true);
    window.setTimeout(connectSocket, 1500);
  });

  socket.addEventListener("error", () => {
    setStatus("Error de conexion en tiempo real.", true);
  });
}

async function uploadImage(file) {
  const data = new FormData();
  data.append("image", file);

  const response = await fetch("/chat/upload-image", {
    method: "POST",
    credentials: "same-origin",
    body: data,
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || "No se pudo subir la imagen.");
  }

  return payload;
}

async function onSubmit(event) {
  event.preventDefault();

  if (!socket || socket.readyState !== WebSocket.OPEN) {
    setStatus("El chat aun no esta conectado.", true);
    return;
  }

  const textEl = document.getElementById("chatText");
  const text = textEl.value.trim();

  if (!text && !pendingImage) {
    setStatus("Escribe un mensaje o adjunta una imagen.", true);
    return;
  }

  const body = {
    type: "message",
    text,
    image_object_key: pendingImage ? pendingImage.object_key : null,
    reply_to_message_id: replyTarget ? replyTarget.id : null,
  };

  socket.send(JSON.stringify(body));
  textEl.value = "";
  pendingImage = null;
  document.getElementById("imageInfo").textContent = "";
  document.getElementById("chatImage").value = "";
  clearReplyBanner();
}

async function onImageChange(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) {
    return;
  }

  setStatus("Subiendo imagen...", false);
  try {
    pendingImage = await uploadImage(file);
    document.getElementById("imageInfo").textContent = `Imagen lista: ${file.name}`;
    setStatus("Imagen adjuntada. Ahora envia el mensaje.");
  } catch (error) {
    pendingImage = null;
    document.getElementById("imageInfo").textContent = "";
    setStatus(error.message || "Error al subir imagen", true);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  document
    .getElementById("chatComposer")
    .addEventListener("submit", onSubmit);
  document
    .getElementById("chatImage")
    .addEventListener("change", onImageChange);
  document
    .getElementById("clearReply")
    .addEventListener("click", clearReplyBanner);

  try {
    await fetchHistory();
    setStatus("Historial cargado.");
  } catch (error) {
    setStatus(error.message || "No se pudo cargar historial.", true);
  }

  connectSocket();
});
