(() => {
  const el = document.querySelector("#delivery-map");
  if (!el) return;
  const panel = el.closest("details");
  const lat = document.querySelector("[name=latitude]");
  const lon = document.querySelector("[name=longitude]");
  const status = document.querySelector("[data-map-status]");
  const number = (value) => Number(String(value).replace(",", "."));
  let map, marker;
  const setPoint = (latitude, longitude) => {
    lat.value = latitude.toFixed(6);
    lon.value = longitude.toFixed(6);
    if (marker) marker.setLatLng([latitude, longitude]);
    else marker = L.marker([latitude, longitude]).addTo(map);
    status.textContent =
      "Точка сохранена. Укажите квартиру и подъезд в адресе.";
  };
  const initialize = () => {
    if (map) {
      map.invalidateSize();
      return;
    }
    if (!window.L) {
      status.textContent = "Карта недоступна. Можно оформить заказ по адресу.";
      return;
    }
    const configured = el.dataset.lat !== "" && el.dataset.lon !== "";
    const existing = lat.value !== "" && lon.value !== "";
    const center = existing
      ? [number(lat.value), number(lon.value)]
      : configured
        ? [number(el.dataset.lat), number(el.dataset.lon)]
        : [20, 0];
    map = L.map(el, { scrollWheelZoom: false }).setView(
      center,
      existing || configured ? 15 : 2,
    );
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    })
      .addTo(map)
      .on("tileerror", () => {
        status.textContent =
          "Подложка карты недоступна. Укажите адрес или используйте своё местоположение.";
      });
    map.on("click", (event) => setPoint(event.latlng.lat, event.latlng.lng));
    if (existing) setPoint(...center);
  };
  panel.addEventListener("toggle", () => {
    if (panel.open) initialize();
  });
  document
    .querySelector("[data-locate-customer]")
    .addEventListener("click", () => {
      initialize();
      if (!map) return;
      if (!navigator.geolocation) {
        status.textContent =
          "Браузер не поддерживает геопозицию. Укажите адрес.";
        return;
      }
      status.textContent = "Определяем местоположение…";
      navigator.geolocation.getCurrentPosition(
        (position) => {
          const { latitude, longitude, accuracy } = position.coords;
          map.setView([latitude, longitude], 16);
          setPoint(latitude, longitude);
          if (accuracy > 200)
            status.textContent =
              "Позиция приблизительная. Передвиньте точку нажатием на карте.";
        },
        () => {
          status.textContent =
            "Местоположение недоступно. Поставьте точку вручную или оставьте только адрес.";
        },
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 },
      );
    });
  document.querySelector("[data-clear-point]").addEventListener("click", () => {
    lat.value = "";
    lon.value = "";
    if (marker) {
      marker.remove();
      marker = null;
    }
    status.textContent = "Точка убрана. Заказ оформится по указанному адресу.";
  });
})();
