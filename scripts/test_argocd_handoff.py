import json
import unittest
from unittest.mock import patch

from argocd_handoff import TRACKING, check_render, identity, kube, transfers


class AdoptionTest(unittest.TestCase):
    def setUp(self):
        self.obj = {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "pl-sessions", "namespace": "powerlifting"}}
        self.key = identity(self.obj)
        self.metadata = {**self.obj["metadata"], "uid": "original", "annotations": {TRACKING: f"nolift-app:{self.key}"}}
        self.change = {"mode": "managed", "type": "kubernetes_service_v1", "address": "kubernetes_service_v1.sessions",
                       "change": {"actions": ["delete"], "before": {"metadata": [self.metadata]}}}

    def release(self):
        return transfers([self.change], "app", {self.key: self.obj})

    @patch("argocd_handoff.kube")
    def test_only_existing_self_tracked_objects_are_releasable(self, get):
        get.return_value = {"metadata": self.metadata}
        self.assertEqual(self.release()[0]["id"], "powerlifting/pl-sessions")
        for metadata in ({**self.metadata, "uid": "replacement"},
                         {**self.metadata, "annotations": {TRACKING: f"nolift-network:{self.key}"}}):
            get.return_value = {"metadata": metadata}
            with self.assertRaises(SystemExit):
                self.release()
        self.change["change"]["actions"] = ["delete", "create"]
        with self.assertRaises(SystemExit):
            self.release()

    @patch("argocd_handoff.subprocess.run")
    def test_kubectl_get_file_can_wrap_a_single_object_in_a_list(self, run):
        run.return_value.returncode = 0
        run.return_value.stdout = json.dumps({"kind": "List", "items": [self.obj]})
        self.assertEqual(kube("get", obj=self.obj), self.obj)

    def test_render_rejects_private_markers_and_unpinned_ecr_images(self):
        repo = "000000000000.dkr.ecr.us-east-1.amazonaws.com/if-sessions"
        deployment = {**self.obj, "kind": "Deployment", "spec": {"template": {"spec": {"containers": []}}}}
        for value in ("if-sessions", f"{repo}:latest", "nolift:private:unknown"):
            deployment["spec"]["template"]["spec"]["containers"] = [{"image": value}]
            with self.assertRaises(SystemExit):
                check_render([deployment])
        deployment["spec"]["template"]["spec"]["containers"] = [{"image": f"{repo}@sha256:{'a' * 64}"}]
        check_render([deployment])


if __name__ == "__main__":
    unittest.main()
