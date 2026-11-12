import re
import unittest

from image_tag import image_tag


class ImageTagTests(unittest.TestCase):
    def test_master_uses_latest(self):
        self.assertEqual(image_tag("master"), "latest")

    def test_feature_branches_are_stable_valid_tags(self):
        for branch in ("main", "istio", "feature/istio", "latest", "Master", "a" * 300, "fix/登录"):
            with self.subTest(branch=branch):
                tag = image_tag(branch)
                self.assertNotEqual(tag, "latest")
                self.assertEqual(tag, image_tag(branch))
                self.assertIsNotNone(re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", tag))

    def test_normalized_branch_names_do_not_collide(self):
        self.assertNotEqual(image_tag("feature/istio"), image_tag("feature-istio"))
        self.assertNotEqual(image_tag("a" * 100 + "/first"), image_tag("a" * 100 + "/second"))

    def test_empty_and_whitespace_names_fail(self):
        for branch in ("", "feature istio", "master\n"):
            with self.subTest(branch=branch):
                with self.assertRaises(ValueError):
                    image_tag(branch)


if __name__ == "__main__":
    unittest.main()
