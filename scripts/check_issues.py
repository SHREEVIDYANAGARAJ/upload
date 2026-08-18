#!/usr/bin/env python3

"""
Find very fresh, unassigned, zero-comment, documentation-related
good-first-issue/help-wanted issues across recognized infrastructure
and system-design repositories.

Runs from GitHub Actions using only Python's standard library.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta


# ============================================================
# REPOSITORIES
# ============================================================

REPOS = [
    # Docker / containers
    "moby/moby",
    "docker/compose",
    "docker/cli",
    "docker/buildx",
    "containerd/containerd",
    "containers/podman",
    "cri-o/cri-o",

    # Kubernetes / cloud native
    "kubernetes/kubernetes",
    "kubernetes/website",
    "kubernetes-sigs/kind",
    "kubernetes-sigs/kustomize",
    "kubernetes-sigs/external-dns",
    "kubernetes/minikube",
    "helm/helm",
    "argoproj/argo-cd",
    "argoproj/argo-workflows",
    "k3s-io/k3s",
    "rancher/rancher",
    "kedacore/keda",
    "crossplane/crossplane",
    "goharbor/harbor",
    "linkerd/linkerd2",
    "cilium/cilium",
    "istio/istio",
    "envoyproxy/envoy",

    # Observability / infrastructure
    "prometheus/prometheus",
    "grafana/grafana",
    "grafana/loki",
    "grafana/tempo",
    "grafana/mimir",
    "open-telemetry/opentelemetry-collector",
    "hashicorp/terraform",
    "hashicorp/vault",
    "hashicorp/consul",
    "etcd-io/etcd",
    "traefik/traefik",
    "caddyserver/caddy",
    "minio/minio",

    # Databases / search
    "vitessio/vitess",
    "pingcap/tidb",
    "ClickHouse/ClickHouse",
    "cockroachdb/cockroach",
    "elastic/elasticsearch",
    "redis/redis",
    "duckdb/duckdb",
    "apache/apisix",

    # Distributed systems / platforms
    "gitea/gitea",
    "temporalio/temporal",
    "keycloak/keycloak",
    "airbytehq/airbyte",
    "n8n-io/n8n",
    "supabase/supabase",
    "apache/kafka",
]


# ============================================================
# CONFIGURATION
# ============================================================

STATE_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "state",
    "seen_issues.json",
)

MAX_AGE_HOURS = float(
    os.environ.get("MAX_AGE_HOURS", "6")
)

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

BATCH_SIZE = 5

# Documentation-related words.
# We use these because repositories do not all use the same label.
DOC_KEYWORDS = [
    "documentation",
    "document",
    "docs",
    "readme",
    "guide",
    "tutorial",
    "example",
    "examples",
    "configuration",
    "config",
    "setup",
    "installation",
    "getting started",
    "troubleshooting",
    "explanation",
    "reference",
]

GOOD_FIRST_LABELS = [
    "good first issue",
    "good-first-issue",
]

HELP_WANTED_LABELS = [
    "help wanted",
    "help-wanted",
]


# ============================================================
# STATE
# ============================================================

def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()

    return set()


def save_state(seen):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)

    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, indent=2)


# ============================================================
# GITHUB API
# ============================================================

def github_request(url):
    request = urllib.request.Request(url)

    request.add_header(
        "Accept",
        "application/vnd.github+json"
    )

    request.add_header(
        "X-GitHub-Api-Version",
        "2022-11-28"
    )

    if GITHUB_TOKEN:
        request.add_header(
            "Authorization",
            f"Bearer {GITHUB_TOKEN}"
        )

    for attempt in range(3):
        try:
            with urllib.request.urlopen(
                request,
                timeout=30
            ) as response:

                return json.loads(
                    response.read().decode("utf-8")
                )

        except urllib.error.HTTPError as error:

            body = error.read().decode(
                "utf-8",
                errors="ignore"
            )

            print(
                f"GitHub HTTP {error.code}: {body}",
                file=sys.stderr
            )

            if error.code in (403, 429):
                time.sleep(15)
                continue

            return {}

        except Exception as error:

            print(
                f"GitHub request error: {error}",
                file=sys.stderr
            )

            time.sleep(5)

    return {}


# ============================================================
# SEARCH
# ============================================================

def search_batch(repos):
    """
    Search a small batch of repositories.

    We deliberately search broadly for:
      open
      issues
      unassigned
      good first issue OR help wanted

    Documentation is filtered locally because labels differ
    between repositories.
    """

    repo_query = " OR ".join(
        f"repo:{repo}"
        for repo in repos
    )

    query = (
        'is:open '
        'is:issue '
        'no:assignee '
        '(label:"good first issue" OR '
        'label:"good-first-issue" OR '
        'label:"help wanted" OR '
        'label:"help-wanted") '
        f'({repo_query})'
    )

    url = (
        "https://api.github.com/search/issues?"
        + urllib.parse.urlencode(
            {
                "q": query,
                "sort": "created",
                "order": "desc",
                "per_page": 100,
            }
        )
    )

    print(f"Searching: {repos}")

    return github_request(url)


# ============================================================
# FILTERS
# ============================================================

def parse_github_time(value):
    """
    Convert GitHub's ISO timestamp into a timezone-aware datetime.
    """

    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


def is_recent(item):
    """
    True only when the issue was created within MAX_AGE_HOURS.
    """

    created = parse_github_time(
        item["created_at"]
    )

    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(hours=MAX_AGE_HOURS)
    )

    return created >= cutoff


def has_zero_comments(item):
    return item.get("comments", 0) == 0


def has_no_assignee(item):
    return not item.get("assignees")


def has_good_label(item):
    labels = {
        label["name"].strip().lower()
        for label in item.get("labels", [])
    }

    return (
        bool(labels.intersection(GOOD_FIRST_LABELS))
        or bool(labels.intersection(HELP_WANTED_LABELS))
    )


def is_documentation_related(item):
    """
    Documentation labels are inconsistent across GitHub projects.

    Therefore we inspect:
      - labels
      - issue title
      - issue body
    """

    labels = " ".join(
        label["name"].lower()
        for label in item.get("labels", [])
    )

    title = item.get("title", "").lower()

    body = item.get("body") or ""
    body = body.lower()

    combined = f"{labels} {title} {body}"

    return any(
        keyword in combined
        for keyword in DOC_KEYWORDS
    )


# ============================================================
# MAIN
# ============================================================

def main():

    seen = load_state()

    new_items = []

    print(
        f"Checking {len(REPOS)} repositories..."
    )

    print(
        f"Looking for issues created within "
        f"the last {MAX_AGE_HOURS} hours."
    )

    print(
        "Requirements: open + unassigned + "
        "0 comments + GFI/help-wanted + documentation."
    )

    # --------------------------------------------------------
    # Search repositories in batches
    # --------------------------------------------------------

    for i in range(
        0,
        len(REPOS),
        BATCH_SIZE
    ):

        batch = REPOS[
            i:i + BATCH_SIZE
        ]

        data = search_batch(batch)

        for item in data.get("items", []):

            url = item["html_url"]

            # Already alerted about this issue
            if url in seen:
                continue

            # ------------------------------------------------
            # STRICT FILTERS
            # ------------------------------------------------

            if not is_recent(item):
                continue

            if not has_zero_comments(item):
                continue

            if not has_no_assignee(item):
                continue

            if not has_good_label(item):
                continue

            if not is_documentation_related(item):
                continue

            # ------------------------------------------------
            # MATCH
            # ------------------------------------------------

            new_items.append(item)

            # Mark as seen only after it passes all filters.
            seen.add(url)

        # Small delay between API requests.
        time.sleep(1)

    # --------------------------------------------------------
    # Save state
    # --------------------------------------------------------

    save_state(seen)

    # --------------------------------------------------------
    # GitHub Actions output
    # --------------------------------------------------------

    github_output = os.environ.get(
        "GITHUB_OUTPUT"
    )

    if new_items:

        lines = []

        for item in new_items:

            repo = (
                item["repository_url"]
                .split("/repos/")[-1]
            )

            labels = ", ".join(
                label["name"]
                for label in item.get("labels", [])
            )

            lines.append(
                f"### {repo}\n"
                f"**{item['title']}**\n\n"
                f"{item['html_url']}\n\n"
                f"- Comments: {item.get('comments', 0)}\n"
                f"- Assignee: None\n"
                f"- Created: {item['created_at']}\n"
                f"- Labels: {labels}"
            )

        body = (
            "# 🚨 Fresh Open-Source Issues Found\n\n"
            "These issues match your watcher criteria:\n\n"
            + "\n\n---\n\n".join(lines)
            + "\n"
        )

        with open(
            "email_body.txt",
            "w",
            encoding="utf-8"
        ) as f:

            f.write(body)

        print(body)

        if github_output:

            with open(
                github_output,
                "a",
                encoding="utf-8"
            ) as f:

                f.write("found=true\n")

    else:

        print(
            "No fresh matching issues found."
        )

        if github_output:

            with open(
                github_output,
                "a",
                encoding="utf-8"
            ) as f:

                f.write("found=false\n")


if __name__ == "__main__":
    main()