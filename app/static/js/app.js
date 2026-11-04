/* No inline scripts are used (strict Content-Security-Policy); everything lives here. */
document.addEventListener('submit', function (e) {
  var msg = e.target.getAttribute('data-confirm');
  if (msg && !window.confirm(msg)) { e.preventDefault(); }
});
document.addEventListener('click', function (e) {
  if (e.target.closest('[data-print]')) { window.print(); }
  var t = e.target.closest('[data-toggle-sidebar]');
  if (t) { document.getElementById('sidebar').classList.toggle('open'); }
});
/* Payment page: show only the fields for the chosen method */
(function () {
  var sel = document.querySelector('[data-method-select]');
  if (!sel) return;
  function update() {
    document.querySelectorAll('[data-method-group]').forEach(function (g) {
      var on = g.getAttribute('data-method-group') === sel.value;
      g.style.display = on ? '' : 'none';
      g.querySelectorAll('input').forEach(function (i) { i.disabled = !on; });
    });
  }
  sel.addEventListener('change', update); update();
})();
/* Treatment form: show only the charge fields that belong to the chosen type */
(function () {
  var sel = document.querySelector('[data-treatment-type]');
  if (!sel) return;
  function update() {
    document.querySelectorAll('[data-for-type]').forEach(function (g) {
      g.style.display = g.getAttribute('data-for-type').split(' ').indexOf(sel.value) >= 0 ? '' : 'none';
    });
  }
  sel.addEventListener('change', update); update();
})();
/* Admin dashboard charts */
(function () {
  var holder = document.getElementById('chart-data');
  if (!holder || typeof Chart === 'undefined') return;
  var d = JSON.parse(holder.getAttribute('data-chart'));
  var teal = '#0f9d9a', navy = '#0b2a4a';
  var s = document.getElementById('statusChart');
  if (s) new Chart(s, {type: 'doughnut', data: {labels: d.status_labels, datasets: [{data: d.status_values,
    backgroundColor: ['#e0a100', '#123a63', '#2e9e6b', '#8a97a6', '#d64550']}]}, options: {plugins: {legend: {position: 'bottom'}}}});
  var r = document.getElementById('revenueChart');
  if (r) new Chart(r, {type: 'bar', data: {labels: d.days, datasets: [{label: 'Payments received (₹)', data: d.revenue,
    backgroundColor: teal, borderRadius: 6}]}, options: {plugins: {legend: {display: false}}, scales: {y: {beginAtZero: true}}}});
})();
