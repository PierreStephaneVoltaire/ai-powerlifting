import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


class DigestRenderingTest(unittest.TestCase):
    def test_unchanged_digests_keep_the_same_pod_template(self):
        digest = "sha256:" + "a" * 64
        for app in ("app", "coach"):
            with self.subTest(app=app), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                shutil.copytree(Path(__file__).resolve().parents[1] / "deploy" / "argocd" / app, directory, dirs_exist_ok=True)
                path = directory / "kustomization.yaml"
                config = yaml.safe_load(path.read_text())
                repos = set()
                for name in config["resources"]:
                    for doc in yaml.safe_load_all((directory / name).read_text()):
                        if doc["kind"] == "Deployment":
                            repos.update(c["image"] for c in doc["spec"]["template"]["spec"]["containers"] if re.fullmatch("if-[a-z0-9-]+", c["image"]))
                self.assertTrue(repos)
                previous = {}
                for override in ({"newTag": "latest"}, {"digest": digest}, {"newTag": "latest", "digest": digest}):
                    config["images"] = [{"name": repo, "newName": "registry.invalid/" + repo, **override} for repo in sorted(repos)]
                    path.write_text(yaml.safe_dump(config))
                    docs = yaml.safe_load_all(subprocess.check_output(["kubectl", "kustomize", directory]))
                    templates = {d["metadata"]["name"]: d["spec"]["template"] for d in docs if d["kind"] == "Deployment"}
                    actual = {c["image"] for template in templates.values() for c in template["spec"]["containers"]
                              if c["image"].startswith("registry.invalid/")}
                    suffix = "@" + digest if "digest" in override else ":latest"
                    self.assertEqual(actual, {"registry.invalid/" + repo + suffix for repo in repos})
                    if "newTag" in override and "digest" in override:
                        self.assertEqual(templates, previous)
                    previous = templates


if __name__ == "__main__":
    unittest.main()
