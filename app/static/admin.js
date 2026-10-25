let me;
let users = [];
let pets = [];

async function loadStats() {
  const s = await api("/admin/stats");
  const items = [
    [s.scheduled_appointments, "запланованих прийомів"],
    [s.appointments, "записів усього"],
    [s.pets, "тварин"],
    [s.users, "користувачів"],
  ];
  document.getElementById("stats").replaceChildren(
    ...items.map(([value, label]) => el("div", { className: "panel stat" }, el("b", {}, value), el("span", {}, label))),
  );
}

async function loadUsers() {
  users = await api("/admin/users");
  pets = await api("/pets");
  const rows = document.getElementById("user-rows");
  rows.replaceChildren();
  for (const u of users) {
    const petCount = pets.filter((p) => p.owner_id === u.id).length;
    const select = el("select", {
      "aria-label": `Роль: ${u.email}`,
      disabled: u.id === me.id,  // власну роль змінити не можна (так само перевіряє бекенд)
      onchange: (e) => changeRole(u, e.target),
    }, ...Object.entries(ROLE_LABELS).map(([value, label]) =>
      el("option", { value, selected: u.role === value }, label)));
    rows.append(el("tr", {},
      el("td", {}, u.full_name, u.id === me.id ? el("span", { className: "muted" }, " (ви)") : null),
      el("td", {}, u.email),
      el("td", {}, petCount),
      el("td", {}, select)));
  }
}

async function loadAppointments() {
  const appointments = await api("/appointments");
  const rows = document.getElementById("appt-rows");
  rows.replaceChildren();
  if (appointments.length === 0) {
    rows.append(el("tr", {}, el("td", { colspan: 5, className: "empty" }, "Записів поки немає.")));
    return;
  }
  for (const a of appointments) {
    const pet = pets.find((p) => p.id === a.pet_id) || {};
    const owner = users.find((u) => u.id === pet.owner_id) || {};
    const select = el("select", {
      "aria-label": "Статус запису",
      onchange: (e) => changeStatus(a, e.target),
    }, ...Object.entries(STATUS_LABELS).map(([value, label]) =>
      el("option", { value, selected: a.status === value }, label)));
    rows.append(el("tr", {},
      el("td", {}, fmtDateTime(parseDate(a.scheduled_at))),
      el("td", {}, pet.name || `#${a.pet_id}`),
      el("td", {}, owner.full_name || "—"),
      el("td", {}, a.reason),
      el("td", {}, select)));
  }
}

async function changeRole(user, select) {
  const previous = user.role;
  try {
    const updated = await api(`/admin/users/${user.id}/role`, { method: "PATCH", json: { role: select.value } });
    user.role = updated.role;
    toast(`Роль ${user.email} змінено: ${ROLE_LABELS[updated.role]}`);
  } catch (err) {
    select.value = previous;
    toast(err.message);
  }
}

async function changeStatus(appointment, select) {
  const previous = appointment.status;
  try {
    const updated = await api(`/appointments/${appointment.id}/status`, { method: "PATCH", json: { status: select.value } });
    appointment.status = updated.status;
    toast(`Статус змінено: ${STATUS_LABELS[updated.status]}`);
    await loadStats();
  } catch (err) {
    select.value = previous;
    toast(err.message);
  }
}

(async () => {
  me = await requireUser("admin");
  if (!me) return;
  fillSidebar(me);
  await fillHomeHeader();
  await Promise.all([loadStats(), loadUsers()]);
  await loadAppointments();
})().catch((err) => toast(err.message));
