"""Порівняння кількох прогонів навантажувального тесту (наприклад, 1 репліка проти 3 за Nginx).

    python loadtest/compare.py lb-1-replica lb-3-replicas

Аргументи — назви папок у loadtest/results/. Результат: loadtest/results/comparison.md і графіки поруч.
"""

import sys
from pathlib import Path
from typing import Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from report import load, num, series  # noqa: E402

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
COLORS = ["#b4473d", "#3f7262", "#b9821f", "#4a6fa5"]
KEY_ENDPOINTS = ["POST /auth/register", "POST /auth/login", "GET /pets", "POST /appointments"]


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
    return {
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
        "endpoints": {e: num(by_name[e]["95%"]) for e in KEY_ENDPOINTS if e in by_name},
        "points": points,
    }


def change(base: float, value: float, higher_is_better: bool) -> str:
    if not base:
        return "—"
    delta = 100 * (value - base) / base
    better = delta > 0 if higher_is_better else delta < 0
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta:.0f}%" + (" ✅" if better and abs(delta) >= 5 else "")


def charts(runs: List[Dict]) -> List[str]:
    names = [r["name"] for r in runs]
    colors = COLORS[: len(runs)]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].bar(names, [r["rps"] for r in runs], color=colors)
    axes[0].set(title="Пропускна здатність", ylabel="RPS")
    metrics = ["p50", "p95", "p99"]
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
    fig.savefig(RESULTS / "comparison_summary.png", dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 4.5))
    for run, color in zip(runs, colors):
        pts = [p for p in run["points"] if p["p95"]]
        if pts:
            ax.plot([p["ts"] - pts[0]["ts"] for p in pts], [p["p95"] for p in pts], label=run["name"], color=color)
    ax.set(title="p95 часу відповіді в динаміці", xlabel="Час від початку тесту, с", ylabel="мс (лог. шкала)")
    ax.set_yscale("log")
    ax.grid(alpha=0.3, which="both")
    ax.legend()
    fig.tight_layout()
    fig.savefig(RESULTS / "comparison_p95.png", dpi=120)
    plt.close(fig)
    return ["comparison_summary.png", "comparison_p95.png"]


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit("Використання: python loadtest/compare.py <базовий_прогін> <прогін_2> [...]")
    runs = [summarize(name) for name in sys.argv[1:]]
    base = runs[0]
    images = charts(runs)

    header = "| Метрика | " + " | ".join(f"`{r['name']}`" for r in runs) + " | Зміна відносно базового |"
    lines = [
        "# Порівняння прогонів навантажувального тесту",
        "",
        f"Базовий прогін: `{base['name']}`. Остання колонка — зміна останнього прогону відносно базового.",
        "",
        header,
        "|---|" + "---:|" * (len(runs) + 1),
    ]
    last = runs[-1]
    rows = [
        ("RPS", "rps", 1, True),
        ("Latency avg, мс", "avg", 0, False),
        ("Latency p50, мс", "p50", 0, False),
        ("Latency p95, мс", "p95", 0, False),
        ("Latency p99, мс", "p99", 0, False),
        ("Latency max, мс", "max", 0, False),
        ("Пік p95 у динаміці, мс", "peak_p95", 0, False),
        ("Error Rate, %", "error_rate", 2, False),
    ]
    for title, key, digits, higher_better in rows:
        values = " | ".join(f"{r[key]:.{digits}f}" for r in runs)
        lines.append(f"| {title} | {values} | {change(base[key], last[key], higher_better)} |")
    lines.append(f"| Запитів усього | {' | '.join(str(r['count']) for r in runs)} | |")

    lines += [
        "",
        "## p95 ключових ендпоінтів, мс",
        "",
        "| Ендпоінт | " + " | ".join(f"`{r['name']}`" for r in runs) + " |",
    ]
    lines.append("|---|" + "---:|" * len(runs))
    for endpoint in KEY_ENDPOINTS:
        if all(endpoint in r["endpoints"] for r in runs):
            lines.append(f"| {endpoint} | " + " | ".join(f"{r['endpoints'][endpoint]:.0f}" for r in runs) + " |")

    lines += ["", "## Графіки", ""] + [f"![{img}]({img})\n" for img in images]
    lines.append(
        "Детальні звіти кожного прогону: " + ", ".join(f"[`{r['name']}`]({r['name']}/report.md)" for r in runs)
    )
    lines.append("")

    path = RESULTS / "comparison.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Готово: {path.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
