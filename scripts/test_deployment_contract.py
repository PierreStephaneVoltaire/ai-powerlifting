import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

from image_tag import image_tag


ROOT = Path(__file__).resolve().parents[1]


class DeploymentContractTests(unittest.TestCase):
    def test_push_to_istio_deploys_all_components(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/build-images.yml").read_text())
        triggers = workflow.get("on") or workflow[True]
        self.assertIn("istio", triggers["push"]["branches"])
        self.assertNotIn("paths", triggers["push"])
        result = next(step for step in workflow["jobs"]["changes"]["steps"] if step.get("id") == "result")
        script = result["run"].replace("${{ github.event_name }}", "push")
        for component in ("backend", "frontend", "services", "terraform", "kubernetes"):
            script = script.replace("${{ steps.filter.outputs." + component + " }}", "false")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            subprocess.run(
                ["bash", "-e", "-c", script],
                env=dict(os.environ, GITHUB_OUTPUT=str(output)),
                check=True,
            )
            self.assertEqual(
                set(output.read_text().splitlines()),
                {f"{component}=true" for component in ("backend", "frontend", "services", "terraform", "kubernetes")},
            )

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
