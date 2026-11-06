import unittest

from proxy_utils import (
    normalize_address,
    parse_entry,
    parse_ip_port_text,
    site_slug,
    site_url,
    sort_key,
)


class NormalizeAddressTests(unittest.TestCase):
    def test_accepts_public_ipv4(self):
        self.assertEqual(normalize_address("8.8.8.8", "8080"), "8.8.8.8:8080")
        self.assertEqual(normalize_address(" 1.2.3.4 ", 3128), "1.2.3.4:3128")

    def test_rejects_non_public_ranges(self):
        for ip in ["127.0.0.1", "10.0.0.1", "192.168.1.1", "172.16.0.1", "0.0.0.0", "224.0.0.1", "198.51.100.0"]:
            with self.subTest(ip=ip):
                self.assertIsNone(normalize_address(ip, 8080))

    def test_rejects_invalid_values(self):
        for ip, port in [("999.1.1.1", 80), ("8.8.8.8", 0), ("8.8.8.8", 70000), ("8.8.8.8", "abc"), ("", 80)]:
            with self.subTest(ip=ip, port=port):
                self.assertIsNone(normalize_address(ip, port))


class ParseEntryTests(unittest.TestCase):
    def test_bare_and_prefixed_entries(self):
        self.assertEqual(parse_entry("8.8.8.8:8080"), "8.8.8.8:8080")
        self.assertEqual(parse_entry("http://8.8.8.8:8080/"), "8.8.8.8:8080")
        self.assertEqual(parse_entry("socks5://8.8.8.8:1080"), "8.8.8.8:1080")
        self.assertEqual(parse_entry('  "8.8.8.8:8080"  '), "8.8.8.8:8080")

    def test_rejects_garbage(self):
        for entry in ["", "not-a-proxy", "8.8.8.8", "8.8.8.8:", "host:8080"]:
            with self.subTest(entry=entry):
                self.assertIsNone(parse_entry(entry))


class ParseTextTests(unittest.TestCase):
    def test_extracts_pairs_from_free_form_text(self):
        body = """
        8.8.8.8:8080
        http://1.2.3.4:3128
        9.9.9.9:4145:United States
        10.0.0.1:80
        """
        self.assertEqual(parse_ip_port_text(body), ["8.8.8.8:8080", "1.2.3.4:3128", "9.9.9.9:4145"])

    def test_ignores_embedded_ip_without_port(self):
        self.assertEqual(parse_ip_port_text("server at 8.8.8.8 is down"), [])


class OrderingTests(unittest.TestCase):
    def test_numeric_sort(self):
        addresses = ["10.0.0.2:80", "9.0.0.1:8080", "10.0.0.1:443"]
        # 10.0.0.x is private, but sort_key only orders strings it is given.
        self.assertEqual(sorted(addresses, key=sort_key), ["9.0.0.1:8080", "10.0.0.1:443", "10.0.0.2:80"])


class SiteTests(unittest.TestCase):
    def test_site_url_scheme_depends_on_proxy_method(self):
        self.assertEqual(site_url("google.com", "http"), "http://google.com")
        self.assertEqual(site_url("google.com", "https"), "https://google.com")
        self.assertEqual(site_url("google.com", "socks5"), "https://google.com")
        self.assertEqual(site_url("https://example.com/x", "http"), "https://example.com/x")

    def test_site_slug(self):
        self.assertEqual(site_slug("https://www.google.com/"), "google")
        self.assertEqual(site_slug("http://facebook.com"), "facebook")
        self.assertEqual(site_slug("https://www.google.co.id/search"), "google")


if __name__ == "__main__":
    unittest.main()
