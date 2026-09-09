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


QUERY = """
query($login:String!) {
  user(login:$login) {
    name
    login

    followers {
      totalCount
    }

    repositories(
      first: 100,
      ownerAffiliations: OWNER,
      isFork: false,
      orderBy: {
        field: PUSHED_AT,
        direction: DESC
      }
    ) {
      totalCount

      nodes {
        name
        url
        pushedAt
        stargazerCount
        isPrivate

        languages(
          first: 10,
          orderBy: {
            field: SIZE,
            direction: DESC
          }
        ) {
          edges {
            size

            node {
              name
              color
            }
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


# ---------------------------------------------------------
# GitHub API
# ---------------------------------------------------------

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

    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode())


def github_data():
    result = request_json(
        GRAPHQL,
        {
            "query": QUERY,
            "variables": {
                "login": USER
            }
        }
    )

    if result.get("errors"):
        raise RuntimeError(result["errors"])

    return result["data"]["user"]


# ---------------------------------------------------------
# Language statistics
# ---------------------------------------------------------

def aggregate_languages(repos):
    totals = {}

    for repo in repos:
        if repo.get("isPrivate"):
            continue

        edges = repo.get("languages", {}).get("edges", [])

        for edge in edges:
            language = edge["node"]["name"]
            size = int(edge["size"])

            totals[language] = totals.get(language, 0) + size

    total_size = sum(totals.values()) or 1

    ranked = sorted(
        totals.items(),
        key=lambda item: item[1],
        reverse=True
    )[:5]

    return [
        (language, size / total_size * 100)
        for language, size in ranked
    ]


# ---------------------------------------------------------
# Time formatting
# ---------------------------------------------------------

def time_ago(timestamp):
    if not timestamp:
        return "—"

    dt = datetime.fromisoformat(
        timestamp.replace("Z", "+00:00")
    )

    delta = datetime.now(timezone.utc) - dt
    seconds = max(0, int(delta.total_seconds()))

    if seconds < 3600:
        minutes = max(1, seconds // 60)
        return f"{minutes}m ago"

    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours}h ago"

    if seconds < 86400 * 30:
        days = seconds // 86400
        return f"{days}d ago"

    return dt.strftime("%Y-%m-%d")


# ---------------------------------------------------------
# Dashboard SVG
# ---------------------------------------------------------

def svg(theme, user):
    dark = theme == "dark"

    bg = "#0d1117" if dark else "#ffffff"
    fg = "#f0f6fc" if dark else "#1f2328"
    muted = "#8b949e" if dark else "#656d76"
    border = "#30363d" if dark else "#d0d7de"
    track = "#21262d" if dark else "#eaeef2"

    accent = "#ff7a00"

    repos = user["repositories"]["nodes"]

    languages = aggregate_languages(repos)

    latest = repos[0] if repos else None

    stars = sum(
        int(repo["stargazerCount"])
        for repo in repos
    )

    contributions = (
        user["contributionsCollection"]
        ["contributionCalendar"]
        ["totalContributions"]
    )

    width = 980
    height = 330

    parts = [
        f"""
<svg
    xmlns="http://www.w3.org/2000/svg"
    width="{width}"
    height="{height}"
    viewBox="0 0 {width} {height}"
>

<style>

text {{
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        Helvetica,
        Arial,
        sans-serif;
}}

.label {{
    fill: {muted};
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 1.4px;
}}

.big {{
    fill: {fg};
    font-size: 32px;
    font-weight: 700;
}}

.value {{
    fill: {fg};
    font-size: 18px;
    font-weight: 650;
}}

.small {{
    fill: {muted};
    font-size: 13px;
}}

.lang {{
    fill: {fg};
    font-size: 14px;
    font-weight: 600;
}}

</style>


<rect
    x="0.5"
    y="0.5"
    width="{width - 1}"
    height="{height - 1}"
    rx="14"
    fill="{bg}"
    stroke="{border}"
/>


<!-- Header -->

<circle
    cx="34"
    cy="35"
    r="5"
    fill="{accent}"
/>

<text
    x="51"
    y="40"
    class="label"
>
    GITHUB / LIVE
</text>


<!-- Contributions -->

<text
    x="34"
    y="95"
    class="big"
>
    {escape(str(contributions))}
</text>

<text
    x="34"
    y="119"
    class="small"
>
    contributions · last year
</text>


<!-- Repositories -->

<text
    x="280"
    y="95"
    class="big"
>
    {escape(str(user["repositories"]["totalCount"]))}
</text>

<text
    x="280"
    y="119"
    class="small"
>
    repositories
</text>


<!-- Stars -->

<text
    x="470"
    y="95"
    class="big"
>
    {escape(str(stars))}
</text>

<text
    x="470"
    y="119"
    class="small"
>
    stars
</text>


<!-- Latest Push -->

<text
    x="650"
    y="75"
    class="label"
>
    LATEST PUSH
</text>

<text
    x="650"
    y="101"
    class="value"
>
    {escape(latest["name"] if latest else "—")}
</text>

<text
    x="650"
    y="124"
    class="small"
>
    {
        escape(
            time_ago(latest["pushedAt"])
            if latest
            else "—"
        )
    }
</text>


<line
    x1="34"
    y1="154"
    x2="946"
    y2="154"
    stroke="{border}"
/>


<!-- Languages -->

<text
    x="34"
    y="187"
    class="label"
>
    LANGUAGES
</text>
"""
    ]

    base_y = 216

    for index, (name, percentage) in enumerate(languages):
        y = base_y + index * 22

        bar_x = 160
        bar_width = 430

        fill_width = max(
            2,
            bar_width * percentage / 100
        )

        opacity = max(
            0.28,
            1 - index * 0.13
        )

        parts += [
            f"""
<text
    x="34"
    y="{y + 4}"
    class="lang"
>
    {escape(name)}
</text>
""",

            f"""
<rect
    x="{bar_x}"
    y="{y - 7}"
    width="{bar_width}"
    height="8"
    rx="4"
    fill="{track}"
/>
""",

            f"""
<rect
    x="{bar_x}"
    y="{y - 7}"
    width="{fill_width:.1f}"
    height="8"
    rx="4"
    fill="{accent}"
    opacity="{opacity:.2f}"
/>
""",

            f"""
<text
    x="610"
    y="{y + 4}"
    class="small"
>
    {percentage:.1f}%
</text>
"""
        ]

    # Profile block
    parts += [
        f"""
<text
    x="790"
    y="187"
    class="label"
>
    PROFILE
</text>

<text
    x="790"
    y="218"
    class="value"
>
    @{escape(USER)}
</text>

<text
    x="790"
    y="242"
    class="small"
>
    {escape(str(user["followers"]["totalCount"]))} followers
</text>

<text
    x="790"
    y="267"
    class="small"
>
    auto-updated
</text>

</svg>
"""
    ]

    return "".join(parts)


# ---------------------------------------------------------
# Recent GitHub Activity
# ---------------------------------------------------------

def recent_activity():
    events = request_json(EVENTS)

    rows = []
    seen = set()

    for event in events:
        event_type = event.get("type")

        repo = (
            event
            .get("repo", {})
            .get("name", "")
        )

        # ---------------------------------------------
        # Ignore profile repository activity
        # ---------------------------------------------

        if repo == f"{USER}/{USER}":
            continue

        created_at = event.get("created_at")

        key = (
            event_type,
            repo
        )

        if key in seen:
            continue

        seen.add(key)

        # ---------------------------------------------
        # Push
        # ---------------------------------------------

        if event_type == "PushEvent":
            commits = len(
                event
                .get("payload", {})
                .get("commits", [])
            )

            commit_text = (
                f"{commits} commit"
                if commits == 1
                else f"{commits} commits"
            )

            text = (
                f"pushed {commit_text} "
                f"to `{repo}`"
            )

            icon = "↳"

        # ---------------------------------------------
        # Pull Request
        # ---------------------------------------------

        elif event_type == "PullRequestEvent":
            action = (
                event
                .get("payload", {})
                .get("action", "updated")
            )

            text = (
                f"{action} a pull request "
                f"in `{repo}`"
            )

            icon = "↗"

        # ---------------------------------------------
        # Repository / Branch / Tag creation
        # ---------------------------------------------

        elif event_type == "CreateEvent":
            ref_type = (
                event
                .get("payload", {})
                .get("ref_type", "repository")
            )

            text = (
                f"created {ref_type} "
                f"in `{repo}`"
            )

            icon = "+"

        # ---------------------------------------------
        # Issue
        # ---------------------------------------------

        elif event_type == "IssuesEvent":
            action = (
                event
                .get("payload", {})
                .get("action", "updated")
            )

            text = (
                f"{action} an issue "
                f"in `{repo}`"
            )

            icon = "!"

        # ---------------------------------------------
        # Release
        # ---------------------------------------------

        elif event_type == "ReleaseEvent":
            action = (
                event
                .get("payload", {})
                .get("action", "published")
            )

            text = (
                f"{action} a release "
                f"in `{repo}`"
            )

            icon = "◆"

        else:
            continue

        rows.append(
            f"- `{icon}` {text} · "
            f"{time_ago(created_at)}"
        )

        if len(rows) >= 5:
            break

    if not rows:
        return "_No recent public activity._"

    # 실제 Markdown 줄바꿈
    return "\n".join(rows)


# ---------------------------------------------------------
# README Update
# ---------------------------------------------------------

def update_readme(activity):
    readme_path = ROOT / "README.md"

    content = readme_path.read_text(
        encoding="utf-8"
    )

    start_marker = "<!-- RECENT_ACTIVITY:START -->"
    end_marker = "<!-- RECENT_ACTIVITY:END -->"

    before, rest = content.split(
        start_marker,
        1
    )

    _, after = rest.split(
        end_marker,
        1
    )

    # 중요:
    # "\\n"이 아니라 "\n"이어야 실제 줄바꿈이 들어감.
    new_content = (
        before
        + start_marker
        + "\n"
        + activity
        + "\n"
        + end_marker
        + after
    )

    readme_path.write_text(
        new_content,
        encoding="utf-8"
    )


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():
    user = github_data()

    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)

    # Dark dashboard
    (
        assets
        / "dashboard-dark.svg"
    ).write_text(
        svg("dark", user),
        encoding="utf-8"
    )

    # Light dashboard
    (
        assets
        / "dashboard-light.svg"
    ).write_text(
        svg("light", user),
        encoding="utf-8"
    )

    # Recent GitHub activity
    update_readme(
        recent_activity()
    )


if __name__ == "__main__":
    main()
