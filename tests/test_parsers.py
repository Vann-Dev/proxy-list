import unittest

from proxyScraper import Source, parse_geonode, parse_html_table, parse_source_body

GEONODE_BODY = """
{"data": [
  {"ip": "8.8.8.8", "port": "8080"},
  {"ip": "10.0.0.1", "port": "3128"},
  {"ip": "1.1.1.1", "port": "0"}
]}
"""

TABLE_BODY = """
<table id="proxylisttable" class="table table-striped table-bordered">
  <thead><tr><th>IP Address</th><th>Port</th><th>Code</th><th>Country</th><th>Anonymity</th><th>Google</th><th>Https</th></tr></thead>
  <tbody>
    <tr><td>8.8.8.8</td><td>8080</td><td>US</td><td>United States</td><td>elite</td><td>yes</td><td>yes</td></tr>
    <tr><td>1.1.1.1</td><td>3128</td><td>AU</td><td>Australia</td><td>elite</td><td>no</td><td>no</td></tr>
    <tr><td>9.9.9.9</td><td>80</td><td>FR</td><td>France</td><td>anonymous</td><td>yes</td><td>yes</td></tr>
  </tbody>
</table>
"""


class GeonodeParserTests(unittest.TestCase):
    def test_extracts_ip_and_port_fields(self):
        self.assertEqual(parse_geonode(GEONODE_BODY), ["8.8.8.8:8080"])

    def test_missing_data_key(self):
        self.assertEqual(parse_geonode('{"message": "rate limited"}'), [])


class HtmlTableParserTests(unittest.TestCase):
    def test_http_table_keeps_all_public_rows(self):
        self.assertEqual(parse_html_table(TABLE_BODY, "http"), ["8.8.8.8:8080", "1.1.1.1:3128", "9.9.9.9:80"])

    def test_https_table_filters_on_https_column(self):
        self.assertEqual(parse_html_table(TABLE_BODY, "https"), ["8.8.8.8:8080", "9.9.9.9:80"])

    def test_missing_table_returns_empty(self):
        self.assertEqual(parse_html_table("<html><body>blocked</body></html>", "http"), [])


class SourceDispatchTests(unittest.TestCase):
    def test_text_parser(self):
        source = Source("test", "https://example.com", "http")
        self.assertEqual(parse_source_body(source, "8.8.8.8:8080\n1.1.1.1:3128"), ["8.8.8.8:8080", "1.1.1.1:3128"])

    def test_geonode_dispatch(self):
        source = Source("test", "https://example.com", "socks5", parser="geonode")
        self.assertEqual(parse_source_body(source, GEONODE_BODY), ["8.8.8.8:8080"])


if __name__ == "__main__":
    unittest.main()
