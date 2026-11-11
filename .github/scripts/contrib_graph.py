"""Genera las gráficas de barras de contribuciones (claro y oscuro) como SVG.

Uso: GITHUB_TOKEN=... python3 contrib_graph.py <usuario> <carpeta_salida>
     python3 contrib_graph.py --demo <carpeta_salida>   (datos de prueba)
"""
import datetime as dt
import json
import os
import random
import sys
import urllib.request

CELL, GAP = 11, 3
STEP = CELL + GAP
LEFT, TOP = 36, 64
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"

THEMES = {
    "dark": {
        "bg": "#0d1117", "text": "#c9d1d9", "muted": "#8b949e", "border": "#30363d",
        "levels": ["#161b22", "#2e2e2e", "#5c5c5c", "#9e9e9e", "#ffffff"],
    },
    "light": {
        "bg": "#ffffff", "text": "#1f2328", "muted": "#656d76", "border": "#d0d7de",
        "levels": ["#ebedf0", "#c6c6c6", "#8c8c8c", "#555555", "#1f1f1f"],
    },
}
LEVEL = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
         "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

QUERY = """query($login:String!){user(login:$login){contributionsCollection{
contributionCalendar{totalContributions weeks{contributionDays{
date contributionCount contributionLevel}}}}}}"""


def fetch(user):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": user}}).encode(),
        headers={"Authorization": "bearer " + os.environ["GITHUB_TOKEN"],
                 "Content-Type": "application/json"},
    )
    data = json.load(urllib.request.urlopen(req))
    if "errors" in data:
        raise SystemExit(data["errors"])
    cal = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    return [[{"date": d["date"], "count": d["contributionCount"],
              "level": LEVEL[d["contributionLevel"]]} for d in w["contributionDays"]]
            for w in cal["weeks"]]


def demo():
    random.seed(1)
    end = dt.date(2026, 11, 11)
    start = end - dt.timedelta(days=364)
    start -= dt.timedelta(days=(start.weekday() + 1) % 7)  # domingo
    weeks, d = [], start
    while d <= end:
        if not weeks or len(weeks[-1]) == 7:
            weeks.append([])
        c = random.choice([0, 0, 0, 1, 2, 3, 5, 8, 13])
        weeks[-1].append({"date": d.isoformat(), "count": c,
                          "level": 0 if c == 0 else min(4, 1 + c // 4)})
        d += dt.timedelta(days=1)
    return weeks


def fmt_date(iso):
    d = dt.date.fromisoformat(iso)
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


def stats(weeks):
    days = [d for w in weeks for d in w]
    total = sum(d["count"] for d in days)
    active = sum(1 for d in days if d["count"] > 0)
    best = max(days, key=lambda d: d["count"])
    by_wd = [0] * 7
    for d in days:
        by_wd[(dt.date.fromisoformat(d["date"]).weekday() + 1) % 7] += d["count"]
    wd_names = "Sundays Mondays Tuesdays Wednesdays Thursdays Fridays Saturdays".split()
    return [
        (f"{total:,}", "contributions"),
        (f"{active}", f"active days of {len(days)}"),
        (f"{total / len(days):.1f}", "per day on average"),
        (f"{best['count']}", f"best day · {fmt_date(best['date'])}"),
        (wd_names[by_wd.index(max(by_wd))], "most active weekday"),
    ]


def bucket(weeks):
    days = [d for w in weeks for d in w]
    months = {}
    weekday = [0] * 7
    for d in days:
        date = dt.date.fromisoformat(d["date"])
        months[(date.year, date.month)] = months.get((date.year, date.month), 0) + d["count"]
        weekday[(date.weekday() + 1) % 7] += d["count"]
    keys = sorted(months)[-12:]
    return [(k, months[k]) for k in keys], weekday


def bars(o, t, x0, y0, w, h, items, title):
    """Dibuja un panel de barras. items = [(etiqueta, sub_etiqueta, valor)]."""
    o.append(f'<text x="{x0}" y="{y0}" font-size="15" font-weight="600" '
             f'fill="{t["text"]}">{title}</text>')
    top, base = y0 + 32, y0 + h - 40
    for k in range(4):  # líneas guía
        y = base - (base - top) * k / 3
        o.append(f'<line x1="{x0}" x2="{x0 + w}" y1="{y:.1f}" y2="{y:.1f}" '
                 f'stroke="{t["border"]}" stroke-width="1"'
                 f'{"" if k == 0 else " stroke-dasharray=\"2 3\""}/>')
    peak = max(v for _, _, v in items) or 1
    slot = w / len(items)
    bw = min(28, slot * 0.62)
    for i, (label, sub, v) in enumerate(items):
        cx = x0 + slot * i + slot / 2
        bh = (base - top) * v / peak
        color = t["levels"][4] if v == peak and v > 0 else t["levels"][2]
        o.append(f'<rect x="{cx - bw / 2:.1f}" y="{base - bh:.1f}" width="{bw:.1f}" '
                 f'height="{max(bh, 0.01):.1f}" rx="3" fill="{color}">'
                 f'<title>{label} {sub}: {v} contributions</title></rect>')
        o.append(f'<text x="{cx:.1f}" y="{base - bh - 5:.1f}" text-anchor="middle" '
                 f'font-size="13" fill="{t["text"] if v == peak else t["muted"]}">{v}</text>')
        o.append(f'<text x="{cx:.1f}" y="{base + 18}" text-anchor="middle" '
                 f'font-size="13" fill="{t["muted"]}">{label}</text>')
        if sub:
            o.append(f'<text x="{cx:.1f}" y="{base + 33}" text-anchor="middle" '
                     f'font-size="11" fill="{t["muted"]}" opacity="0.7">{sub}</text>')


def render(weeks, theme):
    t = THEMES[theme]
    months, weekday = bucket(weeks)
    width, height = 760, 270
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
         f'viewBox="0 0 {width} {height}" font-family="{FONT}">',
         f'<rect width="{width}" height="{height}" rx="4.5" fill="{t["bg"]}"/>']

    month_items = []
    for i, ((y, m), v) in enumerate(months):
        sub = str(y) if i == 0 or m == 1 else ""
        month_items.append((MONTHS[m - 1], sub, v))
    bars(o, t, 20, 28, 440, 220, month_items, "Contributions per month")
    wd = "Sun Mon Tue Wed Thu Fri Sat".split()
    bars(o, t, 504, 28, 236, 220, [(wd[i], "", weekday[i]) for i in range(7)],
         "By day of the week")
    o.append(f'<line x1="482" x2="482" y1="16" y2="{height - 24}" stroke="{t["border"]}"/>')
    o.append(f'<text x="{width - 14}" y="{height - 8}" text-anchor="end" font-size="11" '
             f'fill="{t["muted"]}" opacity="0.7">Last 12 months · updated '
             f'{dt.date.today():%b %d, %Y}</text>')
    o.append("</svg>")
    return "".join(o)


if __name__ == "__main__":
    if sys.argv[1] == "--demo":
        weeks = demo()
    else:
        weeks = fetch(sys.argv[1])
    out = sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for theme, name in (("dark", "activity-bars-dark.svg"),
                        ("light", "activity-bars.svg")):
        with open(os.path.join(out, name), "w") as f:
            f.write(render(weeks, theme))
