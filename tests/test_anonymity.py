import unittest

from proxy_anonymity import (
    ANONYMOUS,
    ELITE,
    TRANSPARENT,
    UNKNOWN,
    classify,
    echo_headers,
    echo_ip,
    ip_url,
    weakest,
)

CLIENT_IP = "203.0.113.10"


class ClassifyTests(unittest.TestCase):
    def test_no_proxy_headers_is_elite(self):
        headers = {"Host": "example.com", "User-Agent": "Mozilla/5.0"}
        self.assertEqual(classify(headers), ELITE)

    def test_proxy_header_without_client_ip_is_anonymous(self):
        headers = {"X-Forwarded-For": "198.51.100.7", "User-Agent": "Mozilla/5.0"}
        self.assertEqual(classify(headers, CLIENT_IP), ANONYMOUS)

    def test_client_ip_in_forwarded_header_is_transparent(self):
        headers = {"X-Forwarded-For": f"{CLIENT_IP}, 198.51.100.7"}
        self.assertEqual(classify(headers, CLIENT_IP), TRANSPARENT)

    def test_client_ip_in_forwarded_rfc7239_header_is_transparent(self):
        headers = {"Forwarded": f"for={CLIENT_IP};proto=https"}
        self.assertEqual(classify(headers, CLIENT_IP), TRANSPARENT)

    def test_unknown_client_ip_cannot_be_transparent(self):
        headers = {"X-Real-IP": CLIENT_IP}
        self.assertEqual(classify(headers, None), ANONYMOUS)

    def test_via_header_marks_a_proxy(self):
        headers = {"Via": "1.1 squid"}
        self.assertEqual(classify(headers), ANONYMOUS)

    def test_header_names_are_case_insensitive(self):
        headers = {"x-fOrWaRdEd-FoR": "198.51.100.7"}
        self.assertEqual(classify(headers, CLIENT_IP), ANONYMOUS)


class EchoPayloadTests(unittest.TestCase):
    def test_echo_headers_returns_header_map(self):
        payload = {"headers": {"User-Agent": "curl", "X-Forwarded-For": "198.51.100.7"}}
        self.assertEqual(
            echo_headers(payload),
            {"User-Agent": "curl", "X-Forwarded-For": "198.51.100.7"},
        )

    def test_echo_headers_rejects_unexpected_payloads(self):
        self.assertEqual(echo_headers(None), {})
        self.assertEqual(echo_headers({"headers": ["nope"]}), {})

    def test_echo_ip_uses_first_origin(self):
        self.assertEqual(echo_ip({"origin": "203.0.113.10, 198.51.100.7"}), CLIENT_IP)
        self.assertEqual(echo_ip({"ip": CLIENT_IP}), CLIENT_IP)
        self.assertIsNone(echo_ip({"headers": {}}))

    def test_ip_url_keeps_host_and_replaces_path(self):
        self.assertEqual(ip_url("https://httpbingo.org/headers"), "https://httpbingo.org/ip")
        self.assertEqual(ip_url("http://example.com:8080/anything"), "http://example.com:8080/ip")


class WeakestTests(unittest.TestCase):
    def test_least_private_wins(self):
        self.assertEqual(weakest(["elite", "anonymous"]), ANONYMOUS)
        self.assertEqual(weakest(["anonymous", "transparent"]), TRANSPARENT)
        self.assertEqual(weakest(["elite", None, "unknown"]), ELITE)

    def test_no_data_is_unknown(self):
        self.assertEqual(weakest([None, None]), UNKNOWN)


if __name__ == "__main__":
    unittest.main()
