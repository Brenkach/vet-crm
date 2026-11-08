"""Перевірка балансування: серія запитів через Nginx і статистика, яка репліка що обробила.

    python loadtest/lb_check.py                        # 12 послідовних запитів на http://localhost/health
    python loadtest/lb_check.py -n 20                  # 20 запитів
    python loadtest/lb_check.py --watch                # безперервно — для демонстрації відмови репліки
    python loadtest/lb_check.py --url http://localhost:8080

Для CI: --expect-instances N завершує скрипт з кодом 1, якщо відповіли не рівно N реплік
або якщо був хоч один невдалий запит.
"""

import argparse
import collections
import sys
import time
import urllib.error
import urllib.request
from typing import Dict


def probe(url: str, timeout: float) -> Dict[str, str]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            status, headers = str(resp.status), resp.headers
            resp.read()
    except urllib.error.HTTPError as exc:
        status, headers = str(exc.code), exc.headers
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        return {"status": "ERR", "instance": "—", "upstream": str(reason)[:30], "ms": "—"}
    return {
        "status": status,
        "instance": headers.get("X-Instance", "?"),
        # Якщо Nginx пробував кілька реплік, тут буде кілька адрес через кому
        "upstream": headers.get("X-Upstream-Addr", "—"),
        "ms": f"{(time.perf_counter() - started) * 1000:.0f}",
    }


def print_summary(counts: collections.Counter, total: int, errors: int) -> None:
    print("\nРозподіл запитів між репліками:")
    for instance, count in sorted(counts.items()):
        share = 100 * count / total if total else 0
        print(f"  {instance:<14} {count:>4}  {share:5.1f}%  {'█' * count}")
    print(f"Усього запитів: {total}, успішних: {total - errors}, помилок: {errors}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Перевірка розподілу запитів балансувальником")
    parser.add_argument("--url", default="http://localhost", help="адреса Nginx")
    parser.add_argument("--path", default="/health")
    parser.add_argument("-n", "--requests", type=int, default=12)
    parser.add_argument("--watch", action="store_true", help="надсилати запити безперервно (Ctrl+C — зупинка)")
    parser.add_argument("--interval", type=float, help="пауза між запитами, с (за замовчуванням 0, у --watch 0.5)")
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--expect-instances", type=int, help="очікувана кількість різних реплік (для CI)")
    args = parser.parse_args()

    url = args.url.rstrip("/") + args.path
    interval = args.interval if args.interval is not None else (0.5 if args.watch else 0)
    counts: collections.Counter = collections.Counter()
    total = errors = 0

    print(f"Запити на {url}\n")
    print(f"{'№':>4}  {'Репліка (X-Instance)':<22} {'Upstream (Nginx)':<24} {'Статус':<7} {'Час, мс':>7}")
    try:
        while args.watch or total < args.requests:
            result = probe(url, args.timeout)
            total += 1
            if result["status"] == "200":
                counts[result["instance"]] += 1
            else:
                errors += 1
            row = f"{total:>4}  {result['instance']:<22} {result['upstream']:<24} "
            print(row + f"{result['status']:<7} {result['ms']:>7}", flush=True)
            if interval:
                time.sleep(interval)
    except KeyboardInterrupt:
        pass

    print_summary(counts, total, errors)

    if args.expect_instances is not None:
        if len(counts) != args.expect_instances or errors:
            print(f"ПОМИЛКА: очікувалось {args.expect_instances} реплік без помилок, отримано {len(counts)}")
            sys.exit(1)
        print(f"OK: запити рівномірно оброблено {len(counts)} репліками без помилок")


if __name__ == "__main__":
    main()
