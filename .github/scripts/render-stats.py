#!/usr/bin/env python3
"""Build profile/stats.svg from the GitHub API.

The old card was downloaded from a third-party Vercel app. When that app
fails it still returns an SVG, and the workflow was saving that error image
("Something went wrong! file an issue") over the real stats.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

LOGIN = "hisshanzzz"
OUT = os.path.join("profile", "stats.svg")
API = "https://api.github.com/graphql"


def graphql(token: str, query: str, variables: dict | None = None) -> dict:
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "hisshanzzz-profile-stats",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        payload = json.loads(res.read().decode())
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"]))
    return payload["data"]


def collect(token: str) -> dict:
    year = datetime.now(timezone.utc).year
    # contributionsCollection rejects ranges longer than one year.
    parts = []
    for start in range(2024, year + 1):
        data = graphql(
            token,
            """
            query($login: String!, $from: DateTime!, $to: DateTime!) {
              user(login: $login) {
                contributionsCollection(from: $from, to: $to) {
                  totalCommitContributions
                }
              }
            }
            """,
            {
                "login": LOGIN,
                "from": f"{start}-01-01T00:00:00Z",
                "to": f"{start + 1}-01-01T00:00:00Z",
            },
        )
        parts.append(data["user"]["contributionsCollection"]["totalCommitContributions"])

    stars = 0
    cursor = None
    while True:
        data = graphql(
            token,
            """
            query($login: String!, $after: String) {
              user(login: $login) {
                repositories(
                  first: 100
                  after: $after
                  ownerAffiliations: OWNER
                  privacy: PUBLIC
                ) {
                  pageInfo { hasNextPage endCursor }
                  nodes { stargazerCount }
                }
                pullRequests(states: [OPEN, CLOSED, MERGED]) { totalCount }
                issues(states: [OPEN, CLOSED]) { totalCount }
                repositoriesContributedTo(
                  first: 1
                  contributionTypes: [COMMIT, ISSUE, PULL_REQUEST, REPOSITORY]
                ) { totalCount }
              }
            }
            """,
            {"login": LOGIN, "after": cursor},
        )
        user = data["user"]
        stars += sum(node["stargazerCount"] for node in user["repositories"]["nodes"])
        prs = user["pullRequests"]["totalCount"]
        issues = user["issues"]["totalCount"]
        contribs = user["repositoriesContributedTo"]["totalCount"]
        page = user["repositories"]["pageInfo"]
        if not page["hasNextPage"]:
            break
        cursor = page["endCursor"]

    return {
        "commits": sum(parts),
        "stars": stars,
        "prs": prs,
        "issues": issues,
        "contribs": contribs,
    }


STAR = "M8 .25a.75.75 0 01.673.418l1.882 3.815 4.21.612a.75.75 0 01.416 1.279l-3.046 2.97.719 4.192a.75.75 0 01-1.088.791L8 12.347l-3.766 1.98a.75.75 0 01-1.088-.79l.72-4.194L.818 6.374a.75.75 0 01.416-1.28l4.21-.611L7.327.668A.75.75 0 018 .25zm0 2.445L6.615 5.5a.75.75 0 01-.564.41l-3.097.45 2.24 2.184a.75.75 0 01.216.664l-.528 3.084 2.769-1.456a.75.75 0 01.698 0l2.77 1.456-.53-3.084a.75.75 0 01.216-.664l2.24-2.183-3.096-.45a.75.75 0 01-.564-.41L8 2.694v.001z"
COMMITS = "M1.643 3.143L.427 1.927A.25.25 0 000 2.104V5.75c0 .138.112.25.25.25h3.646a.25.25 0 00.177-.427L2.715 4.215a6.5 6.5 0 11-1.18 4.458.75.75 0 10-1.493.154 8.001 8.001 0 101.6-5.684zM7.75 4a.75.75 0 01.75.75v2.992l2.028.812a.75.75 0 01-.557 1.392l-2.5-1A.75.75 0 017 8.25v-3.5A.75.75 0 017.75 4z"
PRS = "M7.177 3.073L9.573.677A.25.25 0 0110 .854v4.792a.25.25 0 01-.427.177L7.177 3.427a.25.25 0 010-.354zM3.75 2.5a.75.75 0 100 1.5.75.75 0 000-1.5zm-2.25.75a2.25 2.25 0 113 2.122v5.256a2.251 2.251 0 11-1.5 0V5.372A2.25 2.25 0 011.5 3.25zM11 2.5h-1V4h1a1 1 0 011 1v5.628a2.251 2.251 0 101.5 0V5A2.5 2.5 0 0011 2.5zm1 10.25a.75.75 0 111.5 0 .75.75 0 01-1.5 0zM3.75 12a.75.75 0 100 1.5.75.75 0 000-1.5z"
ISSUES = "M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM0 8a8 8 0 1116 0A8 8 0 010 8zm9 3a1 1 0 11-2 0 1 1 0 012 0zm-.25-6.25a.75.75 0 00-1.5 0v3.5a.75.75 0 001.5 0v-3.5z"
CONTRIBS = "M2 2.5A2.5 2.5 0 014.5 0h8.75a.75.75 0 01.75.75v12.5a.75.75 0 01-.75.75h-2.5a.75.75 0 110-1.5h1.75v-2h-8a1 1 0 00-.714 1.7.75.75 0 01-1.072 1.05A2.495 2.495 0 012 11.5v-9zm10.5-1V9h-8c-.356 0-.694.074-1 .208V2.5a1 1 0 011-1h8zM5 12.25v3.25a.25.25 0 00.4.2l1.45-1.087a.25.25 0 01.3 0L8.6 15.7a.25.25 0 00.4-.2v-3.25a.25.25 0 00-.25-.25h-3.5a.25.25 0 00-.25.25z"

ROWS = [
    ("stars", "Total Stars:", STAR),
    ("commits", "Total Commits:", COMMITS),
    ("prs", "Total PRs:", PRS),
    ("issues", "Total Issues:", ISSUES),
    ("contribs", "Contributed to:", CONTRIBS),
]


def render(stats: dict) -> str:
    rows = []
    for index, (key, label, icon) in enumerate(ROWS):
        rows.append(
            f"""<g transform="translate(0, {index * 25})">
      <g transform="translate(25, 0)">
        <svg class="icon" viewBox="0 0 16 16" width="16" height="16">
          <path fill-rule="evenodd" d="{icon}"/>
        </svg>
        <text class="stat bold" x="25" y="12.5">{label}</text>
        <text class="stat" x="170" y="12.5" data-testid="{key}">{stats[key]}</text>
      </g>
    </g>"""
        )
    body = "\n".join(rows)
    return f"""<svg width="495" height="195" viewBox="0 0 495 195" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Hisshan M GitHub stats">
  <title>Hisshan M's GitHub Stats</title>
  <style>
    .header {{ font: 600 18px 'Segoe UI', Ubuntu, Sans-Serif; fill: #fe428e; }}
    .stat {{ font: 600 14px 'Segoe UI', Ubuntu, Sans-Serif; fill: #a9fef7; }}
    .bold {{ font-weight: 700; }}
    .icon {{ fill: #f8d847; }}
  </style>
  <rect x="0.5" y="0.5" width="494" height="194" rx="4.5" fill="#141321"/>
  <text x="25" y="32" class="header">Hisshan M's GitHub Stats</text>
  <g transform="translate(0, 55)">
    {body}
  </g>
</svg>
"""


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("no token; keeping last-known-good stats.svg", file=sys.stderr)
        return 0
    try:
        stats = collect(token)
        svg = render(stats)
    except (urllib.error.URLError, RuntimeError, KeyError, TimeoutError) as exc:
        print(f"stats fetch failed ({exc}); keeping last-known-good stats.svg", file=sys.stderr)
        return 0
    if "Something went wrong" in svg or "<svg" not in svg:
        print("refusing to write an error card", file=sys.stderr)
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(svg)
    print(
        "stats.svg refreshed: "
        + ", ".join(f"{key}={stats[key]}" for key, _, _ in ROWS)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
