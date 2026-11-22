"""Порівняння кількох прогонів навантажувального тесту («ДО» і «ПІСЛЯ»).

    python loadtest/compare.py lb-1-replica lb-3-replicas
    python loadtest/compare.py --out lab7-50 --title "ЛР №7, профіль ЛР №4" before-50 after-50

Аргументи — назви папок у loadtest/results/. Перший прогін вважається базовим («ДО»).
Результат: loadtest/results/<out>.md і графіки <out>_*.png поруч.
"""

import argparse
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from report import load, num, read_csv, series  # noqa: E402

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
COLORS = ["#b4473d", "#b9821f", "#3f7262", "#4a6fa5"]
KEY_ENDPOINTS = [
    "POST /auth/register",
    "POST /auth/login",
    "GET /home",
    "GET /users/me",
    "GET /pets",
    "GET /appointments",
    "POST /pets",
    "POST /appointments",
]


def resource_stats(out_dir: Path) -> Dict[str, Optional[float]]:
    rows = read_csv(out_dir / "resources.csv")

    def column(key: str) -> List[float]:
        return [v for v in (num(r.get(key)) for r in rows) if v is not None]

    result: Dict[str, Optional[float]] = {}
    for key, name in (
        ("server_cpu_percent", "cpu"),
        ("server_rss_mb", "ram"),
        ("db_cpu_percent", "db_cpu"),
        ("redis_mem_mb", "redis_ram"),
    ):
        values = column(key)
        result[f"{name}_avg"] = statistics.mean(values) if values else None
        result[f"{name}_max"] = max(values) if values else None
    return result


def summarize(name: str) -> Dict:
    out_dir = RESULTS / name
    if not (out_dir / "locust_stats.csv").exists():
        sys.exit(f"Немає результатів у {out_dir}. Спершу запустіть: python loadtest/run.py ... --name {name}")
    stats, history, _, _ = load(out_dir)
    by_name = {r["Name"]: r for r in stats}
    total = by_name["Aggregated"]
    count, fails = int(total["Request Count"]), int(total["Failure Count"])
    points = series(history)
    stable = [p["p95"] for p in points if p["p95"] is not None]
    run = {
        "name": name,
        "rps": num(total["Requests/s"]) or 0.0,
        "avg": num(total["Average Response Time"]) or 0.0,
        "p50": num(total["50%"]) or 0.0,
        "p95": num(total["95%"]) or 0.0,
        "p99": num(total["99%"]) or 0.0,
        "max": num(total["Max Response Time"]) or 0.0,
        "count": count,
        "error_rate": 100.0 * fails / count if count else 0.0,
        "peak_p95": max(stable) if stable else 0.0,
        "endpoints": {
            e: (num(by_name[e]["Average Response Time"]), num(by_name[e]["95%"])) for e in KEY_ENDPOINTS if e in by_name
        },
        "points": points,
    }
    run.update(resource_stats(out_dir))
    return run


def change(base: Optional[float], value: Optional[float], higher_is_better: bool) -> str:
    if not base or value is None:
        return "—"
    delta = 100 * (value - base) / base
    better = delta > 0 if higher_is_better else delta < 0
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta:.0f}%" + (" ✅" if better and abs(delta) >= 5 else "")


def fmt(value: Optional[float], digits: int) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def timeline(ax, runs, colors, key, log=False):
    for run, color in zip(runs, colors):
        pts = [p for p in run["points"] if p[key] is not None]
        if pts:
            ax.plot([p["ts"] - pts[0]["ts"] for p in pts], [p[key] for p in pts], label=run["name"], color=color)
    if log:
        ax.set_yscale("log")
    ax.grid(alpha=0.3, which="both")
    ax.legend()


def charts(runs: List[Dict], out: str) -> List[str]:
    names = [r["name"] for r in runs]
    colors = COLORS[: len(runs)]
    files = []

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].bar(names, [r["rps"] for r in runs], color=colors)
    axes[0].set(title="Пропускна здатність", ylabel="RPS")
    metrics = ["avg", "p50", "p95"]
    width = 0.8 / len(runs)
    for i, run in enumerate(runs):
        xs = [m + i * width for m in range(len(metrics))]
        axes[1].bar(xs, [run[m] for m in metrics], width=width, color=colors[i], label=run["name"])
    axes[1].set_xticks([m + width * (len(runs) - 1) / 2 for m in range(len(metrics))], metrics)
    axes[1].set(title="Затримка", ylabel="мс")
    axes[1].legend()
    for ax in axes:
        ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    files.append(f"{out}_summary.png")
    fig.savefig(RESULTS / files[-1], dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 4.5))
    timeline(ax, runs, colors, "p95", log=True)
    ax.set(title="p95 часу відповіді в динаміці", xlabel="Час від початку тесту, с", ylabel="мс (лог. шкала)")
    fig.tight_layout()
    files.append(f"{out}_latency.png")
    fig.savefig(RESULTS / files[-1], dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 4.5))
    timeline(ax, runs, colors, "rps")
    ax.set(title="Пропускна здатність у динаміці", xlabel="Час від початку тесту, с", ylabel="запитів/с")
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    files.append(f"{out}_throughput.png")
    fig.savefig(RESULTS / files[-1], dpi=120)
    plt.close(fig)

    endpoints = [e for e in KEY_ENDPOINTS if all(e in r["endpoints"] for r in runs)]
    if endpoints:
        fig, ax = plt.subplots(figsize=(11, 0.5 * len(endpoints) * len(runs) + 1.5))
        height = 0.8 / len(runs)
        for i, run in enumerate(runs):
            ys = [y + i * height for y in range(len(endpoints))]
            ax.barh(
                ys, [run["endpoints"][e][1] or 0 for e in endpoints], height=height, color=colors[i], label=run["name"]
            )
        ax.set_yticks([y + height * (len(runs) - 1) / 2 for y in range(len(endpoints))], endpoints)
        ax.set_xscale("log")
        ax.set(title="p95 за ендпоінтами", xlabel="мс (лог. шкала)")
        ax.grid(alpha=0.3, axis="x", which="both")
        ax.legend()
        fig.tight_layout()
        files.append(f"{out}_endpoints.png")
        fig.savefig(RESULTS / files[-1], dpi=120)
        plt.close(fig)
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description="Порівняння прогонів навантажувального тесту")
    parser.add_argument("runs", nargs="+", help="назви папок у loadtest/results/, перша — базова")
    parser.add_argument("--out", default="comparison", help="назва файлу звіту без розширення")
    parser.add_argument("--title", default="Порівняння прогонів навантажувального тесту")
    args = parser.parse_args()
    if len(args.runs) < 2:
        sys.exit("Потрібно щонайменше два прогони")

    runs = [summarize(name) for name in args.runs]
    base, last = runs[0], runs[-1]
    images = charts(runs, args.out)
    names = " | ".join(f"`{r['name']}`" for r in runs)

    lines = [
        f"# {args.title}",
        "",
        f"Базовий прогін: `{base['name']}`. Остання колонка — зміна `{last['name']}` відносно базового.",
        "",
        f"| Метрика | {names} | Зміна |",
        "|---|" + "---:|" * (len(runs) + 1),
    ]
    rows = [
        ("RPS", "rps", 1, True),
        ("Latency avg, мс", "avg", 0, False),
        ("Latency p50, мс", "p50", 0, False),
        ("Latency p95, мс", "p95", 0, False),
        ("Latency p99, мс", "p99", 0, False),
        ("Latency max, мс", "max", 0, False),
        ("Пік p95 у динаміці, мс", "peak_p95", 0, False),
        ("Error Rate, %", "error_rate", 2, False),
        ("CPU реплік сер., % ядра", "cpu_avg", 0, False),
        ("CPU реплік макс., % ядра", "cpu_max", 0, False),
        ("RAM реплік макс., МБ", "ram_max", 0, False),
        ("CPU PostgreSQL сер., % ядра", "db_cpu_avg", 0, False),
        ("RAM Redis макс., МБ", "redis_ram_max", 1, False),
    ]
    for title, key, digits, higher_better in rows:
        if all(r[key] is None for r in runs):
            continue
        values = " | ".join(fmt(r[key], digits) for r in runs)
        lines.append(f"| {title} | {values} | {change(base[key], last[key], higher_better)} |")
    lines.append(f"| Запитів усього | {' | '.join(str(r['count']) for r in runs)} | |")

    lines += ["", "## Ендпоінти: середній час / p95, мс", "", f"| Ендпоінт | {names} |", "|---|" + "---:|" * len(runs)]
    for endpoint in KEY_ENDPOINTS:
        if all(endpoint in r["endpoints"] for r in runs):
            cells = " | ".join(
                f"{fmt(r['endpoints'][endpoint][0], 0)} / {fmt(r['endpoints'][endpoint][1], 0)}" for r in runs
            )
            lines.append(f"| {endpoint} | {cells} |")

    lines += ["", "## Графіки", ""] + [f"![{img}]({img})\n" for img in images]
    links = ", ".join(f"[`{r['name']}`]({r['name']}/report.md)" for r in runs)
    lines += [f"Детальні звіти кожного прогону: {links}", ""]

    path = RESULTS / f"{args.out}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Готово: {path.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
