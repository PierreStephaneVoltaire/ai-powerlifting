from fnmatch import fnmatchcase
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import yaml

from image_tag import image_tag


ROOT = Path(__file__).resolve().parents[1]


class DeploymentContractTests(unittest.TestCase):
    def test_push_paths_exclude_documentation(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/build-images.yml").read_text())
        triggers = workflow.get("on") or workflow[True]
        self.assertEqual(triggers["push"]["branches"], ["**"])
        self.assertIn("github.ref_protected", workflow["jobs"]["changes"]["if"])
        self.assertIn("github.ref_type == 'branch'", workflow["jobs"]["changes"]["if"])
        self.assertNotIn("pull_request", triggers)
        pull_requests = yaml.safe_load((ROOT / ".github/workflows/pull-requests.yml").read_text())
        pr_triggers = pull_requests.get("on") or pull_requests[True]
        self.assertEqual(set(pr_triggers), {"pull_request"})
        cases = (
            ("README.md", False),
            ("docs/architecture.md", False),
            ("src/frontend/README.md", False),
            ("src/services/coach/README.md", False),
            ("terraform/k8s/README.md", False),
            ("src/frontend/src/main.tsx", True),
            ("src/backend/src/server.ts", True),
            ("src/services/lib/oidc.py", True),
            ("src/services/coach/requirements.txt", True),
            ("docker/powerlifting-services.pkr.hcl", True),
            ("src/lambda/video-thumbnail/index.py", True),
            ("terraform/k8s/app/mesh.tf", True),
            ("src/package.json", True),
            ("src/package-lock.json", True),
            ("src/tsconfig.json", True),
            ("src/dependencies/types/index.ts", True),
            (".github/workflows/build-images.yml", True),
            (".github/workflows/pull-requests.yml", True),
        )
        for event, paths in (("push", triggers["push"]["paths"]), ("pull_request", pr_triggers["pull_request"]["paths"])):
            for path, expected in cases:
                with self.subTest(event=event, path=path):
                    included = False
                    for pattern in paths:
                        if fnmatchcase(path, pattern.lstrip("!")):
                            included = not pattern.startswith("!")
                    self.assertEqual(included, expected)

    def test_component_filters_cover_all_build_inputs(self):
        filters = yaml.safe_load((ROOT / ".github/image-filters.yml").read_text())
        for path, expected in (
            ("src/frontend/src/main.tsx", {"frontend"}),
            ("src/services/lib/oidc.py", {"backend", "services"}),
            ("src/dependencies/types/index.ts", {"backend", "frontend", "services"}),
            ("src/package.json", {"backend", "frontend", "services"}),
            ("src/package-lock.json", {"backend", "frontend", "services"}),
            ("src/backend/package.json", {"backend", "frontend", "services"}),
            ("src/tsconfig.json", {"backend", "frontend", "services"}),
            ("docker/powerlifting-services.pkr.hcl", {"backend", "frontend", "services"}),
            ("src/lambda/master-sync/handler.py", {"terraform"}),
            (".github/workflows/pull-requests.yml", {"backend", "frontend", "services", "terraform"}),
        ):
            with self.subTest(path=path):
                selected = {
                    component for component, patterns in filters.items()
                    if any(fnmatchcase(path, pattern) or fnmatchcase(path, pattern.replace("/**/", "/")) for pattern in patterns)
                }
                self.assertEqual(selected, expected)

    def test_pushes_preserve_component_filters(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/build-images.yml").read_text())
        filter_step = next(step for step in workflow["jobs"]["changes"]["steps"] if step.get("id") == "filter")
        self.assertEqual(filter_step["with"]["base"], "${{ github.ref }}")
        result = next(step for step in workflow["jobs"]["changes"]["steps"] if step.get("id") == "result")
        components = ("backend", "frontend", "services", "terraform", "kubernetes")
        for event, changed in (
            ("push", set()),
            ("push", {"frontend"}),
            ("push", {"backend", "services"}),
            ("push", {"terraform", "kubernetes"}),
            ("workflow_dispatch", set()),
        ):
            with self.subTest(event=event, changed=changed), tempfile.TemporaryDirectory() as directory:
                script = result["run"].replace("${{ github.event_name }}", event)
                for component in components:
                    script = script.replace(
                        "${{ steps.filter.outputs." + component + " }}",
                        str(component in changed).lower(),
                    )
                output = Path(directory) / "output"
                subprocess.run(
                    ["bash", "-e", "-c", script],
                    env=dict(os.environ, GITHUB_OUTPUT=str(output)),
                    check=True,
                )
                expected = set(components) if event == "workflow_dispatch" else changed
                self.assertEqual(
                    dict(line.split("=") for line in output.read_text().splitlines()),
                    {component: str(component in expected).lower() for component in components},
                )

    def test_manual_apply_defaults_to_disabled_for_both_stacks(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/build-images.yml").read_text())
        triggers = workflow.get("on") or workflow[True]
        self.assertEqual(triggers["workflow_dispatch"]["inputs"]["apply_terraform"]["default"], "false")
        for job in ("terraform-apply", "security-apply", "kubernetes-apply"):
            for event, branch, protected, ref_type, apply, expected in (
                ("push", "master", True, "branch", "false", True),
                ("push", "master", False, "branch", "false", False),
                ("push", "release/next", True, "branch", "false", True),
                ("push", "release/next", False, "branch", "false", False),
                ("push", "v1", True, "tag", "false", False),
                ("pull_request", "istio", True, "branch", "true", False),
                ("workflow_dispatch", "istio", True, "branch", "false", False),
                ("workflow_dispatch", "istio", True, "branch", "true", True),
                ("workflow_dispatch", "istio", False, "branch", "true", False),
                ("workflow_dispatch", "master", True, "branch", "false", False),
            ):
                with self.subTest(job=job, event=event, branch=branch, protected=protected, ref_type=ref_type, apply=apply):
                    expression = workflow["jobs"][job]["if"].strip().removeprefix("${{").removesuffix("}}")
                    replacements = {
                        "github.event_name": repr(event),
                        "github.ref": repr(f"refs/heads/{branch}"),
                        "github.ref_type": repr(ref_type),
                        "github.ref_protected": str(protected),
                        "inputs.apply_terraform": repr(apply),
                        "github.triggering_actor": "'owner'",
                        "github.repository_owner": "'owner'",
                        "github.actor": "'owner'",
                        "needs.terraform-plan.result": "'success'",
                        "needs.changes.outputs.kubernetes": "'true'",
                        "always()": "True",
                        "contains(needs.*.result, 'failure')": "False",
                        "contains(needs.*.result, 'cancelled')": "False",
                    }
                    for component in ("backend", "frontend", "services", "coach"):
                        replacements[f"needs.build-{component}.result"] = "'success'"
                    for original in sorted(replacements, key=len, reverse=True):
                        value = replacements[original]
                        expression = expression.replace(original, value)
                    expression = re.sub(r"!(?!=)", " not ", expression).replace("&&", " and ").replace("||", " or ")
                    self.assertEqual(eval(" ".join(expression.split()), {"__builtins__": {}}, {}), expected)

    def test_master_uses_main_and_other_branches_use_stage(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/build-images.yml").read_text())
        for name, job in workflow["jobs"].items():
            if name == "changes":
                continue
            for branch, expected in (("master", "main"), ("main", "stage"), ("istio", "stage"), ("release/next", "stage")):
                with self.subTest(job=name, branch=branch):
                    expression = job["environment"].strip().removeprefix("${{").removesuffix("}}")
                    expression = expression.replace("github.ref_name", repr(branch)).replace("&&", " and ").replace("||", " or ")
                    self.assertEqual(eval(expression.strip(), {"__builtins__": {}}, {}), expected)

    def test_deployment_provisions_keys_and_migrates_pointers(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/build-images.yml").read_text())
        kubernetes = workflow["jobs"]["kubernetes-apply"]
        self.assertIn("security-apply", kubernetes["needs"])
        security = workflow["jobs"]["security-apply"]
        self.assertTrue(any("key=powerlifting-app/security.tfstate" in step.get("run", "") for step in security["steps"]))
        migration = next(step for step in kubernetes["steps"] if step.get("name") == "Preserve existing identity pointers")
        self.assertEqual(migration["run"].splitlines(), [
            "python scripts/migrate_identity_pointers.py",
            "python scripts/migrate_identity_pointers.py --apply",
        ])

    def test_pull_requests_build_without_publishing(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/pull-requests.yml").read_text())
        self.assertNotIn("id-token", workflow["permissions"])
        build = next(step for step in workflow["jobs"]["images"]["steps"] if "packer build" in step.get("run", ""))
        self.assertIn("-except=publish", build["run"])
        self.assertNotIn("secrets.", (ROOT / ".github/workflows/pull-requests.yml").read_text())
        for template in (ROOT / "docker").glob("powerlifting-*.pkr.hcl"):
            self.assertRegex(template.read_text(), r'post-processor "docker-push"\s*\{\s*name\s*=\s*"publish"')

    def test_pull_request_image_selection(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/pull-requests.yml").read_text())
        step = next(step for step in workflow["jobs"]["changes"]["steps"] if step.get("id") == "images")
        for selected, expected in (
            (set(), []),
            ({"FRONTEND"}, ["powerlifting-frontend"]),
            ({"SERVICES"}, ["powerlifting-services", "powerlifting-analytics", "powerlifting-coach-agent", "powerlifting-coach-discord"]),
            ({"BACKEND", "FRONTEND", "SERVICES"}, ["powerlifting-backend", "powerlifting-frontend", "powerlifting-services", "powerlifting-analytics", "powerlifting-coach-agent", "powerlifting-coach-discord"]),
        ):
            with self.subTest(selected=selected), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "output"
                environment = dict(os.environ, GITHUB_OUTPUT=str(output), BRANCH="feature/istio")
                environment.update({component: str(component in selected).lower() for component in ("BACKEND", "FRONTEND", "SERVICES")})
                subprocess.run(["bash", "-e", "-c", step["run"]], cwd=ROOT, env=environment, check=True)
                result = dict(line.split("=", 1) for line in output.read_text().splitlines())
                self.assertEqual(json.loads(result["matrix"]), expected)
                self.assertEqual(result["tag"], image_tag("feature/istio"))

    def test_full_pipeline_applies_matching_images_and_coach_state(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/build-images.yml").read_text())
        job = workflow["jobs"]["kubernetes-apply"]
        step = next(step for step in job["steps"] if "APPLY_COACH" in step.get("env", {}))
        mock = '''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys
with open(os.environ["CALL_LOG"], "a") as log:
    log.write(json.dumps([Path(sys.argv[0]).name, *sys.argv[1:]]) + "\\n")
if "output" in sys.argv:
    if "-chdir=core" not in sys.argv:
        sys.exit("namespace output belongs to core")
    print("powerlifting")
'''
        for branch in ("master", "feature/istio"):
            with self.subTest(branch=branch), tempfile.TemporaryDirectory() as directory:
                temporary = Path(directory)
                for command in ("terraform", "kubectl"):
                    executable = temporary / command
                    executable.write_text(mock)
                    executable.chmod(0o700)
                log = temporary / "calls.jsonl"
                tag = image_tag(branch)
                environment = dict(
                    os.environ,
                    PATH=f"{temporary}:{os.environ['PATH']}",
                    CALL_LOG=str(log),
                    RUNNER_TEMP=str(temporary),
                    TF_STATE_BUCKET="test-state-bucket",
                    AWS_REGION="ca-central-1",
                    APPLY_COACH="true",
                    IMAGE_TAG=tag,
                )
                subprocess.run(
                    ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
                    cwd=ROOT / "terraform/k8s",
                    env=environment,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                calls = [json.loads(line) for line in log.read_text().splitlines()]
                applies = [call for call in calls if call[0] == "terraform" and "apply" in call]
                self.assertEqual(
                    [call[1] for call in applies],
                    [f"-chdir={stack}" for stack in ("core", "perms", "network", "mesh", "app", "../coach")],
                )
                for call in applies:
                    if call[1] in ("-chdir=app", "-chdir=../coach"):
                        self.assertEqual(call[-1], f"-var=image_tag={tag}")
                    else:
                        self.assertFalse(any(argument.startswith("-var=image_tag=") for argument in call))
                self.assertTrue(any("key=powerlifting-app/coach/terraform.tfstate" in " ".join(call) for call in calls))
                self.assertTrue(any("deployment/pl-coach-discord" in call for call in calls))


if __name__ == "__main__":
    unittest.main()
