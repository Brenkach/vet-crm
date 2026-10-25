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
