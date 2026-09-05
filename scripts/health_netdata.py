"""Netdata API — сбор трендов (min/max/avg) за последний час."""
import json
import urllib.request
import urllib.error

NETDATA_BASE = "http://@HERMES_HOST@:@NETDATA_PORT@"

NETDATA_CHARTS = [
    ("system.ram", "RAM", "MB"),
    ("system.cpu", "CPU", "%"),
    ("system.load", "Load", ""),
    ("system.io", "Disk IO", "KB/s"),
    ("system.net", "Network", "kilobits/s"),
]

def query_netdata(chart: str, after: int = -3600, points: int = 6) -> dict | None:
    """Запрашивает данные чарта из Netdata API."""
    url = f"{NETDATA_BASE}/api/v1/data?chart={chart}&after={after}&points={points}&format=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hermes-health-analyzer"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None

def collect_netdata_trends() -> dict:
    """Собирает тренды из Netdata: min/max/avg по каждому чарту за час."""
    trends = {}
    for chart, label, unit in NETDATA_CHARTS:
        data = query_netdata(chart)
        if not data or "data" not in data or not data["data"]:
            trends[label] = {"status": "unavailable"}
            continue
        
        labels = data.get("labels", ["time"])
        points = data["data"]
        
        result = {"unit": unit, "points": len(points)}
        for i, lbl in enumerate(labels[1:], 1):
            values = [pt[i] for pt in points if pt[i] is not None]
            if values:
                result[lbl] = {
                    "min": round(min(values), 1),
                    "max": round(max(values), 1),
                    "avg": round(sum(values) / len(values), 1),
                    "latest": round(values[-1], 1),
                }
        trends[label] = result
    return trends
