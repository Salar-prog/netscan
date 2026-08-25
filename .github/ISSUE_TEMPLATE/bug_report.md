---
name: Bug report
about: Report something broken
labels: bug
---

**What happened?**
A clear description of the bug.

**Steps to reproduce**
1.
2.
3.

**Expected behavior**

**Environment**
- NetScan version/commit:
- Deployment: [bare metal / docker / compose]
- Python version:
- OS:

**Logs**
```
Paste relevant logs (redact secrets, API keys, webhook URLs).
```

**Additional context**
If this involves IP state transitions (e.g. an IP became available
unexpectedly), include the scan history from
`GET /api/v1/ips/{ip}/history` — quarantine logic bugs are high priority.
