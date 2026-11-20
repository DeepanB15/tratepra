"""Verify the REAL services Tratepra depends on and print an evidence report. Exit code 1 if a core check fails.

Usage:
  python -m scripts.verify_setup            # database, pgvector, Ollama, connector configuration
  python -m scripts.verify_setup --probe    # additionally make one real request per configured connector

Nothing here is simulated: each line reports what the service actually answered. A connector that is
configured but not probed is reported as "configured (not probed)", never as working.
"""
import argparse
import sys

from app.connectors import all_connectors
from app.core.health import readiness


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="one live request per configured connector (uses API quota)")
    args = ap.parse_args()

    r = readiness()
    c = r["components"]
    print("Core services")
    for name in ("database", "pgvector", "ollama"):
        item = c[name]
        print(f"  [{'OK' if item['ok'] else 'FAIL'}] {name}: {item.get('detail') or item.get('error') or ''}")
    print(f"  overall: {r['status']}")

    print("\nConnectors")
    probe_failed = False
    for conn in all_connectors():
        a = conn.availability()
        if not a["available"]:
            print(f"  [--] {conn.key}: unavailable - {a['reason']}")
            continue
        if not args.probe:
            print(f"  [..] {conn.key}: configured (not probed)")
            continue
        try:
            n = len(conn.search("artificial intelligence", "7d"))
            print(f"  [OK] {conn.key}: live request succeeded, {n} records")
        except Exception as exc:  # noqa: BLE001 - report whatever the service said
            probe_failed = True
            print(f"  [FAIL] {conn.key}: {type(exc).__name__}: {exc}")
    return 0 if r["status"] in ("ready", "degraded") and not probe_failed else 1


if __name__ == "__main__":
    sys.exit(main())
