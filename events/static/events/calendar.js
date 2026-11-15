(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const months = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'];
  const monthForms = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
  const weekdays = ['Воскресенье', 'Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота'];
  const now = new Date();
  const today = iso(now.getUTCFullYear(), now.getUTCMonth() + 1, now.getUTCDate());
  const state = {year: now.getUTCFullYear(), month: now.getUTCMonth() + 1, selected: today, event: null, days: new Map(), loading: false, failed: false, request: 0, abort: null};
  let returnFocus = null;
  let pendingDelete = null;
  function iso(y, m, d) { return `${String(y).padStart(4, '0')}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`; }
  function dateOf(value) { const [y, m, d] = value.split('-').map(Number); return new Date(Date.UTC(y, m - 1, d)); }
  function addDays(value, count) { const d = dateOf(value); d.setUTCDate(d.getUTCDate() + count); return iso(d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate()); }
  function humanDate(value) { const d = dateOf(value); return `${d.getUTCDate()} ${monthForms[d.getUTCMonth()]} ${d.getUTCFullYear()}`; }
  function rangeForMonth() {
    const first = new Date(Date.UTC(state.year, state.month - 1, 1));
    const offset = (first.getUTCDay() + 6) % 7;
    const count = Math.max(35, Math.ceil((offset + new Date(Date.UTC(state.year, state.month, 0)).getUTCDate()) / 7) * 7);
    const start = addDays(iso(state.year, state.month, 1), -offset);
    return {start, end: addDays(start, count - 1), count};
  }
  function element(tag, className, text) { const el = document.createElement(tag); if (className) el.className = className; if (text !== undefined) el.textContent = text; return el; }
  function setStatus(text, loading = false) { const el = $('status-line'); $('status-message').textContent = text; $('retry-load').hidden = !text || loading; el.classList.toggle('loading', loading); }
  function eventsFor(day) { return state.days.get(day) || []; }
  function selectDay(day, showList = false) {
    state.selected = day; state.event = null;
    const d = dateOf(day); if (d.getUTCFullYear() !== state.year || d.getUTCMonth() + 1 !== state.month) { state.year = d.getUTCFullYear(); state.month = d.getUTCMonth() + 1; loadMonth(); return; }
    render(); if (showList) $('day-list').scrollIntoView({behavior: 'smooth', block: 'nearest'});
  }
  function selectEvent(event) { state.event = event; renderDetails(); }
  function renderMini() {
    $('mini-title').textContent = `${months[state.month - 1][0].toUpperCase()}${months[state.month - 1].slice(1)} ${state.year}`;
    const grid = $('mini-grid'); grid.replaceChildren(); const {start, count} = rangeForMonth();
    for (let i = 0; i < count; i++) { const day = addDays(start, i), d = dateOf(day); const b = element('button', '', String(d.getUTCDate())); b.type = 'button'; b.setAttribute('aria-label', humanDate(day)); b.classList.toggle('muted', d.getUTCMonth() + 1 !== state.month); b.classList.toggle('today', day === today); b.classList.toggle('selected', day === state.selected); b.addEventListener('click', () => selectDay(day)); grid.append(b); }
  }
  function renderGrid() {
    const grid = $('month-grid'); grid.replaceChildren(); const {start, count} = rangeForMonth();
    for (let i = 0; i < count; i++) {
      const day = addDays(start, i), d = dateOf(day), events = eventsFor(day); const cell = element('div', 'day-cell');
      cell.classList.toggle('outside', d.getUTCMonth() + 1 !== state.month); cell.classList.toggle('selected', day === state.selected);
      const dayButton = element('button', 'day-number', String(d.getUTCDate())); dayButton.type = 'button'; dayButton.setAttribute('aria-label', humanDate(day)); dayButton.classList.toggle('today', day === today); dayButton.addEventListener('click', () => selectDay(day)); cell.append(dayButton);
      for (const event of events.slice(0, 2)) { const button = element('button', 'cell-event'); button.type = 'button'; button.title = `${event.time} UTC · ${event.name}`; const time = element('span', 'time', event.time); button.append(time, document.createTextNode(event.name)); button.addEventListener('click', () => {selectDay(day); selectEvent(event);}); cell.append(button); }
      if (events.length > 2) { const more = element('button', 'more-button', `Ещё ${events.length - 2}`); more.type = 'button'; more.addEventListener('click', () => selectDay(day, true)); cell.append(more); }
      grid.append(cell);
    }
  }
  function renderDetails() {
    const d = dateOf(state.selected), events = eventsFor(state.selected);
    $('selected-date-title').textContent = `${d.getUTCDate()} ${monthForms[d.getUTCMonth()]}`;
    $('selected-date-meta').textContent = `${weekdays[d.getUTCDay()]}, ${d.getUTCFullYear()} · UTC`;
    $('day-count').textContent = String(events.length);
    const list = $('day-list'); list.replaceChildren();
    if (!events.length) { const empty = element('div', 'empty-state'); const icon = element('span', 'empty-icon', '◇'); empty.append(icon, document.createTextNode(state.loading ? 'Загружаем события…' : state.failed ? 'Не удалось загрузить события.' : 'В этот день событий нет.')); list.append(empty); }
    for (const event of events) { const button = element('button', 'day-item'); button.type = 'button'; button.classList.toggle('active', state.event?.id === event.id); button.append(element('span', 'event-bar')); const copy = element('span'); copy.append(element('strong', '', event.name), element('small', '', `${event.time} UTC`)); button.append(copy); button.addEventListener('click', () => selectEvent(event)); list.append(button); }
    const detail = $('event-detail'); detail.replaceChildren(); detail.hidden = !state.event;
    if (state.event) {
      detail.append(element('h3', '', state.event.name), element('p', '', `${humanDate(state.selected)} · ${state.event.time} UTC`));
      const actions = element('div', 'detail-actions');
      const rename = element('button', '', 'Переименовать это повторение'); rename.type = 'button'; rename.addEventListener('click', openRename);
      const one = element('button', 'danger-text', 'Удалить только эту дату'); one.type = 'button'; one.addEventListener('click', () => openDelete('one'));
      const next = element('button', 'danger-text', 'Удалить эту и следующие даты'); next.type = 'button'; next.addEventListener('click', () => openDelete('next'));
      actions.append(rename, one, next); detail.append(actions);
    }
  }
  function render() {
    $('month-title').textContent = `${months[state.month - 1][0].toUpperCase()}${months[state.month - 1].slice(1)} ${state.year}`;
    $('month-subtitle').textContent = state.loading ? 'Загружаем события…' : 'События и повторения на месяц';
    renderMini(); renderGrid(); renderDetails();
  }
  async function loadMonth(afterSave = false) {
    const ticket = ++state.request; if (state.abort) state.abort.abort(); state.abort = new AbortController();
    const {start, end} = rangeForMonth(); state.loading = true; state.failed = false; state.days = new Map(); setStatus('Загружаем календарь…', true); render();
    try {
      const response = await fetch(`/events/range/?start=${start}&end=${end}`, {signal: state.abort.signal});
      if (!response.ok) throw new Error('Не удалось загрузить календарь. Попробуйте ещё раз.');
      const body = await response.json(); if (ticket !== state.request) return;
      state.days = new Map(body.days.map(day => [day.date, day.events])); state.loading = false; state.failed = false; setStatus('');
      if (state.event) state.event = eventsFor(state.selected).find(event => event.id === state.event.id) || null;
      render();
    } catch (error) {
      if (ticket !== state.request || error.name === 'AbortError') return;
      state.loading = false; state.failed = true; setStatus(afterSave ? 'Изменение сохранено, но календарь не удалось обновить. Повторите загрузку.' : 'Не удалось загрузить календарь. Проверьте соединение и повторите попытку.'); render();
    }
  }
  function changeMonth(delta) { const d = new Date(Date.UTC(state.year, state.month - 1 + delta, 1)); state.year = d.getUTCFullYear(); state.month = d.getUTCMonth() + 1; state.selected = iso(state.year, state.month, 1); state.event = null; loadMonth(); }
  function openDialog(dialog) { returnFocus = document.activeElement; dialog.showModal(); const field = dialog.querySelector('input,button'); if (field) field.focus(); }
  function closeDialog(dialog) { dialog.close(); }
  for (const dialog of document.querySelectorAll('dialog')) { dialog.addEventListener('close', () => { if (returnFocus?.isConnected) returnFocus.focus(); returnFocus = null; }); dialog.addEventListener('click', event => { if (event.target === dialog) closeDialog(dialog); }); for (const button of dialog.querySelectorAll('[data-close]')) button.addEventListener('click', () => closeDialog(dialog)); }
  function errorAt(id, message) { const el = $(id); el.textContent = message; el.hidden = !message; }
  async function post(path, payload) {
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
    const response = await fetch(path, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', ...(csrfToken ? {'X-CSRFToken': csrfToken} : {})},
      body: payload === undefined ? undefined : JSON.stringify(payload),
    });
    if (!response.ok) {
      const message = response.status === 404 ? 'Это повторение больше недоступно. Обновите календарь.'
        : response.status === 400 ? 'Проверьте введённые данные.'
        : 'Не удалось сохранить изменения. Попробуйте ещё раз.';
      throw new Error(message);
    }
    return response;
  }
  $('create-button').addEventListener('click', () => { $('event-form').reset(); $('event-date').value = state.selected; $('event-time').value = '09:00'; $('custom-period-wrap').hidden = true; errorAt('event-error', ''); openDialog($('event-dialog')); $('event-name').focus(); });
  $('event-repeat').addEventListener('change', () => { $('custom-period-wrap').hidden = $('event-repeat').value !== 'custom'; });
  $('event-form').addEventListener('submit', async event => {
    event.preventDefault();
    const button = $('save-event');
    if (button.disabled) return;
    const name = $('event-name').value.trim();
    const day = $('event-date').value;
    const time = $('event-time').value;
    if (!name || !day || !/^\d{2}:\d{2}$/.test(time)) {
      errorAt('event-error', 'Заполните название, дату и время.');
      return;
    }
    const repeat = $('event-repeat').value;
    const period = repeat === 'once' ? null : repeat === 'daily' ? 1
      : repeat === 'weekly' ? 7 : Number($('event-period').value);
    if (repeat === 'custom' && (!Number.isSafeInteger(period) || period < 1)) {
      errorAt('event-error', 'Период должен быть целым числом дней больше нуля.');
      return;
    }
    const [year, month, date] = day.split('-').map(Number);
    const [hour, minute] = time.split(':').map(Number);
    const start_at = Math.floor(Date.UTC(year, month - 1, date, hour, minute) / 1000);
    if (!Number.isSafeInteger(start_at)) {
      errorAt('event-error', 'Дата или время указаны неверно.');
      return;
    }
    button.disabled = true;
    errorAt('event-error', '');
    try {
      await post('/add/', {name, start_at, period});
    } catch (error) {
      errorAt('event-error', error.message || 'Проверьте соединение и повторите попытку.');
      button.disabled = false;
      return;
    }
    button.disabled = false;
    closeDialog($('event-dialog'));
    state.year = year;
    state.month = month;
    state.selected = day;
    state.event = null;
    await loadMonth(true);
  });
  function occurrencePath(kind) { const [y, m, d] = state.selected.split('-').map(Number); return `/${kind}/${state.event.id}/${y}/${m}/${d}/`; }
  function openRename() { if (!state.event) return; $('rename-name').value = state.event.name; errorAt('rename-error', ''); openDialog($('rename-dialog')); $('rename-name').focus(); }
  $('rename-form').addEventListener('submit', async event => {
    event.preventDefault();
    const button = $('save-rename');
    if (button.disabled || !state.event) return;
    const name = $('rename-name').value.trim();
    if (!name) {
      errorAt('rename-error', 'Введите название события.');
      return;
    }
    button.disabled = true;
    errorAt('rename-error', '');
    try {
      await post(occurrencePath('update'), {name});
    } catch (error) {
      errorAt('rename-error', error.message || 'Проверьте соединение и повторите попытку.');
      button.disabled = false;
      return;
    }
    button.disabled = false;
    closeDialog($('rename-dialog'));
    await loadMonth(true);
  });
  function openDelete(scope) { if (!state.event) return; pendingDelete = {scope, path: occurrencePath(scope === 'one' ? 'remove' : 'remove-next')}; $('delete-copy').textContent = `«${state.event.name}», ${humanDate(state.selected)}. ${scope === 'one' ? 'Будет удалено только это повторение.' : 'Будут удалены это повторение и все последующие в серии.'}`; errorAt('delete-error', ''); openDialog($('delete-dialog')); }
  $('confirm-delete').addEventListener('click', async () => {
    const button = $('confirm-delete');
    if (button.disabled || !pendingDelete) return;
    button.disabled = true;
    errorAt('delete-error', '');
    try {
      await post(pendingDelete.path);
    } catch (error) {
      errorAt('delete-error', error.message || 'Проверьте соединение и повторите попытку.');
      button.disabled = false;
      return;
    }
    button.disabled = false;
    closeDialog($('delete-dialog'));
    pendingDelete = null;
    state.event = null;
    await loadMonth(true);
  });
  for (const id of ['prev-month', 'mini-prev']) $(id).addEventListener('click', () => changeMonth(-1));
  for (const id of ['next-month', 'mini-next']) $(id).addEventListener('click', () => changeMonth(1));
  $('today-button').addEventListener('click', () => { const d = dateOf(today); state.year = d.getUTCFullYear(); state.month = d.getUTCMonth() + 1; state.selected = today; state.event = null; loadMonth(); });
  $('retry-load').addEventListener('click', () => loadMonth());
  loadMonth();
})();
