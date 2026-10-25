"""Запуск навантажувального тесту з моніторингом ресурсів сервера та генерацією звіту.

Перед запуском підніміть sandbox в окремому терміналі (без --reload):
    uvicorn app.main:app

Профілі:
    python loadtest/run.py baseline   # контрольний: 50 VUsers, розгін 5 корист./с (10 с), 3 хв
    python loadtest/run.py step       # ступінчастий: 10→25→50→100→150 VUsers по 60 с

Результати: loadtest/results/<профіль>/report.md (таблиці, графіки, вузькі місця).
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

from monitor import ResourceMonitor, find_server_processes
from report import build_report

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"

PROFILES = {
    "baseline": {"users": 50, "spawn_rate": 5.0, "duration": 180},
    "step": {"stages": "10,25,50,100,150", "stage_seconds": 60, "spawn_rate": 5.0},
}


def check_server(host: str) -> dict:
    with urllib.request.urlopen(f"{host}/health", timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Навантажувальний тест Vet CRM")
    parser.add_argument("profile", choices=sorted(PROFILES))
    parser.add_argument("--host", default="http://127.0.0.1:8000")
    parser.add_argument("--users", type=int, help="baseline: кількість VUsers")
    parser.add_argument("--spawn-rate", type=float, help="швидкість розгону, користувачів за секунду")
    parser.add_argument("--duration", type=int, help="baseline: тривалість, с")
    parser.add_argument("--stages", help="step: кількість VUsers на кожному ступені, через кому")
    parser.add_argument("--stage-seconds", type=int, help="step: тривалість ступеня, с")
    parser.add_argument("--pid", type=int, help="PID процесу сервера, якщо автопошук знаходить кілька")
    parser.add_argument("--allow-production", action="store_true", help="дозволити тест не-sandbox середовища")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile = dict(PROFILES[args.profile])
    for key in ("users", "spawn_rate", "duration", "stages", "stage_seconds"):
        value = getattr(args, key, None)
        if value is not None and key in profile:
            profile[key] = value

    try:
        info = check_server(args.host)
    except OSError:
        sys.exit(f"Сервер {args.host} не відповідає. Запустіть його в іншому терміналі: uvicorn app.main:app")
    environment = info.get("environment")
    if environment != "sandbox" and not args.allow_production:
        sys.exit(f"Середовище сервера: {environment}. Навантажувальні тести запускаються лише на sandbox.")

    processes = find_server_processes(args.pid)
    roots = [p for p in processes if not any(p.ppid() == q.pid for q in processes)]
    if len(roots) > 1:
        print("УВАГА: знайдено кілька запущених серверів uvicorn — зупиніть зайві або вкажіть --pid.")
    if processes:
        print("Моніторинг процесів сервера, PID:", ", ".join(str(p.pid) for p in processes))
    else:
        print("УВАГА: процес uvicorn не знайдено — CPU/RAM сервера не буде виміряно (лише система загалом).")
    if not (os.getenv("LOADTEST_ADMIN_EMAIL") and os.getenv("LOADTEST_ADMIN_PASSWORD")):
        print("Адміністратори в тесті не беруть участі (не задано LOADTEST_ADMIN_EMAIL / LOADTEST_ADMIN_PASSWORD).")

    out_dir = RESULTS_DIR / args.profile
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)

    env = os.environ.copy()
    env["LOADTEST_USER_PASSWORD"] = uuid.uuid4().hex
    cmd = [
        sys.executable, "-m", "locust",
        "-f", str(HERE / "locustfile.py"),
        "--headless",
        "--host", args.host,
        "--csv", str(out_dir / "locust"),
        "--csv-full-history",
        "--html", str(out_dir / "locust.html"),
    ]  # fmt: skip
    if args.profile == "baseline":
        env.pop("LOAD_SHAPE", None)
        cmd += ["-u", str(profile["users"]), "-r", str(profile["spawn_rate"]), "-t", f"{profile['duration']}s"]
    else:
        env.update(
            LOAD_SHAPE="step",
            LOAD_STAGES=str(profile["stages"]),
            LOAD_STAGE_SECONDS=str(profile["stage_seconds"]),
            LOAD_SPAWN_RATE=str(profile["spawn_rate"]),
        )

    meta = {
        "profile": args.profile,
        "settings": profile,
        "host": args.host,
        "environment": environment,
        "admins_included": bool(os.getenv("LOADTEST_ADMIN_EMAIL")),
        "server_pids": [p.pid for p in processes],
        "machine": f"{platform.system()} {platform.machine()}, {os.cpu_count()} логічних ядер",
        "python": platform.python_version(),
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }

    monitor = ResourceMonitor(processes, out_dir / "resources.csv")
    monitor.start()
    started = time.time()
    result = subprocess.run(cmd, env=env)
    monitor.stop()
    monitor.join()

    meta["duration_s"] = round(time.time() - started, 1)
    meta["locust_exit_code"] = result.returncode
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    report_path = build_report(out_dir, meta)
    print(f"\nГотово. Звіт: {report_path.relative_to(HERE.parent)}")
    print(f"Детальний HTML-звіт Locust: {(out_dir / 'locust.html').relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
