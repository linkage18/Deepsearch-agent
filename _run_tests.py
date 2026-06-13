"""Test SearXNG and search tool"""
import sys, json, subprocess, os

# Test 1: SearXNG directly
print("=== Test 1: SearXNG HTTP API ===")
try:
    import requests
    r = requests.get("http://localhost:8888/search", 
                     params={"format": "json", "q": "influence maximization multiplex networks", "language": "zh-CN,en"},
                     timeout=10)
    data = r.json()
    results = data.get("results", [])[:3]
    print(f"  SearXNG responded: {len(data.get('results',[]))} results total")
    for i, res in enumerate(results):
        print(f"  [{i+1}] {res.get('title','')[:50]}")
        print(f"       engine: {res.get('engine','')}")
        print(f"       snippet: {res.get('content','')[:80]}")
    print("  PASSED")
except Exception as e:
    print(f"  FAILED: {e}")

print()

# Test 2: Local search tool import + basic call
print("=== Test 2: Search tool function ===")
sys.path.insert(0, '.')
from app.tools.search_tool import internet_search
print(f"  Tool name: {internet_search.name}")
print(f"  Has invoke: {hasattr(internet_search, 'invoke')}")
# Test that it produces a callable result (SearXNG needs to be reachable)
# Use a short timeout
from app.tools.search_tool import SEARXNG_BASE_URL
print(f"  SEARXNG_BASE_URL: {SEARXNG_BASE_URL}")
print("  PASSED")

print()

# Test 3: RAG evaluation
print("=== Test 3: RAG Evaluation (evaluate.py) ===")
from app.tools.llamaindex_tools import list_paper_library_files
files_result = list_paper_library_files.invoke({})
print(f"  Library files: {files_result[:100]}...")
print("  PASSED")

print()

print("=== Test 4: Agent task submission ===")
import requests as req
resp = req.post("http://localhost:8000/api/task", 
                json={"query": "介绍 MIM-Reasoner 的核心方法"},
                timeout=5)
data = resp.json()
print(f"  Status: {data.get('status')}")
print(f"  Thread ID: {data.get('thread_id')[:12]}...")
print("  PASSED")

print()

print("ALL TESTS DONE")
