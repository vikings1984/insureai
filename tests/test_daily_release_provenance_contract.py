import unittest
from pathlib import Path


class DailyReleaseProvenanceContractTests(unittest.TestCase):
    def test_stale_is_allowed_but_verified_requires_release_match(self):
        workflow = Path('.github/workflows/daily-collect.yml').read_text(encoding='utf-8')
        self.assertIn("deployment.get('status') in {'pending','stale','verified'}", workflow)
        self.assertIn("deployment.get('verified') is False or (deployment.get('status') == 'verified' and deployment.get('release_match') is True)", workflow)


if __name__ == '__main__':
    unittest.main()
