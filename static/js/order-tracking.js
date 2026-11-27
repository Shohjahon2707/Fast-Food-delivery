(() => {
  const panel = document.querySelector("[data-courier-tracking]");
  const order = document.querySelector("[data-live-order]");
  if (!panel || !order || !window.L) return;
  const canvas = panel.querySelector("[data-tracking-map]");
  const status = panel.querySelector("[data-tracking-status]");
  let position, map, marker;
  function draw() {
    canvas.hidden = !position;
    const text = position ? panel.dataset.current : panel.dataset.waiting;
    if (status.textContent !== text) status.textContent = text;
    if (!panel.open || !position) return;
    if (!map) {
      map = L.map(canvas, { scrollWheelZoom: false }).setView(position, 15);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19,
      }).addTo(map);
      marker = L.marker(position).addTo(map);
    } else {
      map.invalidateSize();
      marker.setLatLng(position);
      if (!map.getBounds().contains(position)) map.panTo(position);
    }
  }
  order.addEventListener("order:location", (event) => {
    position = event.detail;
    draw();
  });
  panel.addEventListener("toggle", draw);
})();
