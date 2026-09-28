#!/usr/bin/env python3
"""Draw profile/stats.svg, streak.svg, and activity.svg from the GitHub API.

Colors are set on each shape. GitHub's image proxy drops <style> and
<foreignObject>, which turned the old charts into blank dark boxes.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

LOGIN = "hisshanzzz"
API = "https://api.github.com/graphql"
PROFILE = "profile"

BG = "#141321"
PINK = "#fe428e"
CYAN = "#a9fef7"
GOLD = "#f8d847"
MUTED = "#8b949e"
EMPTY = "#21262d"
GREENS = ("#0e4429", "#006d32", "#26a641", "#39d353")
FONT = "Segoe UI, Ubuntu, Sans-Serif"


def graphql(token: str, query: str, variables: dict | None = None) -> dict:
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "hisshanzzz-profile-graphs",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        payload = json.loads(res.read().decode())
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"]))
    return payload["data"]


def collect_stats(token: str) -> dict:
    year = datetime.now(timezone.utc).year
    commits = 0
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
        commits += data["user"]["contributionsCollection"]["totalCommitContributions"]

    stars = 0
    prs = issues = contribs = 0
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
        "commits": commits,
        "stars": stars,
        "prs": prs,
        "issues": issues,
        "contribs": contribs,
    }


def collect_days(token: str) -> dict[date, int]:
    year = datetime.now(timezone.utc).year
    days: dict[date, int] = {}
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            weeks {
              contributionDays { date contributionCount }
            }
          }
        }
      }
    }
    """
    for start in range(2024, year + 1):
        data = graphql(
            token,
            query,
            {
                "login": LOGIN,
                "from": f"{start}-01-01T00:00:00Z",
                "to": f"{start + 1}-01-01T00:00:00Z",
            },
        )
        weeks = data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
        for week in weeks:
            for item in week["contributionDays"]:
                days[date.fromisoformat(item["date"])] = item["contributionCount"]
    # The yearly query end date is in the future, so drop days that have not happened.
    today = datetime.now(ZoneInfo("Asia/Colombo")).date()
    days = {day: count for day, count in days.items() if day <= today}
    if not days:
        raise RuntimeError("contribution calendar was empty")
    return days


def sunday_on_or_before(day: date) -> date:
    return day - timedelta(days=(day.weekday() + 1) % 7)


def weeks_ending(days: dict[date, int], today: date, count: int = 53) -> list[list[tuple[date, int]]]:
    start = sunday_on_or_before(today) - timedelta(weeks=count - 1)
    columns = []
    for index in range(count):
        week_start = start + timedelta(weeks=index)
        columns.append(
            [
                (week_start + timedelta(days=offset), days.get(week_start + timedelta(days=offset), 0))
                for offset in range(7)
            ]
        )
    return columns


def green(count: int, positive: list[int]) -> str:
    if count <= 0 or not positive:
        return EMPTY
    if len(set(positive)) == 1:
        return GREENS[-1]
    ranks = [positive[len(positive) * bucket // 4] for bucket in (1, 2, 3)]
    if count <= ranks[0]:
        return GREENS[0]
    if count <= ranks[1]:
        return GREENS[1]
    if count <= ranks[2]:
        return GREENS[2]
    return GREENS[3]


def streaks(days: dict[date, int], today: date) -> dict:
    ordered = []
    cursor = min(days)
    last = max(days)
    while cursor <= last:
        ordered.append((cursor, days.get(cursor, 0)))
        cursor += timedelta(days=1)

    best_len = 0
    best_start = best_end = today
    run = 0
    run_start = today
    for day, count in ordered:
        if count > 0:
            if run == 0:
                run_start = day
            run += 1
            if run > best_len:
                best_len = run
                best_start, best_end = run_start, day
        else:
            run = 0

    anchor = today if days.get(today, 0) > 0 else today - timedelta(days=1)
    current_len = 0
    current_start = current_end = anchor
    if days.get(anchor, 0) > 0:
        cursor = anchor
        current_end = anchor
        while days.get(cursor, 0) > 0:
            current_len += 1
            current_start = cursor
            cursor -= timedelta(days=1)

    active_days = [day for day, count in ordered if count > 0]
    return {
        "total": sum(days.values()),
        "first": active_days[0] if active_days else today,
        "current": current_len,
        "current_start": current_start,
        "current_end": current_end,
        "longest": best_len,
        "longest_start": best_start,
        "longest_end": best_end,
    }


def pretty(day: date) -> str:
    return f"{day.strftime('%b')} {day.day}"


def pretty_range(start: date, end: date) -> str:
    if start == end:
        return pretty(start)
    if start.year == end.year and start.month == end.month:
        return f"{start.strftime('%b')} {start.day} - {end.day}"
    if start.year == end.year:
        return f"{pretty(start)} - {pretty(end)}"
    return f"{pretty(start)}, {start.year} - {pretty(end)}, {end.year}"


def text(x, y, value, fill, size, weight="600", anchor="start") -> str:
    return (
        f'<text x="{x}" y="{y}" fill="{fill}" font-family="{FONT}" '
        f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{value}</text>'
    )


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


def render_stats(stats: dict) -> str:
    rows = []
    for index, (key, label, icon) in enumerate(ROWS):
        y = index * 25
        rows.append(
            f'<g transform="translate(25, {y})">'
            f'<svg viewBox="0 0 16 16" width="16" height="16">'
            f'<path fill="{GOLD}" fill-rule="evenodd" d="{icon}"/>'
            f"</svg>"
            f"{text(25, 12.5, label, CYAN, 14, '700')}"
            f"{text(170, 12.5, stats[key], CYAN, 14, '600')}"
            f"</g>"
        )
    body = "".join(rows)
    return f'''<svg width="495" height="195" viewBox="0 0 495 195" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="GitHub stats">
  <rect width="495" height="195" rx="8" fill="{BG}"/>
  {text(25, 32, "Hisshan M's GitHub Stats", PINK, 18, "700")}
  <g transform="translate(0, 55)">{body}</g>
</svg>
'''


def render_streak(info: dict) -> str:
    current_range = (
        pretty_range(info["current_start"], info["current_end"])
        if info["current"]
        else "None yet today"
    )
    longest_range = (
        pretty_range(info["longest_start"], info["longest_end"])
        if info["longest"]
        else "-"
    )
    total_range = f"{pretty(info['first'])}, {info['first'].year} - Present"
    flame = (
        "M 1.5 0.67 C 1.5 0.67 2.24 3.32 2.24 5.47 C 2.24 7.53 0.89 9.2 -1.17 9.2 "
        "C -3.23 9.2 -4.79 7.53 -4.79 5.47 L -4.76 5.11 C -6.78 7.51 -8 10.62 -8 13.99 "
        "C -8 18.41 -4.42 22 0 22 C 4.42 22 8 18.41 8 13.99 C 8 8.6 5.41 3.79 1.5 0.67 Z "
        "M -0.29 19 C -2.07 19 -3.51 17.6 -3.51 15.86 C -3.51 14.24 -2.46 13.1 -0.7 12.74 "
        "C 1.07 12.38 2.9 11.53 3.92 10.16 C 4.31 11.45 4.51 12.81 4.51 14.2 "
        "C 4.51 16.85 2.36 19 -0.29 19 Z"
    )
    return f'''<svg width="495" height="195" viewBox="0 0 495 195" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="GitHub streak">
  <rect width="495" height="195" rx="8" fill="{BG}"/>
  <line x1="165" y1="36" x2="165" y2="158" stroke="#30363d" stroke-width="1"/>
  <line x1="330" y1="36" x2="330" y2="158" stroke="#30363d" stroke-width="1"/>
  {text(82.5, 78, info["total"], PINK, 28, "700", "middle")}
  {text(82.5, 112, "Total Contributions", PINK, 13, "400", "middle")}
  {text(82.5, 136, total_range, CYAN, 12, "400", "middle")}
  <circle cx="247.5" cy="70" r="32" fill="none" stroke="{PINK}" stroke-width="5"/>
  <path d="{flame}" fill="{PINK}" transform="translate(247.5, 4) scale(0.7)"/>
  {text(247.5, 80, info["current"], GOLD, 28, "700", "middle")}
  {text(247.5, 124, "Current Streak", GOLD, 13, "700", "middle")}
  {text(247.5, 148, current_range, CYAN, 12, "400", "middle")}
  {text(412.5, 78, info["longest"], PINK, 28, "700", "middle")}
  {text(412.5, 112, "Longest Streak", PINK, 13, "400", "middle")}
  {text(412.5, 136, longest_range, CYAN, 12, "400", "middle")}
</svg>
'''


def render_activity(days: dict[date, int], today: date) -> str:
    columns = weeks_ending(days, today)
    shown = [count for week in columns for _, count in week if _ <= today]
    positive = sorted(count for count in shown if count > 0)
    cell = 12
    gap = 3
    step = cell + gap
    left = 36
    top = 52
    width = left + len(columns) * step + 16
    height = top + 7 * step + 28
    parts = [
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Contribution graph">',
        f'<rect width="{width}" height="{height}" rx="8" fill="{BG}"/>',
        text(16, 28, "Contribution graph", PINK, 16, "700"),
        text(width - 16, 28, f"{sum(shown)} contributions in the last year", CYAN, 13, "400", "end"),
    ]
    for row, label in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        parts.append(text(8, top + row * step + 10, label, MUTED, 11, "400"))
    last_month = None
    last_label_x = -100
    for index, week in enumerate(columns):
        x = left + index * step
        month_day = week[0][0]
        if month_day.month != last_month and x - last_label_x >= step * 3:
            parts.append(text(x, top - 8, month_day.strftime("%b"), MUTED, 11, "400"))
            last_month = month_day.month
            last_label_x = x
        for offset, (day, count) in enumerate(week):
            if day > today:
                continue
            y = top + offset * step
            fill = green(count, positive)
            word = "contribution" if count == 1 else "contributions"
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{fill}">'
                f"<title>{day.isoformat()}: {count} {word}</title></rect>"
            )
    legend_y = top + 7 * step + 4
    parts.append(text(width - 148, legend_y + 11, "Less", MUTED, 11, "400"))
    for index, fill in enumerate((EMPTY, *GREENS)):
        parts.append(
            f'<rect x="{width - 112 + index * 16}" y="{legend_y}" width="12" height="12" rx="2" fill="{fill}"/>'
        )
    parts.append(text(width - 28, legend_y + 11, "More", MUTED, 11, "400"))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def write_svg(name: str, svg: str) -> None:
    if "<style" in svg or "<foreignObject" in svg or "Something went wrong" in svg:
        raise RuntimeError(f"{name} still depends on stripped SVG features")
    if svg.count('fill="') < 3:
        raise RuntimeError(f"{name} is missing inline colors")
    path = os.path.join(PROFILE, name)
    os.makedirs(PROFILE, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(svg)


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("no token; keeping last-known-good graphs", file=sys.stderr)
        return 0
    try:
        stats = collect_stats(token)
        days = collect_days(token)
        today = datetime.now(ZoneInfo("Asia/Colombo")).date()
        info = streaks(days, today)
        write_svg("stats.svg", render_stats(stats))
        write_svg("streak.svg", render_streak(info))
        write_svg("activity.svg", render_activity(days, today))
    except (urllib.error.URLError, RuntimeError, KeyError, TimeoutError, OSError) as exc:
        print(f"graph render failed ({exc}); keeping last-known-good SVGs", file=sys.stderr)
        return 0
    print(
        "graphs refreshed: "
        f"stars={stats['stars']} commits={stats['commits']} "
        f"contributions={info['total']} current_streak={info['current']} "
        f"longest_streak={info['longest']} today={today.isoformat()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
