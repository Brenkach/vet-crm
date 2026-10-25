// Спільні функції для всіх сторінок: запити до API, токен, перевірка ролі
const TOKEN_KEY = "vetcrm_token";

const STATUS_LABELS = { scheduled: "Заплановано", completed: "Завершено", cancelled: "Скасовано" };
const ROLE_LABELS = { admin: "Адміністратор", client: "Клієнт" };
const MONTHS = ["січ", "лют", "бер", "квіт", "трав", "черв", "лип", "серп", "вер", "жовт", "лист", "груд"];

function getToken() { return localStorage.getItem(TOKEN_KEY); }
function setToken(token) { localStorage.setItem(TOKEN_KEY, token); }
function logout() { localStorage.removeItem(TOKEN_KEY); location.href = "login.html"; }

class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

function errorMessage(data, status) {
  if (!data || !data.detail) return `Помилка сервера (${status})`;
    // 500 у production: без технічних подробиць, лише код для звернення в підтримку
  if (data.error_id) return `${data.detail} Код помилки: ${data.error_id}`;
  if (typeof data.detail === "string") return data.detail;
  // 422 від FastAPI: список помилок валідації
  return data.detail.map((e) => {
    const field = e.loc[e.loc.length - 1];
    if (field === "password") return "Пароль має містити щонайменше 8 символів";
    if (field === "email") return "Вкажіть коректний email";
    return `${field}: ${e.msg}`;
  }).join(". ");
}

async function api(path, { method = "GET", json, form } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let body;
  if (json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
  if (form !== undefined) { body = new URLSearchParams(form); }

  const resp = await fetch(path, { method, headers, body });
  if (resp.status === 204) return null;
  const data = await resp.json().catch(() => null);
  if (!resp.ok) throw new ApiError(resp.status, errorMessage(data, resp.status));
  return data;
}

function homeFor(role) { return role === "admin" ? "admin.html" : "client.html"; }

// Перевірка на клієнті — лише для зручності. Справжній захист — у бекенді (401/403).
async function requireUser(expectedRole) {
  if (!getToken()) { location.href = "login.html"; return null; }
  try {
    const me = await api("/users/me");
    if (expectedRole && me.role !== expectedRole) { location.href = homeFor(me.role); return null; }
    return me;
  } catch (err) {
    if (err.status === 401) logout();
    throw err;
  }
}

// Безпечне створення елементів (textContent замість innerHTML — без XSS)
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "className") node.className = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : String(child));
  }
  return node;
}

// Сервер зберігає час в UTC; SQLite може повернути його без позначки зони
function parseDate(iso) { return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + "Z"); }
function fmtTime(d) { return d.toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" }); }
function fmtDateTime(d) { return d.toLocaleString("uk-UA", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }); }

function statusBadge(status) {
  return el("span", { className: `status status-${status}` }, STATUS_LABELS[status] || status);
}

function showError(box, err) { box.textContent = err.message || String(err); box.hidden = false; }

let toastTimer;
function toast(text) {
  let node = document.querySelector(".toast");
  if (!node) { node = el("div", { className: "toast", role: "status" }); document.body.append(node); }
  node.textContent = text;
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, 2500);
}

function fillSidebar(me) {
  document.getElementById("who-name").textContent = me.full_name;
  document.getElementById("who-email").textContent = me.email;
  document.getElementById("who-role").textContent = ROLE_LABELS[me.role] || me.role;
  document.getElementById("logout").addEventListener("click", logout);
}

async function fillHomeHeader() {
  const home = await api("/home");
  document.getElementById("page-title").textContent = home.title;
  document.getElementById("page-message").textContent = home.message;
}


// Позначка тестового середовища, щоб sandbox не сплутати з робочою версією
(async () => {
  try {
    const resp = await fetch("/health");
    const info = await resp.json();
    if (info.environment === "sandbox") {
      document.body.prepend(el("div", { className: "env-banner", role: "note" },
        "Тестове середовище (sandbox): дані тут не потрапляють у робочу систему"));
    }
  } catch (e) { /* банер не критичний */ }
})();
