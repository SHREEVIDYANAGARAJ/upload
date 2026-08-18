#!/usr/bin/env python3
"""
Polls GitHub's search API across a curated list of well-known,
actively-used repositories for open, unassigned "good first issue"
tickets with low comment counts, and reports any that haven't been
seen before (tracked in state/seen_issues.json).

Designed to run on a schedule via GitHub Actions. Uses only the
standard library so no pip install step is needed.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

# ---------------------------------------------------------------------------
# Curated list of recognized / resume-worthy repos across
# Docker, Kubernetes, containerization, SQL/databases, and system design.
# Edit this list freely to add or remove projects you care about.
# ---------------------------------------------------------------------------
REPOS = [
    # Docker / containerization
    "moby/moby", "docker/compose", "docker/cli", "docker/buildx",
    "containerd/containerd", "containers/podman", "cri-o/cri-o",
    # Kubernetes ecosystem
    "kubernetes/kubernetes", "kubernetes-sigs/kind", "kubernetes-sigs/kustomize",
    "kubernetes-sigs/external-dns", "kubernetes/minikube", "helm/helm",
    "argoproj/argo-cd", "argoproj/argo-workflows", "k3s-io/k3s",
    "rancher/rancher", "kedacore/keda", "crossplane/crossplane",
    "goharbor/harbor", "linkerd/linkerd2", "cilium/cilium", "istio/istio",
    "envoyproxy/envoy",
    # Observability / infra
    "prometheus/prometheus", "grafana/grafana", "grafana/loki", "grafana/tempo",
    "hashicorp/terraform", "hashicorp/vault", "hashicorp/consul",
    "etcd-io/etcd", "traefik/traefik", "caddyserver/caddy", "minio/minio",
    # Databases / SQL
    "vitessio/vitess", "pingcap/tidb", "ClickHouse/ClickHouse",
    "cockroachdb/cockroach", "elastic/elasticsearch", "redis/redis",
    "duckdb/duckdb", "apache/apisix",
    # Popular dev platforms
    "gitea/gitea", "temporalio/temporal", "keycloak/keycloak",
    "airbytehq/airbyte", "n8n-io/n8n", "supabase/supabase",
]

STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "state", "seen_issues.json")
MAX_COMMENTS = int(os.environ.get("MAX_COMMENTS", "3"))  # only alert if comments <= this
BATCH_SIZE = 5  # GitHub search API rejects queries with >5 OR/AND/NOT operators
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r") as f:
            return set(json.load(f))
    return set()


def save_state(seen):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(sorted(seen), f, indent=2)


def search_batch(repos):
    parts = " OR ".join(f"repo:{r}" for r in repos)
    query = f'is:open is:issue no:assignee label:"good first issue" ({parts})'
    url = "https://api.github.com/search/issues?" + urllib.parse.urlencode(
        {"q": query, "sort": "created", "order": "desc", "per_page": 50}
    )
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    if GITHUB_TOKEN:
        req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            print(f"HTTP {e.code} for batch {repos}: {body}", file=sys.stderr)
            if e.code == 403:
                time.sleep(15)
                continue
            return {"items": []}
        except Exception as e:
            print(f"Error querying batch {repos}: {e}", file=sys.stderr)
            time.sleep(5)
    return {"items": []}


def main():
    seen = load_state()
    new_items = []

    for i in range(0, len(REPOS), BATCH_SIZE):
        batch = REPOS[i : i + BATCH_SIZE]
        data = search_batch(batch)
        for item in data.get("items", []):
            key = item["html_url"]
            if key in seen:
                continue
            seen.add(key)
            if item.get("comments", 0) <= MAX_COMMENTS:
                new_items.append(item)
        time.sleep(2)  # be polite to the search API rate limit

    save_state(seen)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if new_items:
        lines = []
        for item in new_items:
            repo = item["repository_url"].split("/repos/")[-1]
            lines.append(
                f"- {repo}: {item['title']}\n"
                f"  {item['html_url']}\n"
                f"  comments: {item['comments']} | created: {item['created_at']}"
            )
        body = "New good-first-issue(s) found:\n\n" + "\n\n".join(lines) + "\n"
        with open("email_body.txt", "w") as f:
            f.write(body)
        print(body)
        if github_output:
            with open(github_output, "a") as f:
                f.write("found=true\n")
    else:
        print("No new matching issues this run.")
        if github_output:
            with open(github_output, "a") as f:
                f.write("found=false\n")


if __name__ == "__main__":
    main()
