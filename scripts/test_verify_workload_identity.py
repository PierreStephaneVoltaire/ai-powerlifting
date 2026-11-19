import unittest

from verify_workload_identity import expected_denial


class DenialClassificationTests(unittest.TestCase):
    def test_wrong_subject_access_denied_is_expected(self):
        self.assertTrue(expected_denial("AccessDenied", "not trusted"))

    def test_wrong_audience_invalid_token_is_expected(self):
        self.assertTrue(expected_denial("InvalidIdentityToken", "audience claim is invalid", wrong_audience=True))

    def test_wrong_audience_requires_specific_invalid_token_reason(self):
        self.assertFalse(expected_denial("AccessDenied", "not trusted", wrong_audience=True))

    def test_key_retrieval_invalid_token_is_not_expected_denial(self):
        self.assertFalse(expected_denial("InvalidIdentityToken", "unable to retrieve public keys", wrong_audience=True))

    def test_transport_error_is_not_expected_denial(self):
        self.assertFalse(expected_denial("EndpointConnectionError", "Could not connect", wrong_audience=True))

    def test_identity_provider_rejection_is_not_generic_denial(self):
        self.assertFalse(expected_denial("IDPRejectedClaim", "identity provider rejected token", wrong_audience=True))


if __name__ == "__main__":
    unittest.main()
