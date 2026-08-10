"""Packaging smoke tests for the installed server and its runtime dependencies."""

import os
import unittest


class ServerImportTest(unittest.TestCase):
    def test_server_imports_with_supported_mcp_sdk(self):
        os.environ.setdefault("SEC_EDGAR_USER_AGENT", "Package Test (package-test@example.com)")

        from sec_edgar_mcp import server

        self.assertTrue(callable(server.main))


if __name__ == "__main__":
    unittest.main()
