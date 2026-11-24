"""Redraw the activity chart in the profile hero from the GitHub contribution calendar.

Standard library only. Reads assets/hero.json (written when the hero was designed) for the
geometry, colours and letter outlines of each hero file, then replaces the part of each SVG
between the chart markers.

Each candle is one week of the 4-week running total of contributions: where the total stood
when the week began and ended, and the highest and lowest it reached in between. The bars
under the candles are that week's own contributions. Both use a square-root scale.
"""
import json
import math
import os
import re
import sys
import urllib.request

QUERY = ("query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{"
         "totalContributions weeks{contributionDays{date contributionCount}}}}}}")
MONTHS = "JFMAMJJASOND"


def fetch(login):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": "bearer " + os.environ["GITHUB_TOKEN"], "User-Agent": "profile-activity"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def n(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


def candles(days, k=48):
    c = [d["contributionCount"] for d in days]
    roll = [sum(c[max(0, i - 27):i + 1]) for i in range(len(c))]
    k = min(k, (len(c) - 1) // 7)
    out = []
    for j in range(k):
        e = len(c) - 1 - (k - 1 - j) * 7
        s = e - 6
        seg = roll[s - 1:e + 1]
        out.append(dict(o=seg[0], c=seg[-1], h=max(seg), l=min(seg), v=sum(c[s:e + 1]), end=days[e]["date"]))
    return out


def text(t, s, size, x, y, anchor="start"):
    g = t["glyphs"]
    sc = size / g["upm"]
    blank = [None, g["upm"] * .6]
    w = sum(g["map"].get(ch, blank)[1] for ch in s) * sc
    cx = x - w if anchor == "end" else x - w / 2 if anchor == "middle" else x
    uses, pen = [], 0.0
    for ch in s:
        gid, adv = g["map"].get(ch, blank)
        if gid:
            uses.append(f'<use href="#{gid}" x="{pen:.0f}"/>')
        pen += adv
    return f'<g transform="translate({n(cx)} {n(y)}) scale({sc:.5g} {-sc:.5g})">{"".join(uses)}</g>'


def chart(cal, t):
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    cs = candles(days)
    P = t["pal"]
    x0, y0, x1, y1 = t["box"]
    f = math.sqrt
    top = f(max(max(c["h"] for c in cs), 1)) * 1.06
    sy = lambda v: y1 - f(v) / top * (y1 - y0)
    st = (x1 - x0) / len(cs)
    vy, vh = t["vol"]
    mv = f(max(max(c["v"] for c in cs), 1))
    fw = t["flag"]
    o = []
    for j in range(5):
        o.append(f'<path d="M{x0} {n(y0 + j * (y1 - y0) / 4)}H{x1 + fw + 6}" stroke="{P["grid"]}"/>')
    prev = None
    for i, c in enumerate(cs):
        x = x0 + st * (i + .5)
        flat = c["h"] == c["l"]
        col = P["mute"] if flat else P["up"] if c["c"] >= c["o"] else P["dn"]
        a, b = sy(max(c["o"], c["c"])), sy(min(c["o"], c["c"]))
        dl = .3 + i * .022
        live = ' class="live"' if i == len(cs) - 1 and b - a > 6 else ""
        o.append(f'<g class="g" style="animation-delay:{dl:.2f}s"><path d="M{n(x)} {n(sy(c["h"]))}V{n(sy(c["l"]))}" stroke="{col}" stroke-width="{t["wick"]}"/>'
                 f'<rect{live} x="{n(x - st * .32)}" y="{n(min(a, y1 - 2))}" width="{n(st * .64)}" height="{n(max(2, b - a))}" fill="{col}"/></g>')
        h = f(c["v"]) / mv * vh
        if h > .5:
            o.append(f'<rect class="g" style="animation-delay:{dl:.2f}s" x="{n(x - st * .32)}" y="{n(vy - h)}" width="{n(st * .64)}" height="{n(h)}" fill="{P["mute"]}" opacity=".32"/>')
        m = int(c["end"][5:7])
        if prev is not None and m != prev:
            o.append(f'<g fill="{P["mute"]}">{text(t, MONTHS[m - 1], t["msize"], x, t["months_y"], "middle")}</g>')
        prev = m
    ly = sy(cs[-1]["c"])
    o.append(f'<path class="f" style="animation-delay:1.5s" d="M{x0} {n(ly)}H{x1 + 4}" stroke="{P["up"]}" stroke-dasharray="3 4"/>'
             f'<g class="blink"><rect x="{x1 + 6}" y="{n(ly - fw * .24)}" width="{fw}" height="{n(fw * .48)}" rx="4" fill="{P["up"]}"/>'
             f'<g fill="{P["bg"]}">{text(t, "NOW", t["msize"], x1 + 6 + fw / 2, ly + t["msize"] * .35, "middle")}</g></g>')
    tx, ty, anchor = t["total"]
    total = f'{cal["totalContributions"]:,} in the past year'
    o.append(f'<g fill="{P["ink"]}">{text(t, total, t["tsize"], tx, ty, anchor)}</g>')
    return "".join(o)


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    cfg = json.load(open(os.path.join(root, "assets", "hero.json"), encoding="utf-8"))
    cal = json.load(open(sys.argv[2], encoding="utf-8")) if len(sys.argv) > 2 else fetch(cfg["login"])
    for t in cfg["targets"]:
        path = os.path.join(root, t["file"])
        svg = open(path, encoding="utf-8").read()
        new = re.sub(r"<!--chart-->.*?<!--/chart-->", lambda _: "<!--chart-->" + chart(cal, t) + "<!--/chart-->", svg, flags=re.S)
        if new != svg:
            open(path, "w", encoding="utf-8", newline="\n").write(new)
            print("updated", t["file"])


if __name__ == "__main__":
    main()
