(() => {
  const panel = document.querySelector("[data-courier-tracking]");
  const countdown = document.querySelector("[data-countdown]");
  if (countdown) {
    const tick = () => {
      const remaining = Math.max(
        0,
        Math.ceil(
          (Date.parse(countdown.dataset.countdown) - Date.now()) / 1000,
        ),
      );
      countdown.textContent = remaining
        ? `${remaining} сек на ответ`
        : "Время истекло";
      if (!remaining)
        countdown
          .closest("article")
          .querySelectorAll("button")
          .forEach((button) => {
            button.disabled = true;
          });
    };
    tick();
    setInterval(tick, 1000);
  }
  if (!panel) {
    sessionStorage.removeItem("courierGpsEnabled");
    return;
  }
  const status = panel.querySelector("[data-gps-status]");
  const start = panel.querySelector("[data-start-gps]");
  const stop = panel.querySelector("[data-stop-gps]");
  const update = panel.querySelector("[data-offer-update]");
  const csrf = document.querySelector("[name=csrfmiddlewaretoken]")?.value;
  let watcher = null,
    lastSent = 0,
    sending = false,
    polling = false;
  const post = (url, data = {}) =>
    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrf },
      body: new URLSearchParams(data),
    });
  const sendPosition = async (position) => {
    if (sending || Date.now() - lastSent < 20000) return;
    sending = true;
    try {
      const response = await post(panel.dataset.courierTracking, {
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy: position.coords.accuracy,
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(result.error || "Не удалось передать точку.");
      lastSent = Date.now();
      status.textContent = result.precise
        ? "Геопозиция обновляется. Подбираем заказы рядом."
        : "Низкая точность GPS. Для предложений нужна точность до 200 метров.";
    } catch (error) {
      status.textContent =
        error.message || "Связь потеряна. Повторим передачу точки.";
    } finally {
      sending = false;
    }
  };
  start.addEventListener("click", () => {
    if (!navigator.geolocation) {
      status.textContent = "Геопозиция недоступна в этом браузере.";
      return;
    }
    if (watcher !== null) return;
    sessionStorage.setItem("courierGpsEnabled", "yes");
    start.disabled = true;
    stop.hidden = false;
    status.textContent = "Определяем позицию…";
    watcher = navigator.geolocation.watchPosition(
      sendPosition,
      (error) => {
        status.textContent =
          error.code === 1
            ? "Разрешите геопозицию в настройках браузера, затем включите снова."
            : "GPS недоступен. Проверьте связь и попробуйте снова.";
        navigator.geolocation.clearWatch(watcher);
        watcher = null;
        start.disabled = false;
        stop.hidden = true;
      },
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 10000 },
    );
  });
  stop.addEventListener("click", async () => {
    sessionStorage.removeItem("courierGpsEnabled");
    if (watcher !== null) navigator.geolocation.clearWatch(watcher);
    watcher = null;
    start.disabled = false;
    stop.disabled = true;
    try {
      // Wait for an outstanding update before clearing the server position.
      while (sending) await new Promise((resolve) => setTimeout(resolve, 100));
      const response = await post(panel.dataset.stop);
      if (!response.ok) throw new Error();
      status.textContent =
        "Обновление остановлено. Координаты удалены, новые предложения приостановлены.";
      stop.hidden = true;
      lastSent = 0;
    } catch {
      status.textContent =
        "GPS остановлен, но сервер не ответил. Повторите остановку или завершите смену.";
    } finally {
      stop.disabled = false;
    }
  });
  setInterval(() => {
    if (watcher === null || document.hidden) return;
    navigator.geolocation.getCurrentPosition(
      sendPosition,
      () => {
        status.textContent =
          "Не удалось обновить GPS. Проверьте разрешение и связь.";
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 },
    );
  }, 45000);
  if (sessionStorage.getItem("courierGpsEnabled") === "yes") start.click();
  const poll = async () => {
    if (document.hidden || polling) return;
    polling = true;
    try {
      const response = await fetch(panel.dataset.live, {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!response.ok) return;
      const data = await response.json();
      if (
        String(data.offer || "") !== panel.dataset.offer ||
        String(data.state || "") !== panel.dataset.state ||
        String(data.current || "") !== panel.dataset.current ||
        !data.approved
      ) {
        update.replaceChildren();
        const link = document.createElement("a");
        link.className = "button small";
        link.href = location.pathname;
        link.textContent =
          data.offer && String(data.offer) !== panel.dataset.offer
            ? "Новое предложение · открыть →"
            : "Статус изменился · обновить →";
        update.append(link);
        document.title = "Обновление доставки — Тёпло";
      }
    } catch {
      /* The current task stays available during a temporary connection failure. */
    } finally {
      polling = false;
    }
  };
  setInterval(poll, 5000);
  document.addEventListener("visibilitychange", poll);
  window.addEventListener("pagehide", () => {
    if (watcher !== null) navigator.geolocation.clearWatch(watcher);
  });
})();
