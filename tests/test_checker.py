import unittest

from proxyChecker import parse_status_line, socks4_connect_request


class Socks4RequestTests(unittest.TestCase):
    def test_connect_request_layout(self):
        request = socks4_connect_request("1.2.3.4", 8080)
        self.assertEqual(request, b"\x04\x01\x1f\x90\x01\x02\x03\x04\x00")

    def test_port_is_big_endian(self):
        self.assertEqual(socks4_connect_request("8.8.8.8", 443)[2:4], b"\x01\xbb")


class StatusLineTests(unittest.TestCase):
    def test_parses_common_status_lines(self):
        self.assertEqual(parse_status_line(b"HTTP/1.1 200 OK\r\n"), 200)
        self.assertEqual(parse_status_line(b"HTTP/1.0 301 Moved Permanently\r\n"), 301)
        self.assertEqual(parse_status_line(b"HTTP/1.1 407 Proxy Authentication Required\r\n"), 407)

    def test_rejects_malformed_lines(self):
        self.assertEqual(parse_status_line(b""), 0)
        self.assertEqual(parse_status_line(b"HELLO 200 OK\r\n"), 0)
        self.assertEqual(parse_status_line(b"HTTP/1.1\r\n"), 0)


if __name__ == "__main__":
    unittest.main()
