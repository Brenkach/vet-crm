"""Моніторинг ресурсів процесу сервера (CPU, RAM) під час навантажувального тесту."""

import csv
import os
import threading
import time
from pathlib import Path
from typing import List, Optional

import psutil

FIELDS = ["timestamp", "elapsed_s", "server_cpu_percent", "server_rss_mb", "system_cpu_percent", "system_mem_percent"]


def is_uvicorn_app(args: List[str]) -> bool:
    """`uvicorn app.main:app ...` або `python -m uvicorn app.main:app ...`, але не shell, що лише згадує ці слова."""
    launcher = [Path(a).name for a in args[:3]]
    runs_uvicorn = "uvicorn" in launcher or ("-m" in args[:3] and "uvicorn" in args[:4])
    return runs_uvicorn and any(a.startswith("app.main") for a in args)


def find_server_processes(pid: Optional[int] = None) -> List[psutil.Process]:
    """Шукає процеси uvicorn із застосунком app.main (разом із дочірніми, якщо увімкнено --reload)."""
    found = {}
    if pid:
        roots = [psutil.Process(pid)]
    else:
        roots = []
        for proc in psutil.process_iter(["pid", "cmdline"], ad_value=None):
            if proc.pid != os.getpid() and is_uvicorn_app(proc.info["cmdline"] or []):
                roots.append(proc)
    for proc in roots:
        found[proc.pid] = proc
        try:
            for child in proc.children(recursive=True):
                found[child.pid] = child
        except psutil.Error:
            pass
    return list(found.values())


class ResourceMonitor(threading.Thread):
    """Раз на секунду записує в CSV завантаження CPU і пам'ять процесу сервера та системи загалом.

    CPU процесу вимірюється у відсотках одного ядра: 100% означає, що процес повністю зайняв одне ядро.
    """

    def __init__(self, processes: List[psutil.Process], path, interval: float = 1.0):
        super().__init__(daemon=True)
        self.processes = list(processes)
        self.path = path
        self.interval = interval
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        for proc in self.processes:
            try:
                proc.cpu_percent(None)  # перший виклик лише ініціалізує лічильник
            except psutil.Error:
                pass
        psutil.cpu_percent(None)
        started = time.time()

        with open(self.path, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDS)
            writer.writeheader()
            while not self._stop_event.wait(self.interval):
                cpu, rss = 0.0, 0.0
                for proc in list(self.processes):
                    try:
                        cpu += proc.cpu_percent(None)
                        rss += proc.memory_info().rss
                    except psutil.Error:
                        self.processes.remove(proc)
                now = time.time()
                writer.writerow(
                    {
                        "timestamp": round(now, 3),
                        "elapsed_s": round(now - started, 1),
                        "server_cpu_percent": round(cpu, 1),
                        "server_rss_mb": round(rss / 1024 / 1024, 1),
                        "system_cpu_percent": psutil.cpu_percent(None),
                        "system_mem_percent": psutil.virtual_memory().percent,
                    }
                )
                file.flush()


# ---------- Моніторинг контейнерів Docker ----------
DOCKER_FIELDS = FIELDS + ["db_cpu_percent", "db_mem_mb", "redis_cpu_percent", "redis_mem_mb", "nginx_cpu_percent"]
_UNITS = {"b": 1, "kib": 1024, "mib": 1024**2, "gib": 1024**3, "kb": 1000, "mb": 1000**2, "gb": 1000**3}


def parse_mem_mb(value: str) -> float:
    """'45.6MiB / 7.6GiB' -> 45.6"""
    used = value.split("/")[0].strip().lower()
    number = used.rstrip("abcdefghijklmnopqrstuvwxyz")
    unit = used[len(number) :] or "b"
    return float(number) * _UNITS.get(unit, 1) / 1024**2


def parse_docker_stats(output: str, project: str) -> dict:
    """Сумує CPU і RAM контейнерів проєкту за сервісами (app — усі репліки разом)."""
    totals = {"app": [0.0, 0.0], "db": [0.0, 0.0], "redis": [0.0, 0.0], "nginx": [0.0, 0.0]}
    for line in output.strip().splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or not parts[0].startswith(project + "-"):
            continue
        service = parts[0][len(project) + 1 :].rsplit("-", 1)[0]
        if service in totals:
            totals[service][0] += float(parts[1].strip().rstrip("%") or 0)
            totals[service][1] += parse_mem_mb(parts[2])
    return totals


class DockerMonitor(threading.Thread):
    """Знімає `docker stats` контейнерів проєкту і пише CSV у тому ж форматі, що й ResourceMonitor.

    CPU у Docker теж вимірюється у відсотках одного ядра: 300% = три ядра повністю зайняті.
    server_* — сума всіх реплік застосунку.
    """

    def __init__(self, project: str, path):
        super().__init__(daemon=True)
        self.project = project
        self.path = path
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        import subprocess

        psutil.cpu_percent(None)
        started = time.time()
        cmd = ["docker", "stats", "--no-stream", "--format", "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"]
        with open(self.path, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=DOCKER_FIELDS)
            writer.writeheader()
            while not self._stop_event.is_set():
                try:
                    out = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
                except (OSError, subprocess.SubprocessError):
                    self._stop_event.wait(1)
                    continue
                t = parse_docker_stats(out, self.project)
                now = time.time()
                writer.writerow(
                    {
                        "timestamp": round(now, 3),
                        "elapsed_s": round(now - started, 1),
                        "server_cpu_percent": round(t["app"][0], 1),
                        "server_rss_mb": round(t["app"][1], 1),
                        "system_cpu_percent": psutil.cpu_percent(None),
                        "system_mem_percent": psutil.virtual_memory().percent,
                        "db_cpu_percent": round(t["db"][0], 1),
                        "db_mem_mb": round(t["db"][1], 1),
                        "redis_cpu_percent": round(t["redis"][0], 1),
                        "redis_mem_mb": round(t["redis"][1], 1),
                        "nginx_cpu_percent": round(t["nginx"][0], 1),
                    }
                )
                file.flush()
