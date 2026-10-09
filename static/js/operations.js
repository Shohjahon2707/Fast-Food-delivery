(() => {
  const panel = document.querySelector("[data-operations-alerts]");
  if (!panel) return;
  let busy = false;
  setInterval(async () => {
    if (document.hidden || busy) return;
    busy = true;
    try {
      const response = await fetch(panel.dataset.operationsAlerts, {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!response.ok) return;
      const data = await response.json();
      panel.querySelector("[data-alert-count]").textContent = data.count;
      panel.querySelector("[data-worker-health]").textContent = !data.configured
        ? "Укажите адрес и координаты кухни в настройках."
        : !data.healthy
          ? "Диспетчер давно не отвечал. Проверьте процесс worker."
          : "Автоматический диспетчер работает.";
      document.title = data.count
        ? `(${data.count}) Нужна помощь — Тёпло`
        : "Контроль сервиса — Тёпло";
    } catch {
      panel.querySelector("[data-worker-health]").textContent =
        "Не удалось обновить уведомления. Проверьте соединение.";
    } finally {
      busy = false;
    }
  }, 10000);
})();
