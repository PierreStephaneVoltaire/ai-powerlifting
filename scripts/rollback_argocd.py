import json
import os
import re
import subprocess
import sys
from pathlib import Path

from argocd_handoff import APPS, NAMESPACE, TRACKING, identity, kube, require


def rollback(revision, work):
    require(re.fullmatch("[0-9a-f]{40}", revision), "Select the full commit SHA containing the Terraform workloads")
    subprocess.run(["git", "merge-base", "--is-ancestor", revision, "HEAD"], check=True)
    journal = kube("-n", "argocd", "get", "configmap", "nolift-terraform-handoff", "--ignore-not-found")
    annotations = journal["metadata"].get("annotations", {}) if journal else {}
    require(annotations.get("nolift.io/promoted") != "true", "Rollback is limited to the manual adoption phase")
    records = {app: json.loads(journal["data"][app]) if journal else [] for app in APPS}
    archive = work / "legacy.tar"
    subprocess.run(["git", "archive", "-o", archive, revision, "terraform/k8s", "terraform/coach", "src/services/operations"], check=True)
    subprocess.run(["tar", "-xf", archive, "-C", work], check=True)
    require((work / "terraform/k8s/app/sessions.tf").exists() and (work / "terraform/coach/discord.tf").exists()
            and (work / "terraform/k8s/network/routes.tf").exists(), "The selected revision must contain the original workload stacks")
    existing = {}
    for app in APPS:
        resource = f"application/nolift-{app}"
        raw = subprocess.check_output(["kubectl", "-n", "argocd", "get", resource, "--ignore-not-found", "-o", "json"])
        if raw:
            current = json.loads(raw)
            require(not current["metadata"].get("finalizers") and not current["spec"]["syncPolicy"].get("automated")
                    and not current.get("operation"), f"Application {app} must be manual, idle and have no finalizers")
        existing[app] = bool(raw)
        for record in records[app]:
            require(record["metadata"]["namespace"] == NAMESPACE, "Unexpected journal namespace")
            live = kube("get", obj={k: record[k] for k in ("kind", "apiVersion", "metadata")})["metadata"]
            require(live["uid"] == record["uid"] and live.get("annotations", {}).get(TRACKING) == f"nolift-{app}:{identity(record)}",
                    f"Object identity changed for {record['address']}")
    if not journal:
        subprocess.run(["kubectl", "-n", "argocd", "create", "configmap", "nolift-terraform-handoff",
                        *[f"--from-literal={app}=[]" for app in APPS]], check=True)
    subprocess.run(["kubectl", "-n", "argocd", "annotate", "configmap/nolift-terraform-handoff",
                    "nolift.io/rolled-back=true", "--overwrite"], check=True)
    for app in APPS:
        if existing[app]:
            subprocess.run(["kubectl", "-n", "argocd", "delete", f"application/nolift-{app}", "--cascade=orphan"], check=True)
    for app in APPS:
        stack = "terraform/coach" if app == "coach" else f"terraform/k8s/{app}"
        legacy = work / stack
        tf = ["terraform", f"-chdir={legacy}"]
        backend = "powerlifting-app/coach/terraform.tfstate" if app == "coach" else f"powerlifting-app/k8s/{app}.tfstate"
        subprocess.run([*tf, "init", "-input=false", f"-backend-config=bucket={os.environ['TF_STATE_BUCKET']}",
                        f"-backend-config=key={backend}", f"-backend-config=region={os.environ['AWS_REGION']}",
                        "-backend-config=encrypt=true", "-backend-config=use_lockfile=true"], check=True)
        varfile = Path(os.environ["RUNNER_TEMP"]) / ("coach.tfvars" if app == "coach" else "k8s.tfvars")
        listed = set(subprocess.check_output([*tf, "state", "list"], text=True).splitlines())
        for record in records[app]:
            if record["address"] not in listed:
                subprocess.run([*tf, "import", "-input=false", "-lock-timeout=2m", f"-var-file={varfile}",
                                record["address"], record["id"]], check=True, stdout=subprocess.DEVNULL)
        plan = work / f"{app}.rollback.plan"
        subprocess.run([*tf, "plan", "-input=false", f"-var-file={varfile}", f"-out={plan}"], check=True, stdout=subprocess.DEVNULL)
        changes = json.loads(subprocess.check_output([*tf, "show", "-json", plan])).get("resource_changes", [])
        require(all("delete" not in c["change"]["actions"] for c in changes if c["mode"] == "managed"), f"Rollback would delete resources in {app}")


if __name__ == "__main__":
    rollback(sys.argv[1], Path(sys.argv[2]))
