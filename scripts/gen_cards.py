#!/usr/bin/env python3
"""Generate profile SVG cards (stats, top languages, pinned repos) from GitHub GraphQL API.

Usage: GITHUB_TOKEN=... python scripts/gen_cards.py <username> <repo> [<repo> ...]
Writes SVGs to ./cards/.
"""
import json
import os
import sys
import urllib.request
from html import escape
from pathlib import Path

API = "https://api.github.com/graphql"
OUT = Path("cards")

BG, BORDER, TITLE, TEXT, ICON = "#1a1b27", "#2f3346", "#70a5fd", "#a9b1d6", "#bf91f3"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif"


def gql(query, variables):
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"bearer {os.environ['GITHUB_TOKEN']}",
            "Content-Type": "application/json",
            "User-Agent": "profile-cards",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if body.get("errors"):
        raise SystemExit(f"GraphQL error: {body['errors']}")
    return body["data"]


USER_Q = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    name
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
    }
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}"""

REPO_Q = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    name description stargazerCount forkCount
    primaryLanguage { name color }
  }
}"""


def fetch_user(login):
    repos, cursor, user = [], None, None
    while True:
        u = gql(USER_Q, {"login": login, "cursor": cursor})["user"]
        user = user or u
        repos += u["repositories"]["nodes"]
        page = u["repositories"]["pageInfo"]
        if not page["hasNextPage"]:
            break
        cursor = page["endCursor"]
    user["all_repos"] = repos
    return user


def frame(w, h, title, body):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}">
<style>text{{font-family:{FONT}}} .t{{font-size:18px;font-weight:600;fill:{TITLE}}} .l{{font-size:14px;fill:{TEXT}}} .v{{font-size:14px;font-weight:700;fill:{TEXT}}} .s{{font-size:12px;fill:{TEXT}}}</style>
<rect x="0.5" y="0.5" rx="4.5" width="{w-1}" height="{h-1}" fill="{BG}" stroke="{BORDER}"/>
<text x="25" y="35" class="t">{escape(title)}</text>
{body}
</svg>
"""


def stats_card(u, login):
    stars = sum(r["stargazerCount"] for r in u["all_repos"])
    cc = u["contributionsCollection"]
    rows = [
        ("Total stars", stars),
        ("Commits (last year)", cc["totalCommitContributions"] + cc["restrictedContributionsCount"]),
        ("Pull requests", u["pullRequests"]["totalCount"]),
        ("Issues", u["issues"]["totalCount"]),
        ("Repositories", u["repositories"]["totalCount"]),
        ("Followers", u["followers"]["totalCount"]),
    ]
    body = "".join(
        f'<circle cx="31" cy="{66 + i*25}" r="4" fill="{ICON}"/>'
        f'<text x="45" y="{71 + i*25}" class="l">{label}:</text>'
        f'<text x="260" y="{71 + i*25}" class="v">{val:,}</text>'
        for i, (label, val) in enumerate(rows)
    )
    name = u["name"] or login
    return frame(360, 70 + len(rows) * 25, f"{name}'s GitHub Stats", body)


def langs_card(u, n=8):
    totals, colors = {}, {}
    for r in u["all_repos"]:
        for e in r["languages"]["edges"]:
            nm = e["node"]["name"]
            totals[nm] = totals.get(nm, 0) + e["size"]
            colors[nm] = e["node"]["color"] or "#858585"
    top = sorted(totals.items(), key=lambda kv: -kv[1])[:n]
    total = sum(v for _, v in top) or 1
    w, bar_w = 360, 310
    x, bar = 25, []
    for nm, v in top:
        seg = bar_w * v / total
        bar.append(f'<rect x="{x:.2f}" y="55" width="{seg:.2f}" height="8" fill="{colors[nm]}"/>')
        x += seg
    legend = []
    for i, (nm, v) in enumerate(top):
        cx, cy = 25 + (i % 2) * 160, 90 + (i // 2) * 24
        legend.append(
            f'<circle cx="{cx+5}" cy="{cy-4}" r="5" fill="{colors[nm]}"/>'
            f'<text x="{cx+16}" y="{cy}" class="s">{escape(nm)} {100*v/total:.1f}%</text>'
        )
    body = (f'<clipPath id="c"><rect x="25" y="55" width="{bar_w}" height="8" rx="4"/></clipPath>'
            f'<g clip-path="url(#c)">{"".join(bar)}</g>{"".join(legend)}')
    return frame(w, 90 + ((len(top) + 1) // 2) * 24, "Most Used Languages", body)


def wrap(text, width=52, lines=2):
    words, out, cur = text.split(), [], ""
    for wd in words:
        if len(cur) + len(wd) + 1 > width:
            out.append(cur)
            cur = wd
            if len(out) == lines:
                break
        else:
            cur = f"{cur} {wd}".strip()
    else:
        out.append(cur)
    if len(out) > lines or (len(out) == lines and cur and cur not in out):
        out = out[:lines]
        out[-1] = out[-1].rstrip(".,") + "…"
    return out[:lines]


def pin_card(owner, name):
    r = gql(REPO_Q, {"owner": owner, "name": name})["repository"]
    desc = wrap(r["description"] or "No description provided.")
    body = "".join(f'<text x="25" y="{62 + i*20}" class="s">{escape(line)}</text>' for i, line in enumerate(desc))
    foot, x = [], 25
    if r["primaryLanguage"]:
        lang = r["primaryLanguage"]
        foot.append(f'<circle cx="{x+6}" cy="116" r="6" fill="{lang["color"] or "#858585"}"/>'
                    f'<text x="{x+18}" y="120" class="s">{escape(lang["name"])}</text>')
        x += 30 + 7 * len(lang["name"])
    foot.append(f'<text x="{x}" y="120" class="s">★ {r["stargazerCount"]}</text>')
    foot.append(f'<text x="{x+55}" y="120" class="s">⑂ {r["forkCount"]}</text>')
    return frame(400, 140, r["name"], body + "".join(foot))


def main():
    login, pins = sys.argv[1], sys.argv[2:]
    OUT.mkdir(exist_ok=True)
    u = fetch_user(login)
    (OUT / "stats.svg").write_text(stats_card(u, login))
    (OUT / "top-langs.svg").write_text(langs_card(u))
    for p in pins:
        (OUT / f"pin-{p}.svg").write_text(pin_card(login, p))
    print(f"wrote {2 + len(pins)} cards to {OUT}/")


if __name__ == "__main__":
    main()
