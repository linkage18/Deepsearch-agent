"""Speed benchmark after optimizations"""
import os, sys, time
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
os.environ["TOKENIZERS_PARALLELISM"] = "false"

print("=== Speed Benchmark ===")

t0 = time.time()
from app.tools.llamaindex_tools import search_paper_library
t1 = time.time()
print(f"Import: {t1-t0:.1f}s")

t0 = time.time()
r = search_paper_library.invoke({"query": "MIM-Reasoner reinforcement learning", "top_k": 3})
t1 = time.time()
evidence_count = r.count("[证据")
print(f"First search: {t1-t0:.1f}s, results: {evidence_count}")

t0 = time.time()
r2 = search_paper_library.invoke({"query": "Graph Bayesian Optimization", "top_k": 3})
t1 = time.time()
print(f"Second search: {t1-t0:.1f}s, results: {r2.count('[证据')}")

t0 = time.time()
from app.tools.search_tool import internet_search
t1 = time.time()
print(f"Search tool import: {t1-t0:.1f}s")

t0 = time.time()
r3 = internet_search.invoke({"query": "MIM-Reasoner influence maximization", "max_results": 3})
t1 = time.time()
print(f"SearXNG search: {t1-t0:.1f}s, results: {r3.count('[结果')}")

print("=== Done ===")
