import unittest

from validate_terraform_plan import validate


class TerraformPlanTests(unittest.TestCase):
    def resource(self, resource_type, actions):
        return {"address": f"{resource_type}.production", "type": resource_type, "change": {"actions": actions}}

    def test_updates_and_creations_are_allowed(self):
        validate({"resource_changes": [
            self.resource("aws_dynamodb_table", ["update"]),
            self.resource("aws_ssm_parameter", ["create"]),
        ]})
        validate({"resource_changes": []})

    def test_aws_deletion_and_replacement_are_rejected(self):
        for resource_type in ("aws_dynamodb_table", "aws_s3_bucket", "aws_ssm_parameter"):
            for actions in (["delete"], ["delete", "create"], ["create", "delete"]):
                with self.subTest(resource_type=resource_type, actions=actions), self.assertRaisesRegex(ValueError, resource_type):
                    validate({"resource_changes": [self.resource(resource_type, actions)]})

    def test_non_aws_changes_are_not_rejected(self):
        validate({"resource_changes": [self.resource("cloudflare_record", ["delete"])]})


if __name__ == "__main__":
    unittest.main()
