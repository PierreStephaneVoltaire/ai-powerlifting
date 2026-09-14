import importlib
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


class TransportTests(unittest.TestCase):
    def test_http_mcp_calculation_parity_and_auth(self):
        with patch.dict(os.environ, {"PL_DOMAIN": "calculations", "INTERNAL_API_TOKEN": "test-only"}):
            module = importlib.import_module("services.app")
            with TestClient(module.app) as client:
                self.assertEqual(client.post("/operations/kg_to_lb", json={"kg": 100}).status_code, 401)
                headers = {"X-Internal-Token": "test-only"}
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
