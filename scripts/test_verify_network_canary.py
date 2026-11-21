import unittest
from types import SimpleNamespace
from unittest.mock import patch

from verify_network_canary import blocked, curl, ingress_blocked


class CanaryChecks(unittest.TestCase):
    def test_curl_extracts_remote_failure(self):
        result = SimpleNamespace(returncode=1, stdout="000", stderr="command terminated with exit code 28\n")
        with patch("verify_network_canary.subprocess.run", return_value=result):
            self.assertTrue(blocked(curl("powerlifting", "canary", None, "https://example.com")))

    def test_dns_and_exec_failures_do_not_count_as_denials(self):
        self.assertFalse(blocked((6, "000")))
        self.assertFalse(blocked((1, "")))
        self.assertFalse(blocked((0, "200")))
        self.assertFalse(blocked((0, "403")))
        self.assertTrue(ingress_blocked((0, "403")))


if __name__ == "__main__":
    unittest.main()
