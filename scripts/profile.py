#!/usr/bin/env python3

import os
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from html import escape

USER = os.getenv("PROFILE_USER", "feelow3555")
TOKEN = os.environ["GITHUB_TOKEN"]
ROOT = Path(__file__).resolve().parents[1]

GRAPHQL_URL = "https://api.github.com/graphql"
EVENTS_URL = f"https://api.github.com/users/{USER}/events/public?per_page=100"

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
        nameWithOwner
        url
        description
        pushedAt
        stargazerCount
        isPrivate
        primaryLanguage { name color }
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
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
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
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
        "X-GitHub-Api-Version": "2022-11-28",
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
        {"query": QUERY, "variables": {"login": USER}},
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
        item["nameWithOwner"] = repo.get("nameWithOwner") or f"{USER}/{repo['name']}"

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
        reverse=True,
    )

    return result


def aggregate_languages(repos, limit=6):
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
            reverse=True,
        )[:limit]
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
            label = f"push · {short_repo}"
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


def get_theme(theme):
    dark = theme == "dark"

    return {
        "BG": "#07090C" if dark else "#FFFFFF",
        "PANEL": "#0D1117" if dark else "#F6F8FA",
        "PANEL2": "#11161D" if dark else "#FFFFFF",
        "FG": "#F0F6FC" if dark else "#1F2328",
        "MUTED": "#8B949E" if dark else "#656D76",
        "BORDER": "#242B35" if dark else "#D0D7DE",
        "TRACK": "#171D25" if dark else "#EAECEF",
        "ACCENT": "#FF7A00",
    }


def build_dashboard(theme, user):
    colors = get_theme(theme)

    BG = colors["BG"]
    PANEL = colors["PANEL"]
    PANEL2 = colors["PANEL2"]
    FG = colors["FG"]
    MUTED = colors["MUTED"]
    BORDER = colors["BORDER"]
    TRACK = colors["TRACK"]
    ACCENT = colors["ACCENT"]

    repos = normalize_repos(user)
    latest = repos[0] if repos else None
    languages = aggregate_languages(repos, limit=5)
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

    svg = f"""
<svg xmlns="http://www.w3.org/2000/svg"
     width="1100" height="520" viewBox="0 0 1100 520">
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
  .body {{
    fill: {FG};
    font-size: 14px;
  }}
  .small {{
    fill: {MUTED};
    font-size: 12px;
  }}
</style>

<rect x="0.5" y="0.5" width="1099" height="519" rx="22"
      fill="{BG}" stroke="{BORDER}"/>

<rect x="24" y="24" width="1052" height="472" rx="18"
      fill="{PANEL}" stroke="{BORDER}"/>

<rect x="24" y="24" width="6" height="472" rx="3" fill="{ACCENT}"/>

<text x="52" y="58" class="eyebrow">DEVELOPER STATUS</text>
<circle cx="1015" cy="52" r="5" fill="{ACCENT}">
  <animate attributeName="opacity" values="1;.35;1" dur="2.2s" repeatCount="indefinite"/>
</circle>
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
        svg += '<text x="665" y="354" class="small">no recent public activity</text>'

    svg += f"""
<text x="52" y="488" class="small">structure / build / verify / improve</text>
<text x="1048" y="488" class="small" text-anchor="end">accent #{ACCENT[1:]}</text>
</svg>
"""

    return svg


def repo_candidates_for_commits(user):
    candidates = []
    seen = set()

    try:
        events = request_json(EVENTS_URL)
    except Exception:
        events = []

    for event in events:
        if event.get("type") != "PushEvent":
            continue

        repo = event.get("repo", {}).get("name", "")

        if not repo or repo == f"{USER}/{USER}" or repo in seen:
            continue

        seen.add(repo)
        candidates.append(repo)

        if len(candidates) >= 8:
            break

    for repo in normalize_repos(user):
        name = repo["nameWithOwner"]

        if name in seen:
            continue

        seen.add(name)
        candidates.append(name)

        if len(candidates) >= 12:
            break

    return candidates


def fetch_repo_commits(repo_name, per_page=4):
    encoded_user = urllib.parse.quote(USER)

    url = (
        f"https://api.github.com/repos/{repo_name}/commits"
        f"?author={encoded_user}&per_page={per_page}"
    )

    try:
        data = request_json(url)
    except Exception:
        return []

    if not isinstance(data, list):
        return []

    result = []

    for item in data:
        commit = item.get("commit", {})
        message = (commit.get("message") or "commit").splitlines()[0].strip()
        timestamp = (
            commit.get("author", {}).get("date")
            or commit.get("committer", {}).get("date")
        )

        result.append({
            "repo": repo_name,
            "message": message,
            "date": timestamp,
        })

    return result


def recent_commits(user, limit=5):
    rows = []
    seen = set()

    for repo_name in repo_candidates_for_commits(user):
        for commit in fetch_repo_commits(repo_name):
            key = (
                commit["repo"],
                commit["message"],
                commit["date"],
            )

            if key in seen:
                continue

            seen.add(key)
            rows.append(commit)

    def sort_key(item):
        value = item.get("date")
        if not value:
            return datetime.min.replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    rows.sort(key=sort_key, reverse=True)
    return rows[:limit]


def build_commits(theme, user):
    colors = get_theme(theme)

    BG = colors["BG"]
    PANEL = colors["PANEL"]
    FG = colors["FG"]
    MUTED = colors["MUTED"]
    BORDER = colors["BORDER"]
    ACCENT = colors["ACCENT"]

    rows = recent_commits(user, limit=5)

    svg = f"""
<svg xmlns="http://www.w3.org/2000/svg"
     width="1100" height="300" viewBox="0 0 1100 300">
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
  .body {{
    fill: {FG};
    font-size: 14px;
  }}
  .small {{
    fill: {MUTED};
    font-size: 12px;
  }}
</style>

<rect x="0.5" y="0.5" width="1099" height="299" rx="22"
      fill="{BG}" stroke="{BORDER}"/>

<rect x="24" y="24" width="1052" height="252" rx="18"
      fill="{PANEL}" stroke="{BORDER}"/>

<rect x="24" y="24" width="6" height="252" rx="3" fill="{ACCENT}"/>

<text x="52" y="58" class="eyebrow">RECENT COMMITS</text>
<text x="1048" y="58" class="small" text-anchor="end">REAL COMMIT MESSAGES</text>
"""

    if not rows:
        svg += '<text x="52" y="112" class="small">no recent public commits found</text>'
    else:
        y = 104

        for row in rows:
            repo = row["repo"].split("/")[-1]
            message = row["message"]

            if len(message) > 66:
                message = message[:63] + "..."

            when = time_ago(row["date"])

            svg += f"""
<circle cx="58" cy="{y-5}" r="4" fill="{ACCENT}">
  <animate attributeName="opacity" values="1;.35;1" dur="2.6s" repeatCount="indefinite"/>
</circle>

<text x="76" y="{y}" class="body">{svg_text(repo)}</text>
<text x="286" y="{y}" class="small">{svg_text(message)}</text>
<text x="1028" y="{y}" class="small" text-anchor="end">{svg_text(when)}</text>
"""

            if y < 240:
                svg += f'<line x1="76" y1="{y+18}" x2="1028" y2="{y+18}" stroke="{BORDER}"/>'

            y += 39

    svg += "</svg>"
    return svg


def build_codebase(theme, user):
    colors = get_theme(theme)

    BG = colors["BG"]
    PANEL = colors["PANEL"]
    PANEL2 = colors["PANEL2"]
    FG = colors["FG"]
    MUTED = colors["MUTED"]
    BORDER = colors["BORDER"]
    ACCENT = colors["ACCENT"]

    repos = normalize_repos(user)
    languages = aggregate_languages(repos, limit=6)

    svg = f"""
<svg xmlns="http://www.w3.org/2000/svg"
     width="1100" height="365" viewBox="0 0 1100 365">
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
    font-size: 20px;
    font-weight: 800;
  }}
  .metric {{
    fill: {FG};
    font-size: 26px;
    font-weight: 800;
  }}
  .body {{
    fill: {FG};
    font-size: 14px;
  }}
  .small {{
    fill: {MUTED};
    font-size: 12px;
  }}
</style>

<rect x="0.5" y="0.5" width="1099" height="364" rx="22"
      fill="{BG}" stroke="{BORDER}"/>

<rect x="24" y="24" width="1052" height="317" rx="18"
      fill="{PANEL}" stroke="{BORDER}"/>

<rect x="24" y="24" width="6" height="317" rx="3" fill="{ACCENT}"/>

<text x="52" y="58" class="eyebrow">CODEBASE MAP</text>
<text x="1048" y="58" class="small" text-anchor="end">PUBLIC REPOSITORY LANGUAGE DATA</text>

<text x="52" y="100" class="metric">{len(repos)} repos</text>
<text x="52" y="124" class="small">owned + contributed public repositories</text>
"""

    if not languages:
        svg += '<text x="52" y="170" class="small">no language data</text></svg>'
        return svg

    x0 = 52
    y0 = 154
    total_width = 996
    box_height = 112
    gap = 6

    pct_total = sum(pct for _, pct in languages) or 1
    raw_widths = [total_width * pct / pct_total for _, pct in languages]
    min_width = 82
    widths = [max(min_width, width) for width in raw_widths]
    usable = total_width - gap * (len(widths) - 1)
    scale = usable / sum(widths)
    widths = [width * scale for width in widths]

    x = x0

    for i, ((name, pct), width) in enumerate(zip(languages, widths)):
        opacity = max(0.34, 1 - i * 0.11)

        svg += f"""
<rect x="{x:.1f}" y="{y0}" width="{width:.1f}" height="{box_height}" rx="12"
      fill="{PANEL2}" stroke="{ACCENT}" stroke-opacity="{opacity:.2f}"/>

<text x="{x+14:.1f}" y="{y0+35}" class="body">{svg_text(name)}</text>
<text x="{x+14:.1f}" y="{y0+70}" class="title">{pct:.1f}%</text>
"""

        x += width + gap

    svg += f"""
<text x="52" y="310" class="eyebrow">CODE, NOT SELF-RATING</text>
<text x="52" y="336" class="small">calculated from GitHub language bytes across the visible codebase</text>

<circle cx="1028" cy="321" r="5" fill="{ACCENT}">
  <animate attributeName="r" values="4;7;4" dur="2.8s" repeatCount="indefinite"/>
  <animate attributeName="opacity" values="1;.35;1" dur="2.8s" repeatCount="indefinite"/>
</circle>

</svg>
"""

    return svg


def build_system_map(theme):
    colors = get_theme(theme)

    BG = colors["BG"]
    PANEL = colors["PANEL"]
    FG = colors["FG"]
    MUTED = colors["MUTED"]
    BORDER = colors["BORDER"]
    ACCENT = colors["ACCENT"]

    nodes = {
        "AI / LLM": (550, 110),
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
        ("AI / LLM", "VISION"),
        ("AI / LLM", "RAG"),
        ("AI / LLM", "AGENT"),
        ("AI / LLM", "AUTOMATION"),
        ("VISION", "BACKEND"),
        ("RAG", "BACKEND"),
        ("AGENT", "BACKEND"),
        ("AUTOMATION", "BACKEND"),
        ("BACKEND", "SPRING"),
        ("BACKEND", "REDIS"),
        ("BACKEND", "POSTGRES"),
        ("BACKEND", "AWS"),
    ]

    svg = f"""
<svg xmlns="http://www.w3.org/2000/svg"
     width="1100" height="430" viewBox="0 0 1100 430">
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
    font-size: 20px;
    font-weight: 800;
  }}
  .body {{
    fill: {FG};
    font-size: 14px;
  }}
  .small {{
    fill: {MUTED};
    font-size: 12px;
  }}
</style>

<rect x="0.5" y="0.5" width="1099" height="429" rx="22"
      fill="{BG}" stroke="{BORDER}"/>

<rect x="24" y="24" width="1052" height="382" rx="18"
      fill="{PANEL}" stroke="{BORDER}"/>

<rect x="24" y="24" width="6" height="382" rx="3" fill="{ACCENT}"/>

<text x="52" y="58" class="eyebrow">SYSTEM MAP</text>
<text x="1048" y="58" class="small" text-anchor="end">HOW THE PIECES CONNECT</text>
"""

    for source, target in edges:
        x1, y1 = nodes[source]
        x2, y2 = nodes[target]

        svg += f"""
<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"
      stroke="{BORDER}" stroke-width="2" stroke-dasharray="5 7">
  <animate attributeName="stroke-dashoffset" values="24;0" dur="3s" repeatCount="indefinite"/>
</line>
"""

    for i, (name, (x, y)) in enumerate(nodes.items()):
        main = name in ("AI / LLM", "BACKEND")
        radius = 9 if main else 6
        text_class = "title" if main else "body"
        duration = 2.2 + (i % 4) * 0.3

        svg += f"""
<circle cx="{x}" cy="{y}" r="{radius}" fill="{ACCENT}">
  <animate attributeName="opacity" values="1;.4;1" dur="{duration:.1f}s" repeatCount="indefinite"/>
</circle>

<text x="{x}" y="{y-18}" class="{text_class}" text-anchor="middle">{svg_text(name)}</text>
"""

    svg += "</svg>"
    return svg


def main():
    user = github_data()

    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)

    for theme in ("dark", "light"):
        (assets / f"dashboard-{theme}.svg").write_text(
            build_dashboard(theme, user),
            encoding="utf-8",
        )

        (assets / f"commits-{theme}.svg").write_text(
            build_commits(theme, user),
            encoding="utf-8",
        )

        (assets / f"codebase-{theme}.svg").write_text(
            build_codebase(theme, user),
            encoding="utf-8",
        )

        (assets / f"system-map-{theme}.svg").write_text(
            build_system_map(theme),
            encoding="utf-8",
        )

    expected = [
        "dashboard-dark.svg",
        "dashboard-light.svg",
        "commits-dark.svg",
        "commits-light.svg",
        "codebase-dark.svg",
        "codebase-light.svg",
        "system-map-dark.svg",
        "system-map-light.svg",
    ]

    missing = [
        name for name in expected
        if not (assets / name).exists()
    ]

    if missing:
        raise RuntimeError(
            "Missing generated SVG files: " + ", ".join(missing)
        )

    print("OK: all 8 SVG files generated")


if __name__ == "__main__":
    main()
