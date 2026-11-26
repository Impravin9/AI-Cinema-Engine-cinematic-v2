import unittest

from asset_licensing import lic_ok


class LicenceFilterTests(unittest.TestCase):
    def test_accepts_public_domain_cc0_and_cc_by(self):
        for licence in (
            "Public domain",
            "Public Domain Mark",
            "CC0",
            "CC0 1.0",
            "CC BY",
            "CC BY 4.0",
            "CC-BY-3.0",
        ):
            with self.subTest(licence=licence):
                self.assertTrue(lic_ok(licence))

    def test_rejects_restrictive_or_ambiguous_licences(self):
        for licence in (
            "CC BY-SA 4.0",
            "CC BY-NC 4.0",
            "CC BY-NC-SA 4.0",
            "CC BY-ND 4.0",
            "CC BY-NC-ND 4.0",
            "Attribution",
            "All rights reserved",
            "",
        ):
            with self.subTest(licence=licence):
                self.assertFalse(lic_ok(licence))


if __name__ == "__main__":
    unittest.main()
