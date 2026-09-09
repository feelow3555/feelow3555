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

GRAPHQL_URL = "https://api.github.com/graphql"
EVENTS_URL = f"https://api.github.com/users/{USER}/events/public?per_page=50"

QUERY = """
query($login:String!) {
  user(login:$login) {
    login
    followers { totalCount }

    repositories(
      first: 100
      ownerAffiliations: OWNER
      isFork: false
      orderBy: {field: PUSHED_AT, direction: DESC}
    ) {
      nodes {
        name
        url
        description
        pushedAt
        stargazerCount
        isPrivate
        primaryLanguage { name color }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges {
            size
            node { name color }
          }
        }
      }
    }

    repositoriesContributedTo(
      first: 50
      contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]
      includeUserRepositories: false
      orderBy: {field: PUSHED_AT, direction: DESC}
    ) {
      nodes {
        name
        nameWithOwner
        url
        description
        pushedAt
        stargazerCount
        isPrivate
        primaryLanguage { name color }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges {
            size
            node { name color }
          }
        }
      }
    }

    contributionsCollection {
      contributionCalendar {
        totalContributions
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
    result = request_json(
        GRAPHQL_URL,
        {"query": QUERY, "variables": {"login": USER}}
    )

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

def normalize_repos(user):
    result = []
    seen = set()

    for repo in user["repositories"]["nodes"]:
        if repo["name"] == USER:
            continue

        item = dict(repo)
        item["nameWithOwner"] = f"{USER}/{repo['name']}"

        if item["nameWithOwner"] in seen:
            continue

        seen.add(item["nameWithOwner"])
        result.append(item)

    for repo in user["repositoriesContributedTo"]["nodes"]:
        if repo["isPrivate"]:
            continue

        key = repo["nameWithOwner"]

        if key in seen:
            continue

        seen.add(key)
        result.append(repo)

    result.sort(
        key=lambda r: r.get("pushedAt") or "",
        reverse=True
    )

    return result

def aggregate_languages(repos):
    totals = {}

    for repo in repos:
        if repo.get("isPrivate"):
            continue

        for edge in repo.get("languages", {}).get("edges", []):
            name = edge["node"]["name"]
            totals[name] = totals.get(name, 0) + int(edge["size"])

    total = sum(totals.values()) or 1

    return [
        (name, size / total * 100)
        for name, size in sorted(
            totals.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
    ]

def recent_events():
    events = request_json(EVENTS_URL)
    rows = []
    seen = set()

    for event in events:
        repo = event.get("repo", {}).get("name", "")
        event_type = event.get("type", "")

        if not repo or repo == f"{USER}/{USER}":
            continue

        key = (event_type, repo)
        if key in seen:
            continue
        seen.add(key)

        when = time_ago(event.get("created_at"))
        short_repo = repo.split("/")[-1]

        if event_type == "PushEvent":
            count = len(event.get("payload", {}).get("commits", []))
            label = f"push · {short_repo} · {count} commit" + ("" if count == 1 else "s")
        elif event_type == "PullRequestEvent":
            action = event.get("payload", {}).get("action", "updated")
            label = f"PR {action} · {short_repo}"
        elif event_type == "CreateEvent":
            ref_type = event.get("payload", {}).get("ref_type", "repo")
            label = f"created {ref_type} · {short_repo}"
        elif event_type == "IssuesEvent":
            action = event.get("payload", {}).get("action", "updated")
            label = f"issue {action} · {short_repo}"
        else:
            continue

        rows.append((label, when))

        if len(rows) >= 4:
            break

    return rows

def svg_text(text):
    return escape(str(text))

def build_dashboard(theme, user):
    dark = theme == "dark"

    BG = "#07090C" if dark else "#FFFFFF"
    PANEL = "#0D1117" if dark else "#F6F8FA"
    PANEL2 = "#11161D" if dark else "#FFFFFF"
    FG = "#F0F6FC" if dark else "#1F2328"
    MUTED = "#8B949E" if dark else "#656D76"
    BORDER = "#242B35" if dark else "#D0D7DE"
    TRACK = "#171D25" if dark else "#EAECEF"
    ACCENT = "#FF7A00"

    repos = normalize_repos(user)
    latest = repos[0] if repos else None
    languages = aggregate_languages(repos)
    events = recent_events()

    contributions = (
        user["contributionsCollection"]
        ["contributionCalendar"]
        ["totalContributions"]
    )

    stars = sum(int(r.get("stargazerCount", 0)) for r in repos)
    repo_count = len(repos)

    latest_name = latest["name"] if latest else "—"
    latest_owner = latest["nameWithOwner"] if latest else "—"
    latest_lang = (
        latest.get("primaryLanguage", {}).get("name", "—")
        if latest and latest.get("primaryLanguage")
        else "—"
    )
    latest_time = time_ago(latest.get("pushedAt")) if latest else "—"

    width = 1100
    height = 520

    svg = f"""
<svg xmlns="http://www.w3.org/2000/svg"
     width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<style>
  text {{
    font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }}
  .eyebrow {{
    fill: {MUTED};
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 2px;
  }}
  .title {{
    fill: {FG};
    font-size: 28px;
    font-weight: 800;
  }}
  .metric {{
    fill: {FG};
    font-size: 31px;
    font-weight: 800;
  }}
  .label {{
    fill: {MUTED};
    font-size: 12px;
  }}
  .body {{
    fill: {FG};
    font-size: 14px;
  }}
  .small {{
    fill: {MUTED};
    font-size: 12px;
  }}
  .accent {{
    fill: {ACCENT};
  }}
</style>

<rect x="0.5" y="0.5" width="1099" height="519" rx="22"
      fill="{BG}" stroke="{BORDER}"/>

<rect x="24" y="24" width="1052" height="472" rx="18"
      fill="{PANEL}" stroke="{BORDER}"/>

<rect x="24" y="24" width="6" height="472" rx="3" fill="{ACCENT}"/>

<text x="52" y="58" class="eyebrow">DEVELOPER STATUS</text>
<circle cx="1015" cy="52" r="5" fill="{ACCENT}"/>
<text x="1028" y="56" class="small">LIVE</text>

<text x="52" y="100" class="title">@{svg_text(USER)}</text>
<text x="52" y="126" class="small">github data · generated automatically</text>

<rect x="52" y="157" width="212" height="108" rx="14"
      fill="{PANEL2}" stroke="{BORDER}"/>
<text x="72" y="184" class="eyebrow">CONTRIBUTIONS</text>
<text x="72" y="227" class="metric">{svg_text(contributions)}</text>
<text x="72" y="248" class="small">last 12 months</text>

<rect x="280" y="157" width="178" height="108" rx="14"
      fill="{PANEL2}" stroke="{BORDER}"/>
<text x="300" y="184" class="eyebrow">REPOS</text>
<text x="300" y="227" class="metric">{svg_text(repo_count)}</text>
<text x="300" y="248" class="small">owned + contributed</text>

<rect x="474" y="157" width="155" height="108" rx="14"
      fill="{PANEL2}" stroke="{BORDER}"/>
<text x="494" y="184" class="eyebrow">STARS</text>
<text x="494" y="227" class="metric">{svg_text(stars)}</text>
<text x="494" y="248" class="small">public repos</text>

<rect x="645" y="157" width="403" height="108" rx="14"
      fill="{PANEL2}" stroke="{BORDER}"/>
<text x="665" y="184" class="eyebrow">NOW BUILDING</text>
<text x="665" y="214" class="body">{svg_text(latest_name)}</text>
<text x="665" y="237" class="small">{svg_text(latest_owner)}</text>
<text x="665" y="256" class="small">{svg_text(latest_lang)} · {svg_text(latest_time)}</text>

<rect x="52" y="286" width="577" height="180" rx="14"
      fill="{PANEL2}" stroke="{BORDER}"/>
<text x="72" y="314" class="eyebrow">LANGUAGE ACTIVITY</text>

<rect x="645" y="286" width="403" height="180" rx="14"
      fill="{PANEL2}" stroke="{BORDER}"/>
<text x="665" y="314" class="eyebrow">RECENT SIGNALS</text>
"""

    base_y = 344

    for i, (name, pct) in enumerate(languages):
        y = base_y + i * 25
        bar_x = 180
        bar_w = 320
        fill_w = max(3, bar_w * pct / 100)
        opacity = max(0.35, 1.0 - i * 0.12)

        svg += f"""
<text x="72" y="{y}" class="body">{svg_text(name)}</text>
<rect x="{bar_x}" y="{y-10}" width="{bar_w}" height="8" rx="4" fill="{TRACK}"/>
<rect x="{bar_x}" y="{y-10}" width="{fill_w:.1f}" height="8" rx="4"
      fill="{ACCENT}" opacity="{opacity:.2f}"/>
<text x="518" y="{y}" class="small">{pct:.1f}%</text>
"""

    event_y = 348
    for i, (label, when) in enumerate(events):
        y = event_y + i * 31
        svg += f"""
<circle cx="669" cy="{y-5}" r="3" fill="{ACCENT}"/>
<text x="682" y="{y}" class="body">{svg_text(label)}</text>
<text x="1017" y="{y}" class="small" text-anchor="end">{svg_text(when)}</text>
"""

    if not events:
        svg += f'<text x="665" y="354" class="small">no recent public activity</text>'

    svg += f"""
<text x="52" y="488" class="small">structure / build / verify / improve</text>
<text x="1048" y="488" class="small" text-anchor="end">accent #{ACCENT[1:]}</text>
</svg>
"""

    return svg

def main():
    user = github_data()

    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)

    (assets / "dashboard-dark.svg").write_text(
        build_dashboard("dark", user),
        encoding="utf-8"
    )

    (assets / "dashboard-light.svg").write_text(
        build_dashboard("light", user),
        encoding="utf-8"
    )

if __name__ == "__main__":
    main()
