"""Quick sanity view over results.json (dev helper, not part of deliverable)."""
import json
import sys

data = json.load(open("output/results.json", encoding="utf-8"))
kind_of = {}
for r in data["results"]:
    kind = r["filename"].split("_", 2)[1] if "_" in r["filename"] else r["filename"]
    kind_of.setdefault(kind, r)

for kind, r in kind_of.items():
    b = r["score_breakdown"]
    print(
        f"{kind:14s} total={r['total_score']:3d} "
        f"AI={b['ai_project_depth']:2d} Py={b['python_backend']:2d} "
        f"Cloud={b['cloud_fullstack']:2d} GH={b['github']} "
        f"Eng={b['engineering_depth']} pen={b['penalty']:3d} "
        f"gh={r['github_enrichment_status']}"
    )

print()
print("summary:", json.dumps(data["batch_summary"]))

# Show one evidence trail for explainability
top = data["results"][0]
print("\nevidence for top candidate:", top["candidate_name"])
for cat, lines in top["evidence"].items():
    print(f"  {cat}:")
    for line in lines[:4]:
        print(f"    {line}")

# Penalties applied?
penalties = [
    (r["filename"], r["score_breakdown"]["penalty"])
    for r in data["results"] if r["score_breakdown"]["penalty"] < 0
]
print("\npenalized:", penalties if penalties else "NONE — CHECK LOGIC")
sys.exit(0)
