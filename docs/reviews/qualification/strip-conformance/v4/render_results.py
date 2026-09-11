"""Render a v4 results JSON as the per-case markdown table the v2 record used."""

import json
import statistics
import sys
from collections import defaultdict

results = json.load(open(sys.argv[1]))
title = sys.argv[2] if len(sys.argv) > 2 else "Results"
routes = sorted({r["route"] for r in results})
print(f"# {title}")
print()
for slug in routes:
    rs = [r for r in results if r["route"] == slug]
    by_case = defaultdict(list)
    for r in rs:
        by_case[r["case"]].append(r)
    print(f"## {slug}")
    print()
    print("| Case | conformant / false-contamination / BLOCKING | latency median (s) | cost (8 runs) | problems |")
    print("|---|---|---|---|---|")
    for cid, items in by_case.items():
        v = [i["verdict"] for i in items]
        lat = statistics.median(i["ms"] for i in items) / 1000
        cost = sum(i["cost"] for i in items)
        problems = "; ".join(sorted({f"r{i['run']}: {p}" for i in items for p in i["problems"] if i["verdict"] != "conformant"}))
        print(f"| {cid} | {v.count('conformant')} / {v.count('false-contamination')} / {v.count('BLOCKING')} | {lat:.1f} | ${cost:.4f} | {problems} |")
    lat_all = [r["ms"] for r in rs]
    conformant = sum(1 for r in rs if r["verdict"] == "conformant")
    print()
    print(
        f"**{slug}**: conformant {conformant}/{len(rs)}; false-contamination "
        f"{sum(1 for r in rs if r['verdict'] == 'false-contamination')}; BLOCKING "
        f"{sum(1 for r in rs if r['verdict'] == 'BLOCKING')}; truncated "
        f"{sum(1 for r in rs if 'truncated' in r['states'])}; retries {sum(1 for r in rs if len(r['states']) > 1)}; "
        f"latency median {statistics.median(lat_all)/1000:.1f} s, max {max(lat_all)/1000:.1f} s; "
        f"total measured cost ${sum(r['cost'] for r in rs):.4f}; mean per call ${sum(r['cost'] for r in rs)/len(rs):.4f}"
    )
    print()
