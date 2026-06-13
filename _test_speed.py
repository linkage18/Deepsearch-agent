"""Test full task timing"""
import sys, time, requests, json

t0 = time.time()
payload = {"query": "MIM-Reasoner core method for multiplex influence maximization"}
r = requests.post("http://localhost:8000/api/task", json=payload, timeout=30)
t1 = time.time()
tid = r.json().get("thread_id", "?")[:12]
print(f"Submit: {t1-t0:.1f}s | status={r.status_code} | thread={tid}")
print(f"Agent is running in background... check docker compose logs backend")
