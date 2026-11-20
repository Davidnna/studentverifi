"""Compatibility with the previous preview test filename.

This file intentionally contains current backend assertions, so that uploading
this complete release over the React preview branch never retains obsolete
imports from preview-only functions that the hardened backend does not expose.
"""
import unittest

class ReleaseSmokeCompatibility(unittest.TestCase):
    def test_current_adapter_imports_without_database(self):
        import spa_api
        self.assertTrue(hasattr(spa_api, 'install'))
        self.assertTrue(hasattr(spa_api, 'public_student'))
