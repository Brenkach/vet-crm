let pets = [];

async function loadPets() {
  pets = await api("/pets");
  const list = document.getElementById("pet-list");
  list.replaceChildren();
  if (pets.length === 0) {
    list.append(el("li", { className: "panel empty" }, "Додайте першу тварину, щоб записатися на прийом."));
  }
  for (const pet of pets) {
    const details = [pet.species, pet.breed].filter(Boolean).join(", ");
    list.append(el("li", { className: "panel pet" },
      el("h3", {}, pet.name),
      el("span", { className: "muted" }, details),
      pet.birth_date ? el("span", { className: "muted" }, `Народився ${new Date(pet.birth_date).toLocaleDateString("uk-UA")}`) : null,
      el("div", { className: "pet-actions" },
        el("button", { className: "btn btn-danger btn-small", type: "button", onclick: () => deletePet(pet) }, "Видалити")),
    ));
  }

  const select = document.querySelector("#appt-form select[name=pet_id]");
  select.replaceChildren(...pets.map((p) => el("option", { value: p.id }, p.name)));
  document.querySelector("#appt-form button").disabled = pets.length === 0;
}

async function loadAppointments() {
  const appointments = await api("/appointments");
  const list = document.getElementById("appt-list");
  list.replaceChildren();
  if (appointments.length === 0) {
    list.append(el("li", { className: "empty" }, "Записів ще немає. Оберіть тварину і час нижче."));
    return;
  }
  const petName = (id) => (pets.find((p) => p.id === id) || {}).name || `#${id}`;
  const now = new Date();
  for (const a of appointments) {
    const date = parseDate(a.scheduled_at);
    list.append(el("li", { className: `appt${date < now ? " is-past" : ""}` },
      el("div", { className: "appt-date" },
        el("span", { className: "day" }, date.getDate()),
        el("span", { className: "mon" }, `${MONTHS[date.getMonth()]} ${date.getFullYear()}`)),
      el("div", { className: "appt-body" },
        el("p", {}, el("strong", {}, petName(a.pet_id)), `, о ${fmtTime(date)}`),
        el("p", { className: "muted" }, a.reason)),
      el("div", { className: "appt-side" },
        statusBadge(a.status),
        a.status === "scheduled"
          ? el("button", { className: "btn btn-danger btn-small", type: "button", onclick: () => cancelAppointment(a) }, "Скасувати")
          : null),
    ));
  }
}

async function deletePet(pet) {
  if (!confirm(`Видалити ${pet.name}? Записи цієї тварини теж буде видалено.`)) return;
  try {
    await api(`/pets/${pet.id}`, { method: "DELETE" });
    toast(`${pet.name} видалено`);
    await loadPets();
    await loadAppointments();
  } catch (err) { toast(err.message); }
}

async function cancelAppointment(a) {
  if (!confirm("Скасувати цей запис?")) return;
  try {
    await api(`/appointments/${a.id}/cancel`, { method: "POST" });
    toast("Запис скасовано");
    await loadAppointments();
  } catch (err) { toast(err.message); }
}

function bindForm(form, handler) {
  const error = form.querySelector(".form-error");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    if (!form.checkValidity()) { showError(error, new Error("Заповніть обов'язкові поля")); return; }
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try { await handler(new FormData(form)); form.reset(); } catch (err) { showError(error, err); }
    finally { button.disabled = false; }
  });
}

bindForm(document.getElementById("pet-form"), async (data) => {
  const name = data.get("name");
  await api("/pets", {
    method: "POST",
    json: {
      name,
      species: data.get("species"),
      breed: data.get("breed") || null,
      birth_date: data.get("birth_date") || null,
    },
  });
  toast(`${name} додано`);
  await loadPets();
});

bindForm(document.getElementById("appt-form"), async (data) => {
  await api("/appointments", {
    method: "POST",
    json: {
      pet_id: Number(data.get("pet_id")),
      scheduled_at: new Date(data.get("scheduled_at")).toISOString(),
      reason: data.get("reason"),
    },
  });
  toast("Ви записані на прийом");
  await loadAppointments();
});

(async () => {
  const me = await requireUser("client");
  if (!me) return;
  fillSidebar(me);
  await fillHomeHeader();
  await loadPets();
  await loadAppointments();
})().catch((err) => toast(err.message));
