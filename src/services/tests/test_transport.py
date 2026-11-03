import importlib
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from services.contract import load_operations
from services.principal import principal_token


class TransportTests(unittest.TestCase):
    def test_http_mcp_calculation_parity_and_auth(self):
        with patch.dict(os.environ, {"PL_DOMAIN": "profile", "INTERNAL_API_TOKEN": "test-only", "PL_PRINCIPAL_SECRET": "transport-test-principal-signing-secret"}):
            module = importlib.reload(importlib.import_module("services.app"))
            with patch.object(module, 'OPERATIONS', load_operations('calculations')), patch('services.authorization.current_context', return_value={'permissions': []}), TestClient(module.app) as client:
                self.assertEqual(client.post("/operations/kg_to_lb", json={"kg": 100}).status_code, 401)
                headers = {"X-Internal-Token": "test-only", 'X-PL-Principal': principal_token('', '', 'kg_to_lb')}
                http = client.post("/operations/kg_to_lb", headers=headers, json={"kg": 100})
                self.assertEqual(http.status_code, 200, http.text)
                response = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "kg_to_lb", "arguments": {"kg": 100}}})
                self.assertEqual(response.json()["result"]["structuredContent"], http.json())
                schema = client.get("/openapi.json").json()["paths"]["/operations/kg_to_lb"]["post"]["requestBody"]["content"]["application/json"]["schema"]
                listed = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).json()["result"]["tools"]
                self.assertEqual(next(tool["inputSchema"] for tool in listed if tool["name"] == "kg_to_lb"), schema)
                self.assertEqual(client.post("/operations/kg_to_lb", headers=headers, json={"kg": "bad"}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
