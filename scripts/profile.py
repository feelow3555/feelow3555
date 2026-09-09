#!/usr/bin/env python3
import os
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from html import escape

USER = os.getenv("PROFILE_USER", "feelow3555")
TOKEN = os.environ["GITHUB_TOKEN"]
ROOT = Path(__file__).resolve().parents[1]

GRAPHQL = "https://api.github.com/graphql"
EVENTS = f"https://api.github.com/users/{USER}/events/public?per_page=30"

QUERY = '''
query($login:String!) {
  user(login:$login) {
    name
    login
    followers { totalCount }
    repositories(
      first: 100,
      ownerAffiliations: OWNER,
      isFork: false,
      orderBy: {field: PUSHED_AT, direction: DESC}
    ) {
      totalCount
      nodes {
        name
        url
        pushedAt
        stargazerCount
        isPrivate
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      contributionCalendar { totalContributions }
    }
  }
}
'''

def request_json(url, data=None):
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "User-Agent": "feelow3555-profile",
        "Accept": "application/vnd.github+json",
    }
    req = urllib.request.Request(
        url,
        data=(json.dumps(data).encode() if data is not None else None),
        headers=headers,
        method=("POST" if data is not None else "GET"),
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def github_data():
    out = request_json(GRAPHQL, {"query": QUERY, "variables": {"login": USER}})
    if out.get("errors"):
        raise RuntimeError(out["errors"])
    return out["data"]["user"]

def aggregate_languages(repos):
    totals = {}
    for repo in repos:
        if repo.get("isPrivate"):
            continue
        for edge in repo.get("languages", {}).get("edges", []):
            lang = edge["node"]["name"]
            totals[lang] = totals.get(lang, 0) + int(edge["size"])
    total = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:5]
    return [(k, v / total * 100) for k, v in ranked]

def time_ago(ts):
    if not ts:
        return "—"
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    delta = datetime.now(timezone.utc) - dt
    sec = max(0, int(delta.total_seconds()))
    if sec < 3600:
        return f"{max(1, sec//60)}m ago"
    if sec < 86400:
        return f"{sec//3600}h ago"
    if sec < 86400 * 30:
        return f"{sec//86400}d ago"
    return dt.strftime("%Y-%m-%d")

def svg(theme, user):
    dark = theme == "dark"
    bg = "#0d1117" if dark else "#ffffff"
    fg = "#f0f6fc" if dark else "#1f2328"
    muted = "#8b949e" if dark else "#656d76"
    border = "#30363d" if dark else "#d0d7de"
    track = "#21262d" if dark else "#eaeef2"
    accent = "#ff7a00"

    repos = user["repositories"]["nodes"]
    langs = aggregate_languages(repos)
    latest = repos[0] if repos else None
    stars = sum(int(r["stargazerCount"]) for r in repos)
    contrib = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]

    width, height = 980, 330
    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<style>
text {{ font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }}
.label {{ fill:{muted}; font-size:13px; font-weight:600; letter-spacing:1.4px; }}
.big {{ fill:{fg}; font-size:32px; font-weight:700; }}
.value {{ fill:{fg}; font-size:18px; font-weight:650; }}
.small {{ fill:{muted}; font-size:13px; }}
.lang {{ fill:{fg}; font-size:14px; font-weight:600; }}
</style>
<rect x="0.5" y="0.5" width="{width-1}" height="{height-1}" rx="14" fill="{bg}" stroke="{border}"/>
<circle cx="34" cy="35" r="5" fill="{accent}"/>
<text x="51" y="40" class="label">GITHUB / LIVE</text>

<text x="34" y="95" class="big">{escape(str(contrib))}</text>
<text x="34" y="119" class="small">contributions · last year</text>

<text x="280" y="95" class="big">{escape(str(user["repositories"]["totalCount"]))}</text>
<text x="280" y="119" class="small">repositories</text>

<text x="470" y="95" class="big">{escape(str(stars))}</text>
<text x="470" y="119" class="small">stars</text>

<text x="650" y="75" class="label">LATEST PUSH</text>
<text x="650" y="101" class="value">{escape(latest["name"] if latest else "—")}</text>
<text x="650" y="124" class="small">{escape(time_ago(latest["pushedAt"]) if latest else "—")}</text>

<line x1="34" y1="154" x2="946" y2="154" stroke="{border}"/>
<text x="34" y="187" class="label">LANGUAGES</text>
''']

    base_y = 216
    for i, (name, pct) in enumerate(langs):
        yy = base_y + i * 22
        bar_x = 160
        bar_w = 430
        fill_w = max(2, bar_w * pct / 100)
        parts += [
            f'<text x="34" y="{yy+4}" class="lang">{escape(name)}</text>',
            f'<rect x="{bar_x}" y="{yy-7}" width="{bar_w}" height="8" rx="4" fill="{track}"/>',
            f'<rect x="{bar_x}" y="{yy-7}" width="{fill_w:.1f}" height="8" rx="4" fill="{accent}" opacity="{max(.28, 1-i*.13):.2f}"/>',
            f'<text x="610" y="{yy+4}" class="small">{pct:.1f}%</text>',
        ]

    parts += [
        f'<text x="790" y="187" class="label">PROFILE</text>',
        f'<text x="790" y="218" class="value">@{escape(USER)}</text>',
        f'<text x="790" y="242" class="small">{escape(str(user["followers"]["totalCount"]))} followers</text>',
        f'<text x="790" y="267" class="small">auto-updated</text>',
        '</svg>'
    ]
    return "".join(parts)

def recent_activity():
    events = request_json(EVENTS)
    rows = []
    seen = set()
    for ev in events:
        typ = ev.get("type")
        repo = ev.get("repo", {}).get("name", "")
        created = ev.get("created_at")
        key = (typ, repo)
        if key in seen:
            continue
        seen.add(key)

        if typ == "PushEvent":
            commits = len(ev.get("payload", {}).get("commits", []))
            n = str(commits) if commits else ""
            text = f"pushed {n} commit{'s' if commits != 1 else ''} to `{repo}`".replace("  ", " ")
            icon = "↳"
        elif typ == "PullRequestEvent":
            action = ev.get("payload", {}).get("action", "updated")
            text = f"{action} a pull request in `{repo}`"
            icon = "↗"
        elif typ == "CreateEvent":
            ref_type = ev.get("payload", {}).get("ref_type", "repository")
            text = f"created {ref_type} in `{repo}`"
            icon = "+"
        elif typ == "IssuesEvent":
            action = ev.get("payload", {}).get("action", "updated")
            text = f"{action} an issue in `{repo}`"
            icon = "!"
        elif typ == "ReleaseEvent":
            action = ev.get("payload", {}).get("action", "published")
            text = f"{action} a release in `{repo}`"
            icon = "◆"
        else:
            continue
        rows.append(f"- `{icon}` {text} · {time_ago(created)}")
        if len(rows) >= 5:
            break
    return "\n".join(rows) if rows else "_No recent public activity._"

def update_readme(activity):
    p = ROOT / "README.md"
    s = p.read_text(encoding="utf-8")
    a = "<!-- RECENT_ACTIVITY:START -->"
    b = "<!-- RECENT_ACTIVITY:END -->"
    before, rest = s.split(a, 1)
    _, after = rest.split(b, 1)
    p.write_text(before + a + "\\n" + activity + "\\n" + b + after, encoding="utf-8")

def main():
    user = github_data()
    (ROOT / "assets").mkdir(exist_ok=True)
    (ROOT / "assets/dashboard-dark.svg").write_text(svg("dark", user), encoding="utf-8")
    (ROOT / "assets/dashboard-light.svg").write_text(svg("light", user), encoding="utf-8")
    update_readme(recent_activity())

if __name__ == "__main__":
    main()
