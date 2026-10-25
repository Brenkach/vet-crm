"""Генерація первинного звіту з результатів Locust і моніторингу ресурсів.

Можна перегенерувати звіт для вже проведеного тесту:
    python loadtest/report.py baseline
"""

import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
AUTH_ENDPOINTS = ("POST /auth/login", "POST /auth/register")


# ---------- Читання даних ----------
def num(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None  # Locust пише "N/A", поки немає даних


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as file:
        return list(csv.DictReader(file))


def load(out_dir: Path):
    stats = read_csv(out_dir / "locust_stats.csv")
    history = [r for r in read_csv(out_dir / "locust_stats_history.csv") if r["Name"] == "Aggregated"]
    failures = read_csv(out_dir / "locust_failures.csv")
    resources = read_csv(out_dir / "resources.csv")
    return stats, history, failures, resources


# ---------- Обчислення ----------
def endpoint_rows(stats):
    rows = []
    for r in stats:
        count = int(r["Request Count"])
        fails = int(r["Failure Count"])
        rows.append(
            {
                "name": "**Усього (Aggregated)**" if r["Name"] == "Aggregated" else r["Name"],
                "aggregated": r["Name"] == "Aggregated",
                "count": count,
                "fails": fails,
                "error_rate": 100.0 * fails / count if count else 0.0,
                "rps": num(r["Requests/s"]) or 0.0,
                "avg": num(r["Average Response Time"]) or 0.0,
                "min": num(r["Min Response Time"]) or 0.0,
                "max": num(r["Max Response Time"]) or 0.0,
                "p50": num(r["50%"]) or 0.0,
                "p95": num(r["95%"]) or 0.0,
                "p99": num(r["99%"]) or 0.0,
            }
        )
    rows.sort(key=lambda row: (row["aggregated"], -row["p95"]))
    return rows


def resource_summary(resources, start: Optional[float] = None, end: Optional[float] = None):
    samples = [
        r
        for r in resources
        if (start is None or num(r["timestamp"]) >= start) and (end is None or num(r["timestamp"]) <= end)
    ]
    if not samples:
        return None
    cpu = [num(r["server_cpu_percent"]) for r in samples]
    ram = [num(r["server_rss_mb"]) for r in samples]
    sys_cpu = [num(r["system_cpu_percent"]) for r in samples]
    return {
        "cpu_avg": statistics.mean(cpu),
        "cpu_max": max(cpu),
        "ram_avg": statistics.mean(ram),
        "ram_max": max(ram),
        "sys_cpu_avg": statistics.mean(sys_cpu),
        "sys_cpu_max": max(sys_cpu),
        "sys_mem_max": max(num(r["system_mem_percent"]) for r in samples),
    }


def series(history):
    points = []
    for r in history:
        ts, users = num(r["Timestamp"]), num(r["User Count"])
        if ts is None or users is None:
            continue
        points.append(
            {
                "ts": ts,
                "users": int(users),
                "rps": num(r["Requests/s"]) or 0.0,
                "fails": num(r["Failures/s"]) or 0.0,
                "p50": num(r["50%"]),
                "p95": num(r["95%"]),
            }
        )
    return points


def stage_rows(points, resources, stages: List[int]):
    rows = []
    for target in stages:
        stable = [p for p in points if p["users"] == target and p["p95"] is not None]
        if len(stable) > 2:
            stable = stable[1:]  # перша точка ще захоплює розгін
        if not stable:
            continue
        total_rps = statistics.median(p["rps"] for p in stable)
        fail_rps = statistics.median(p["fails"] for p in stable)
        rows.append(
            {
                "users": target,
                "rps": total_rps,
                "p50": statistics.median(p["p50"] for p in stable if p["p50"] is not None),
                "p95": statistics.median(p["p95"] for p in stable),
                "p95_max": max(p["p95"] for p in stable),
                "error_rate": 100.0 * fail_rps / total_rps if total_rps else 0.0,
                "res": resource_summary(resources, stable[0]["ts"], stable[-1]["ts"]),
            }
        )
    return rows


# ---------- Графіки ----------
def _users_axis(ax, t, points):
    twin = ax.twinx()
    twin.plot(t, [p["users"] for p in points], color="gray", linestyle="--", linewidth=1, label="VUsers")
    twin.set_ylabel("Віртуальні користувачі")
    twin.set_ylim(bottom=0)
    return twin


def _save(fig, ax, twin, path):
    lines, labels = ax.get_legend_handles_labels()
    if twin is not None:
        extra_lines, extra_labels = twin.get_legend_handles_labels()
        lines, labels = lines + extra_lines, labels + extra_labels
    ax.legend(lines, labels, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=len(labels), frameon=False)
    ax.grid(alpha=0.3, which="both")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def make_charts(out_dir: Path, points, resources, rows) -> List[str]:
    charts = []
    if points:
        t0 = points[0]["ts"]
        t = [p["ts"] - t0 for p in points]

        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.plot(t, [p["p50"] for p in points], label="Медіана (p50)", color="#3f7262")
        ax.plot(t, [p["p95"] for p in points], label="95-й перцентиль (p95)", color="#b4473d")
        ax.set(
            title="Динаміка часу відповіді", xlabel="Час від початку тесту, с", ylabel="Час відповіді, мс (лог. шкала)"
        )
        # логарифмічна шкала: сплески в секунди і звичайні мілісекунди видно на одному графіку
        ax.set_yscale("log")
        _save(fig, ax, _users_axis(ax, t, points), out_dir / "response_time.png")
        charts.append(("Динаміка часу відповіді", "response_time.png"))

        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.plot(t, [p["rps"] for p in points], label="Запити/с (RPS)", color="#3f7262")
        ax.plot(t, [p["fails"] for p in points], label="Помилки/с", color="#b4473d")
        ax.set(title="Пропускна здатність", xlabel="Час від початку тесту, с", ylabel="Запитів за секунду")
        ax.set_ylim(bottom=0)
        _save(fig, ax, _users_axis(ax, t, points), out_dir / "throughput.png")
        charts.append(("Пропускна здатність", "throughput.png"))

    if resources:
        t0 = num(resources[0]["timestamp"])
        t = [num(r["timestamp"]) - t0 for r in resources]
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
        ax1.plot(t, [num(r["server_cpu_percent"]) for r in resources], label="CPU процесу сервера", color="#b9821f")
        ax1.plot(t, [num(r["system_cpu_percent"]) for r in resources], label="CPU системи", color="gray", alpha=0.6)
        ax1.axhline(100, color="#b4473d", linestyle=":", linewidth=1, label="100% = одне ядро")
        ax1.set(title="Ресурси сервера", ylabel="CPU, %")
        ax1.set_ylim(bottom=0)
        ax1.legend(loc="upper left")
        ax1.grid(alpha=0.3)
        ax2.plot(t, [num(r["server_rss_mb"]) for r in resources], label="RAM процесу сервера", color="#3f7262")
        ax2.set(xlabel="Час від початку тесту, с", ylabel="RAM, МБ")
        ax2.set_ylim(bottom=0)
        ax2.legend(loc="upper left")
        ax2.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(out_dir / "resources.png", dpi=120)
        plt.close(fig)
        charts.append(("Ресурси сервера (CPU, RAM)", "resources.png"))

    endpoint_data = [r for r in rows if not r["aggregated"]]
    if endpoint_data:
        endpoint_data = sorted(endpoint_data, key=lambda r: r["p95"])
        fig, ax = plt.subplots(figsize=(10, 0.45 * len(endpoint_data) + 1.5))
        names = [r["name"] for r in endpoint_data]
        ax.barh(names, [r["p95"] for r in endpoint_data], color="#b4473d", alpha=0.8, label="p95")
        ax.barh(names, [r["avg"] for r in endpoint_data], color="#3f7262", label="Середній")
        ax.set(title="Час відповіді за ендпоінтами", xlabel="мс")
        ax.legend(loc="lower right")
        ax.grid(alpha=0.3, axis="x")
        fig.tight_layout()
        fig.savefig(out_dir / "endpoints.png", dpi=120)
        plt.close(fig)
        charts.append(("Час відповіді за ендпоінтами", "endpoints.png"))
    return charts


# ---------- Вузькі місця ----------
def find_bottlenecks(rows, points, stages, res, failures) -> List[str]:
    notes = []
    total = next((r for r in rows if r["aggregated"]), None)
    endpoints = [r for r in rows if not r["aggregated"] and r["count"] > 0]

    if total and total["error_rate"] > 1:
        bad = ", ".join(f"`{r['name']}` ({r['error_rate']:.1f}%)" for r in endpoints if r["fails"])
        notes.append(
            f"**Помилки.** Загальний Error Rate {total['error_rate']:.2f}% перевищує 1%. Ендпоінти з помилками: {bad}."
        )
    elif total and total["fails"]:
        notes.append(
            f"**Поодинокі помилки.** Невдалих запитів: {total['fails']} ({total['error_rate']:.2f}%) — "
            "див. таблицю помилок."
        )

    auth = [r for r in endpoints if r["name"] in AUTH_ENDPOINTS]
    others = [r for r in endpoints if r["name"] not in AUTH_ENDPOINTS]
    if auth and others:
        auth_p95 = max(r["p95"] for r in auth)
        others_p95 = statistics.median(r["p95"] for r in others)
        if others_p95 and auth_p95 > 3 * others_p95:
            notes.append(
                f"**Автентифікація — найдорожча операція.** p95 входу/реєстрації {auth_p95:.0f} мс проти "
                f"{others_p95:.0f} мс (медіана p95 інших ендпоінтів). Ймовірна причина: хешування паролів bcrypt "
                "навмисно повільне і виконується синхронно всередині async-обробника, тож блокує цикл подій — "
                "поки рахується хеш, сервер не обробляє жодного іншого запиту. Можливе рішення: виконувати bcrypt "
                "у пулі потоків (`run_in_threadpool`) і/або запускати кілька воркерів uvicorn."
            )

    valid = [p for p in points if p["p95"] is not None]
    if len(valid) > 5:
        peak = max(valid, key=lambda p: p["p95"])
        typical = statistics.median(p["p95"] for p in valid)
        if typical and peak["p95"] > 3 * typical:
            changes = [
                b["ts"] for a, b in zip(points, points[1:]) if b["users"] != a["users"] and b["ts"] <= peak["ts"]
            ]
            ramping = bool(changes) and peak["ts"] - changes[-1] <= 30
            when = (
                "під час розгону або одразу після нього, коли нові користувачі масово реєструються та входять"
                if ramping
                else "при стабільній кількості користувачів"
            )
            notes.append(
                f"**Сплеск затримки.** p95 зріс до {peak['p95']:.0f} мс (типове значення {typical:.0f} мс) "
                f"при {peak['users']} VUsers, {when}."
            )

    if len(stages) >= 2:
        base = stages[0]
        degraded = next((s for s in stages[1:] if s["p95"] > 2 * base["p95"] or s["error_rate"] > 1), None)
        if degraded:
            notes.append(
                f"**Точка деградації.** Від {degraded['users']} VUsers p95 стабільного режиму становить "
                f"{degraded['p95']:.0f} мс проти {base['p95']:.0f} мс при {base['users']} VUsers"
                + (f", Error Rate {degraded['error_rate']:.1f}%." if degraded["error_rate"] > 1 else ".")
            )
        last = stages[-1]
        expected = base["rps"] * last["users"] / base["users"]
        if expected and last["rps"] < 0.7 * expected:
            notes.append(
                f"**Насичення пропускної здатності.** При {last['users']} VUsers сервер обробляє "
                f"{last['rps']:.1f} RPS — "
                f"лише {100 * last['rps'] / expected:.0f}% від лінійного прогнозу ({expected:.1f} RPS)."
            )

    if res:
        if res["cpu_max"] >= 90:
            notes.append(
                f"**CPU.** Процес сервера досягав {res['cpu_max']:.0f}% одного ядра. Uvicorn з одним воркером "
                "використовує лише одне ядро, тож це стеля продуктивності незалежно від кількості ядер машини."
            )
        else:
            notes.append(
                f"**CPU.** Максимальне завантаження процесу {res['cpu_max']:.0f}% одного ядра — запас по CPU є."
            )
        notes.append(
            f"**RAM.** Пам'ять процесу {res['ram_avg']:.0f}–{res['ram_max']:.0f} МБ — витоків пам'яті не помітно, "
            "якщо графік RAM не зростає безперервно."
        )

    if failures:
        top = sorted(failures, key=lambda f: -int(f["Occurrences"]))[:3]
        text = "; ".join(f"`{f['Name']}`: {short_error(f['Error'])} ×{f['Occurrences']}" for f in top)
        notes.append(f"**Типи помилок.** {text}.")
        if any("500" in f["Error"] for f in failures):
            notes.append(
                "**Помилки 500.** Подробиці видно лише в лозі сервера (рядки «Необроблена помилка …»). "
                "Для SQLite під конкурентним записом типова причина — `database is locked`: SQLite дозволяє лише "
                "одного записувача, а поки цикл подій заблоковано (наприклад, хешуванням bcrypt), транзакція не "
                "завершується і інші запити перевищують тайм-аут очікування. Рішення — PostgreSQL для production."
            )
        if any("ConnectionReset" in f["Error"] or "RemoteDisconnected" in f["Error"] for f in failures):
            notes.append(
                "**Обірвані з'єднання.** Частина запитів завершилась `Connection reset` — сервер не встигав приймати "
                "нові з'єднання, поки цикл подій був зайнятий."
            )

    if not notes:
        notes.append("Явних вузьких місць при цьому профілі не виявлено — варто збільшити навантаження.")
    return notes


def short_error(error: str) -> str:
    if "HTTPError" in error and "Error:" in error:
        return error.split("HTTPError('", 1)[-1].split(" for url")[0]  # "500 Server Error: Internal Server Error"
    return error.split("(", 1)[0] if "(" in error else error[:80]


# ---------- Звіт ----------
def fmt(value, digits=0):
    return f"{value:.{digits}f}"


def build_report(out_dir: Path, meta: Optional[dict] = None) -> Path:
    out_dir = Path(out_dir)
    if meta is None:
        meta = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))
    stats, history, failures, resources = load(out_dir)
    rows = endpoint_rows(stats)
    points = series(history)
    res = resource_summary(resources)
    s = meta["settings"]
    stages = []
    if meta["profile"] == "step":
        stages = stage_rows(points, resources, [int(n) for n in str(s["stages"]).split(",")])
    charts = make_charts(out_dir, points, resources, rows)
    notes = find_bottlenecks(rows, points, stages, res, failures)

    if meta["profile"] == "baseline":
        ramp = s["users"] / s["spawn_rate"]
        profile = (
            f"{s['users']} VUsers, розгін {s['spawn_rate']:g} корист./с (Ramp-Up ≈ {ramp:.0f} с), "
            f"тривалість {s['duration']} с"
        )
    else:
        profile = (
            f"ступені {s['stages'].replace(',', ' → ')} VUsers по {s['stage_seconds']} с, "
            f"розгін {s['spawn_rate']:g} корист./с"
        )

    lines = [
        f"# Звіт навантажувального тестування — профіль `{meta['profile']}`",
        "",
        "| Параметр | Значення |",
        "|---|---|",
        "| Інструмент | Locust |",
        f"| Профіль навантаження | {profile} |",
        f"| Середовище | `{meta['environment']}`, {meta['host']} |",
        "| Суміш користувачів | клієнти 6 : анонімні 2"
        + (" : адміністратори 1 |" if meta.get("admins_included") else " |"),
        f"| Машина | {meta['machine']}, Python {meta['python']} |",
        f"| Початок | {meta['started_at']}, фактична тривалість {meta.get('duration_s', '?')} с |",
        "",
        "## Підсумкові метрики",
        "",
        "| Ендпоінт | Запитів | Помилок | Error Rate | RPS | Avg, мс | Min, мс | Max, мс "
        "| p50, мс | p95, мс | p99, мс |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['name']} | {r['count']} | {r['fails']} | {fmt(r['error_rate'], 2)}% | {fmt(r['rps'], 1)} | "
            f"{fmt(r['avg'])} | {fmt(r['min'])} | {fmt(r['max'])} | "
            f"{fmt(r['p50'])} | {fmt(r['p95'])} | {fmt(r['p99'])} |"
        )

    lines += ["", "## Ресурси сервера", ""]
    if res:
        lines += [
            "| Показник | Середнє | Максимум |",
            "|---|---:|---:|",
            f"| CPU процесу сервера, % одного ядра | {fmt(res['cpu_avg'])} | {fmt(res['cpu_max'])} |",
            f"| RAM процесу сервера, МБ | {fmt(res['ram_avg'])} | {fmt(res['ram_max'])} |",
            f"| CPU системи, % | {fmt(res['sys_cpu_avg'])} | {fmt(res['sys_cpu_max'])} |",
            f"| RAM системи, % | — | {fmt(res['sys_mem_max'])} |",
            "",
            "> Locust працює на тій самій машині, що й сервер, тож частину CPU системи "
            "займає сам генератор навантаження.",
        ]
    else:
        lines.append("Дані моніторингу відсутні (процес сервера не знайдено).")

    if stages:
        lines += [
            "",
            "## Результати за ступенями навантаження",
            "",
            "| VUsers | RPS | p50, мс | p95, мс | max p95, мс | Error Rate | CPU сервера сер./макс., % | RAM, МБ |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for st in stages:
            r = st["res"]
            cpu = f"{fmt(r['cpu_avg'])} / {fmt(r['cpu_max'])}" if r else "—"
            ram = fmt(r["ram_max"]) if r else "—"
            lines.append(
                f"| {st['users']} | {fmt(st['rps'], 1)} | {fmt(st['p50'])} | {fmt(st['p95'])} | {fmt(st['p95_max'])} | "
                f"{fmt(st['error_rate'], 2)}% | {cpu} | {ram} |"
            )

    lines += ["", "## Графіки", ""]
    for title, file in charts:
        lines += [f"### {title}", "", f"![{title}]({file})", ""]

    if failures:
        lines += ["## Помилки", "", "| Метод | Ендпоінт | Помилка | Кількість |", "|---|---|---|---:|"]
        for f in failures:
            lines.append(f"| {f['Method']} | {f['Name']} | {short_error(f['Error'])} | {f['Occurrences']} |")
        lines.append("")

    lines += ["## Виявлені вузькі місця", ""]
    lines += [f"{i}. {note}" for i, note in enumerate(notes, start=1)]
    lines += [
        "",
        "> Розділ сформовано автоматично за порогами: Error Rate > 1%, p95 > 2× від базового ступеня, "
        "сплеск p95 > 3× від типового, CPU ≥ 90% одного ядра. Перевірте висновки за графіками.",
        "",
    ]

    path = out_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Використання: python loadtest/report.py <baseline|step>")
    print(build_report(HERE / "results" / sys.argv[1]))
