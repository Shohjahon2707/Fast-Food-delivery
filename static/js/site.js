"use strict";
function toast(message, error = false) {
  const box = document.createElement("div");
  box.className = "toast" + (error ? " error" : "");
  const text = document.createElement("span");
  text.textContent = message;
  const close = document.createElement("button");
  close.type = "button";
  close.textContent = "×";
  close.setAttribute("aria-label", "Закрыть уведомление");
  close.onclick = () => box.remove();
  box.append(text, close);
  document.querySelector(".toast-stack").append(box);
  setTimeout(() => box.remove(), 6000);
}
document
  .querySelectorAll("[data-dismiss]")
  .forEach((button) =>
    button.addEventListener("click", () => button.parentElement.remove()),
  );
document
  .querySelectorAll("[data-autosubmit]")
  .forEach((select) =>
    select.addEventListener("change", () => select.form.requestSubmit()),
  );
document.querySelectorAll("[data-confirm]").forEach((form) =>
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  }),
);
document.querySelectorAll("[data-confirm-button]").forEach((button) =>
  button.addEventListener("click", (event) => {
    if (!window.confirm(button.dataset.confirmButton)) event.preventDefault();
  }),
);
document.querySelectorAll("[data-submit-once]").forEach((form) =>
  form.addEventListener("submit", () => {
    const button = form.querySelector("button[type=submit]");
    if (button) {
      button.disabled = true;
      button.textContent = "Оформляем…";
    }
  }),
);
window.addEventListener("pageshow", (event) => {
  if (event.persisted) window.location.reload();
});
document.querySelectorAll("[data-add-cart]").forEach((form) =>
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button");
    if (button.disabled) return;
    button.disabled = true;
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (response.redirected) {
        window.location.assign(response.url);
        return;
      }
      if (!response.ok)
        throw new Error(
          "Не удалось добавить блюдо. Обновите страницу и попробуйте снова.",
        );
      const data = await response.json();
      document.querySelectorAll("[data-cart-count]").forEach((node) => {
        node.textContent = data.count;
      });
      toast(data.message);
    } catch (error) {
      toast(error.message || "Не удалось связаться с сервером.", true);
    } finally {
      button.disabled = false;
    }
  }),
);

const liveOrder = document.querySelector("[data-live-order]");
if (liveOrder) {
  const checkStatus = async () => {
    if (document.visibilityState !== "visible") return;
    try {
      const response = await fetch(liveOrder.dataset.liveOrder, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!response.ok || response.redirected) return;
      const data = await response.json();
      if (
        String(data.version) !== liveOrder.dataset.version &&
        !liveOrder.querySelector("a")
      ) {
        const link = document.createElement("a");
        link.href = window.location.href;
        link.className = "text-link";
        link.textContent = "Есть обновление заказа — показать →";
        liveOrder.replaceChildren(link);
        liveOrder.setAttribute("role", "status");
      }
    } catch (_) {
      /* Keep the last known order and the manual refresh link. */
    }
  };
  setInterval(checkStatus, 20000);
}
