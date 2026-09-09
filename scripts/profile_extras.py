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
ASSETS = ROOT / "assets"

GRAPHQL_URL = "https://api.github.com/graphql"
EVENTS_URL = f"https://api.github.com/users/{USER}/events/public?per_page=100"

QUERY = """
query($login:String!) {
  user(login:$login) {
    repositories(
      first:100
      ownerAffiliations:OWNER
      isFork:false
      orderBy:{field:PUSHED_AT,direction:DESC}
    ) {
      nodes {
        name
        nameWithOwner
        isPrivate
        pushedAt
        languages(first:20, orderBy:{field:SIZE,direction:DESC}) {
          edges { size node { name } }
        }
      }
    }
    repositoriesContributedTo(
      first:50
      contributionTypes:[COMMIT,PULL_REQUEST,REPOSITORY]
      includeUserRepositories:false
      orderBy:{field:PUSHED_AT,direction:DESC}
    ) {
      nodes {
        name
        nameWithOwner
        isPrivate
        pushedAt
        languages(first:20, orderBy:{field:SIZE,direction:DESC}) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""


def request_json(url, data=None):
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "User-Agent": "feelow3555-profile",
        "Accept": "application/vnd.github+json",
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8") if data is not None else None,
        headers=headers,
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def github_data():
    result = request_json(GRAPHQL_URL, {"query": QUERY, "variables": {"login": USER}})
    if result.get("errors"):
        raise RuntimeError(result["errors"])
    return result["data"]["user"]


def time_ago(timestamp):
    if not timestamp:
        return "—"
    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    seconds = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
    if seconds < 3600:
        return f"{max(1, seconds // 60)}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    if seconds < 86400 * 30:
        return f"{seconds // 86400}d ago"
    return dt.strftime("%Y-%m-%d")


def theme(theme_name):
    dark = theme_name == "dark"
    return {
        "bg": "#07090C" if dark else "#FFFFFF",
        "panel": "#0D1117" if dark else "#F6F8FA",
        "panel2": "#11161D" if dark else "#FFFFFF",
        "fg": "#F0F6FC" if dark else "#1F2328",
        "muted": "#8B949E" if dark else "#656D76",
        "border": "#242B35" if dark else "#D0D7DE",
        "track": "#171D25" if dark else "#EAECEF",
        "accent": "#FF7A00",
    }


def shell(theme_name, height, title, subtitle):
    c = theme(theme_name)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="{height}" viewBox="0 0 1100 {height}">
<style>
text {{ font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
.eyebrow {{ fill:{c["muted"]}; font-size:12px; font-weight:700; letter-spacing:2px; }}
.title {{ fill:{c["fg"]}; font-size:20px; font-weight:800; }}
.body {{ fill:{c["fg"]}; font-size:14px; }}
.small {{ fill:{c["muted"]}; font-size:12px; }}
.metric {{ fill:{c["fg"]}; font-size:26px; font-weight:800; }}
</style>
<rect x="0.5" y="0.5" width="1099" height="{height-1}" rx="22" fill="{c["bg"]}" stroke="{c["border"]}"/>
<rect x="24" y="24" width="1052" height="{height-48}" rx="18" fill="{c["panel"]}" stroke="{c["border"]}"/>
<rect x="24" y="24" width="6" height="{height-48}" rx="3" fill="{c["accent"]}"/>
<text x="52" y="58" class="eyebrow">{escape(title)}</text>
<text x="1048" y="58" class="small" text-anchor="end">{escape(subtitle)}</text>
'''
    return c, svg


def recent_commits():
    events = request_json(EVENTS_URL)
    rows = []
    seen = set()

    for event in events:
        if event.get("type") != "PushEvent":
            continue
        repo = event.get("repo", {}).get("name", "")
        if not repo or repo == f"{USER}/{USER}":
            continue

        when = time_ago(event.get("created_at"))
        commits = event.get("payload", {}).get("commits", [])
        for commit in reversed(commits):
            message = (commit.get("message") or "commit").splitlines()[0].strip()
            key = (repo, message)
            if key in seen:
                continue
            seen.add(key)
            rows.append((repo.split("/")[-1], message, when))
            if len(rows) >= 5:
                return rows
    return rows


def build_commits(theme_name):
    c, svg = shell(theme_name, 300, "RECENT COMMITS", "LATEST PUBLIC PUSHES")
    rows = recent_commits()

    if not rows:
        svg += '<text x="52" y="112" class="small">no recent public commits</text>'
    else:
        y = 104
        for repo, message, when in rows:
            message = message if len(message) <= 68 else message[:65] + "..."
            svg += f'''
<circle cx="58" cy="{y-5}" r="4" fill="{c["accent"]}">
  <animate attributeName="opacity" values="1;.35;1" dur="2.6s" repeatCount="indefinite"/>
</circle>
<text x="76" y="{y}" class="body">{escape(repo)}</text>
<text x="278" y="{y}" class="small">{escape(message)}</text>
<text x="1028" y="{y}" class="small" text-anchor="end">{escape(when)}</text>
'''
            if y < 240:
                svg += f'<line x1="76" y1="{y+18}" x2="1028" y2="{y+18}" stroke="{c["border"]}"/>'
            y += 39

    svg += '</svg>'
    return svg


def normalize_repos(user):
    result, seen = [], set()
    for source in (user["repositories"]["nodes"], user["repositoriesContributedTo"]["nodes"]):
        for repo in source:
            if repo.get("isPrivate"):
                continue
            owner = repo.get("nameWithOwner") or f"{USER}/{repo['name']}"
            if owner == f"{USER}/{USER}" or owner in seen:
                continue
            seen.add(owner)
            item = dict(repo)
            item["nameWithOwner"] = owner
            result.append(item)
    return result


def codebase_data(user):
    repos = normalize_repos(user)
    totals = {}
    for repo in repos:
        for edge in repo.get("languages", {}).get("edges", []):
            name = edge["node"]["name"]
            totals[name] = totals.get(name, 0) + int(edge["size"])
    total = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:6]
    return [(name, size / total * 100) for name, size in ranked], len(repos)


def build_codebase(theme_name, user):
    c, svg = shell(theme_name, 365, "CODEBASE MAP", "REAL REPOSITORY LANGUAGE DATA")
    langs, repo_count = codebase_data(user)

    svg += f'''
<text x="52" y="100" class="metric">{repo_count} repos</text>
<text x="52" y="124" class="small">owned + contributed public repositories</text>
'''

    if not langs:
        svg += '<text x="52" y="170" class="small">no language data</text></svg>'
        return svg

    # Stable proportional strip: looks good even when the user has not committed recently.
    x0, y0, total_w, h, gap = 52, 154, 996, 112, 6
    pct_sum = sum(p for _, p in langs) or 1
    raw_widths = [total_w * (p / pct_sum) for _, p in langs]
    min_w = 82
    widths = [max(min_w, w) for w in raw_widths]
    scale = (total_w - gap * (len(widths)-1)) / sum(widths)
    widths = [w * scale for w in widths]

    x = x0
    for i, ((name, pct), w) in enumerate(zip(langs, widths)):
        opacity = max(.34, 1 - i * .11)
        svg += f'''
<rect x="{x:.1f}" y="{y0}" width="{w:.1f}" height="{h}" rx="12" fill="{c["panel2"]}" stroke="{c["accent"]}" stroke-opacity="{opacity:.2f}"/>
<text x="{x+14:.1f}" y="{y0+35}" class="body">{escape(name)}</text>
<text x="{x+14:.1f}" y="{y0+70}" class="title">{pct:.1f}%</text>
'''
        x += w + gap

    svg += f'''
<text x="52" y="310" class="eyebrow">CODE, NOT SELF-RATING</text>
<text x="52" y="336" class="small">calculated from GitHub language bytes across the visible codebase</text>
<circle cx="1028" cy="321" r="5" fill="{c["accent"]}">
  <animate attributeName="r" values="4;7;4" dur="2.8s" repeatCount="indefinite"/>
  <animate attributeName="opacity" values="1;.35;1" dur="2.8s" repeatCount="indefinite"/>
</circle>
</svg>
'''
    return svg


def build_system_map(theme_name):
    c, svg = shell(theme_name, 430, "SYSTEM MAP", "HOW I CONNECT THE PIECES")

    nodes = {
        "AI / LLM": (550, 108),
        "VISION": (245, 200),
        "RAG": (445, 200),
        "AGENT": (655, 200),
        "AUTOMATION": (855, 200),
        "BACKEND": (550, 286),
        "SPRING": (235, 366),
        "REDIS": (445, 366),
        "POSTGRES": (655, 366),
        "AWS": (865, 366),
    }

    edges = [
        ("AI / LLM", "VISION"), ("AI / LLM", "RAG"),
        ("AI / LLM", "AGENT"), ("AI / LLM", "AUTOMATION"),
        ("VISION", "BACKEND"), ("RAG", "BACKEND"),
        ("AGENT", "BACKEND"), ("AUTOMATION", "BACKEND"),
        ("BACKEND", "SPRING"), ("BACKEND", "REDIS"),
        ("BACKEND", "POSTGRES"), ("BACKEND", "AWS"),
    ]

    for a, b in edges:
        x1, y1 = nodes[a]
        x2, y2 = nodes[b]
        svg += f'''
<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{c["border"]}" stroke-width="2" stroke-dasharray="5 7">
  <animate attributeName="stroke-dashoffset" values="24;0" dur="3s" repeatCount="indefinite"/>
</line>
'''

    for i, (name, (x, y)) in enumerate(nodes.items()):
        main = name in ("AI / LLM", "BACKEND")
        r = 9 if main else 6
        cls = "title" if main else "body"
        dur = 2.2 + (i % 4) * 0.3
        svg += f'''
<circle cx="{x}" cy="{y}" r="{r}" fill="{c["accent"]}">
  <animate attributeName="opacity" values="1;.4;1" dur="{dur:.1f}s" repeatCount="indefinite"/>
</circle>
<text x="{x}" y="{y-18}" class="{cls}" text-anchor="middle">{escape(name)}</text>
'''

    svg += '</svg>'
    return svg


def main():
    ASSETS.mkdir(exist_ok=True)
    user = github_data()

    for theme_name in ("dark", "light"):
        (ASSETS / f"commits-{theme_name}.svg").write_text(
            build_commits(theme_name), encoding="utf-8"
        )
        (ASSETS / f"codebase-{theme_name}.svg").write_text(
            build_codebase(theme_name, user), encoding="utf-8"
        )
        (ASSETS / f"system-map-{theme_name}.svg").write_text(
            build_system_map(theme_name), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
