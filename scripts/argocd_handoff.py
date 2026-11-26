import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

import yaml


APPS = ("app", "coach", "network")
NAMESPACE = "powerlifting"
TRACKING = "argocd.argoproj.io/tracking-id"
ECR = re.compile(r"([0-9]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com/if-[a-z0-9-]+)(?::[^@]+)?(?:@(sha256:[0-9a-f]{64}))?")


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def kube(*args, obj=None):
    cmd = ["kubectl", *args, "-o", "json"]
    if obj is not None:
        cmd.extend(["-f", "-"])
    result = subprocess.run(cmd, input=json.dumps(obj), text=True, capture_output=True)
    if result.returncode:
        name = obj["metadata"]["name"] if obj else args[-1]
        raise SystemExit(f"Kubernetes {args[0]} failed for {name}")
    if not result.stdout.strip():
        return None
    data = json.loads(result.stdout)
    if obj is not None and args[0] == "get" and data.get("kind") == "List":
        require(len(data["items"]) <= 1, "Expected at most one Kubernetes object")
        return data["items"][0] if data["items"] else None
    return data


def documents(path):
    return [obj for obj in yaml.safe_load_all(path.read_text()) if obj]


def identity(obj):
    group, _, _ = obj["apiVersion"].rpartition("/")
    meta = obj["metadata"]
    return f'{group}/{obj["kind"]}:{meta["namespace"]}/{meta["name"]}'


def containers(deployment):
    return deployment["spec"]["template"]["spec"]["containers"]


def seed(app, docs):
    application = kube("-n", "argocd", "get", "application", f"nolift-{app}")
    require("automated" not in application["spec"]["syncPolicy"], "Handoff requires manual sync")
    if application["spec"]["source"]["kustomize"].get("images"):
        return
    overrides = {}
    for obj in docs:
        if obj["kind"] != "Deployment":
            continue
        live = kube("get", obj=obj)
        by_name = {c["name"]: c["image"] for c in containers(live)}
        for container in containers(obj):
            target = ECR.fullmatch(container["image"])
            if target:
                name = container["name"]
                current = ECR.fullmatch(by_name.get(name, ""))
                require(current and current[1] == target[1] and current[2], f"Missing live ECR digest for {app}/{name}")
                require(overrides.setdefault(current[1], current[2]) == current[2], f"Conflicting live digests for {app}/{name}")
    if overrides:
        images = [f"{repo}@{digest}" for repo, digest in sorted(overrides.items())]
        patch = {"metadata": {"resourceVersion": application["metadata"]["resourceVersion"]}, "spec": {"source": {"kustomize": {"images": images}}}}
        subprocess.run(["kubectl", "-n", "argocd", "patch", "application", f"nolift-{app}", "--type=merge",
                        "--field-manager=nolift-handoff", "-p", json.dumps(patch)], check=True, stdout=subprocess.DEVNULL)


def check_render(docs):
    require(docs, "Argo returned an empty render")
    for obj in docs:
        name = obj["metadata"]["name"]
        require("nolift:private:" not in json.dumps(obj), f"Unresolved private marker in {name}")
        require(obj["metadata"].get("namespace") == NAMESPACE and obj["kind"] not in ("Secret", "PersistentVolumeClaim"), f"Unexpected resource {name}")
        if obj["kind"] == "Deployment":
            for container in containers(obj):
                image = container["image"]
                require(not re.fullmatch(r"if-[a-z0-9-]+", image), f"Bare ECR name in {name}")
                if ".dkr.ecr." in image:
                    match = ECR.fullmatch(image)
                    require(match and match[2], f"Unpinned ECR image in {name}")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def snapshot(docs, dry_run):
    deployments = {}
    for obj in docs:
        if not dry_run and obj["kind"] != "Deployment":
            continue
        name = obj["metadata"]["name"]
        live = kube("get", "--ignore-not-found", obj=obj)
        if live is None:
            require(obj["kind"] == "HTTPRoute" and name == "argocd", f"Missing adoption target: {name}")
        if dry_run:
            applied = kube("apply", "--server-side", "--dry-run=server", "--field-manager=argocd-controller", "--force-conflicts", obj=obj)
            if live is None:
                continue
            desired_fields = {k: v for k, v in applied.items() if k not in ("metadata", "status")}
            live_fields = {k: v for k, v in live.items() if k not in ("metadata", "status")}
            require(desired_fields == live_fields, f"Handoff would change {obj['kind']} spec: {name}")
        if obj["kind"] != "Deployment":
            continue
        deployments[live["metadata"]["uid"]] = digest(live["spec"])
    replicasets = {r["metadata"]["uid"] for r in kube("-n", NAMESPACE, "get", "replicasets")["items"]
                   if any(owner["uid"] in deployments for owner in r["metadata"].get("ownerReferences", []))}
    pods = {p["metadata"]["uid"]: {c["name"]: c["restartCount"] for c in p.get("status", {}).get("containerStatuses", [])}
            for p in kube("-n", NAMESPACE, "get", "pods")["items"]
            if any(owner["uid"] in replicasets for owner in p["metadata"].get("ownerReferences", []))}
    return {"deployments": deployments, "replicasets": sorted(replicasets), "pods": pods}


TF_KINDS = {"kubernetes_deployment_v1": ("apps/v1", "Deployment"), "kubernetes_service_v1": ("v1", "Service"),
            "kubernetes_service_account_v1": ("v1", "ServiceAccount")}


def transfers(changes, app, rendered):
    records = []
    for change in changes:
        actions = change["change"]["actions"]
        if change["mode"] != "managed" or "delete" not in actions:
            continue
        addr = change["address"]
        require(actions == ["delete"], f"Refusing replacement of {addr}")
        before = change["change"]["before"]
        kind = change["type"]
        if kind == "kubectl_manifest":
            obj = yaml.safe_load(before["yaml_body"])
            uid = before.get("uid")
        else:
            require(kind in TF_KINDS, f"Unexpected Terraform deletion: {addr}")
            api, resource = TF_KINDS[kind]
            obj = {"apiVersion": api, "kind": resource, "metadata": before["metadata"][0]}
            uid = obj["metadata"].get("uid")
        key = identity(obj)
        require(key in rendered, f"Deletion outside nolift-{app}: {addr}")
        live = kube("get", obj=rendered[key])["metadata"]
        require(uid and uid == live["uid"], f"Object identity changed: {addr}")
        require(live.get("annotations", {}).get(TRACKING) == f"nolift-{app}:{key}", f"Missing matching Argo ownership: {addr}")
        meta = obj["metadata"]
        import_id = f'{meta["namespace"]}/{meta["name"]}'
        if kind == "kubectl_manifest":
            import_id = "//".join([obj["apiVersion"], obj["kind"], meta["name"], meta["namespace"]])
        records.append({"address": addr, "id": import_id, "uid": uid, "apiVersion": obj["apiVersion"],
                        "kind": obj["kind"], "metadata": {"name": meta["name"], "namespace": meta["namespace"]}})
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["seed", "render", "before", "after", "release"])
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    for app in APPS:
        docs = documents(args.directory / f"{app}.yaml")
        if args.action == "seed":
            seed(app, docs)
            continue
        check_render(docs)
        if args.action in ("before", "after"):
            path = args.directory / f"{app}-snapshot.json"
            state = snapshot(docs, args.action == "before")
            if args.action == "before":
                path.write_text(json.dumps(state))
            else:
                require(state == json.loads(path.read_text()), f"Workloads changed during adoption: {app}")
        elif args.action == "release":
            changes = json.loads((args.directory / f"{app}.json").read_text())["resource_changes"]
            records = transfers(changes, app, {identity(d): d for d in docs})
            (args.directory / f"{app}.imports").write_text(json.dumps(records))
            addrs = [record["address"] for record in records]
            (args.directory / f"{app}.addresses").write_text("".join(addr + "\n" for addr in addrs))


if __name__ == "__main__":
    main()
