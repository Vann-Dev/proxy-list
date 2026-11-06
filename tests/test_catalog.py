import json
import tempfile
import unittest
from pathlib import Path

from proxy_geo import parse_tsv
from proxyCatalog import Entry, build_catalog, discover_results, merge_results

GEO_TSV = "\n".join(  # noqa: FLY002 - keep the columns visible
    [
        "134744064\t134744319\t15169\tUS\tGOOGLE",
        "16777216\t16777471\t13335\tUS\tCLOUDFLARENET",
        "16777472\t16778239\t0\tNone\tNot routed",
        "",
    ]
)


def result_payload(protocol: str, address: str, sites: dict[str, int], tested: int = 10) -> dict:
    return {
        "generated_at": "2026-11-06T00:00:00Z",
        "protocol": protocol,
        "input": f"proxies/{protocol}.txt",
        "input_count": tested,
        "sites": [{"name": slug, "url": f"https://{slug}.com", "alive": 1} for slug in sites],
        "count": 1,
        "proxies": [
            {
                "address": address,
                "ip": address.partition(":")[0],
                "port": int(address.partition(":")[2]),
                "sites": sites,
            }
        ],
    }


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for protocol in ("http", "https"):
            directory = self.root / f"{protocol}-tested"
            directory.mkdir()
            sites = {"google": 111, "discord": 222} if protocol == "http" else {"google": 90, "twitter": 300}
            (directory / "proxies.json").write_text(
                json.dumps(result_payload(protocol, "8.8.8.8:8080", sites)), encoding="utf-8"
            )
        self.geo = parse_tsv(GEO_TSV.splitlines(), updated_at="2026-11-01T00:00:00Z")

    def tearDown(self):
        self.temp.cleanup()

    def test_discover_and_merge_across_protocols(self):
        paths = discover_results(self.root)
        self.assertEqual(len(paths), 2)
        entries, summaries = merge_results(paths)
        self.assertEqual(list(entries), ["8.8.8.8:8080"])
        entry = entries["8.8.8.8:8080"]
        self.assertEqual(entry.protocols, {"http", "https"})
        # Lowest latency wins when an address appears in several results.
        self.assertEqual(entry.sites, {"google": 90, "discord": 222, "twitter": 300})
        self.assertEqual(set(summaries), {"http", "https"})

    def test_build_catalog_enriches_and_counts(self):
        entries, summaries = merge_results(discover_results(self.root))
        catalog, stats = build_catalog(entries, summaries, self.geo, generated_at="2026-11-06T00:00:00Z")

        self.assertEqual(catalog["count"], 1)
        proxy = catalog["proxies"][0]
        self.assertEqual(proxy["address"], "8.8.8.8:8080")
        self.assertEqual(proxy["protocols"], ["http", "https"])
        self.assertEqual(proxy["country"], "US")
        self.assertEqual(proxy["asn"], "AS15169")
        self.assertEqual(proxy["as_name"], "GOOGLE")
        self.assertEqual(catalog["geo"]["updated_at"], "2026-11-01T00:00:00Z")

        self.assertEqual(stats["total_proxies"], 1)
        self.assertEqual(stats["protocols"]["http"]["alive"], 1)
        self.assertEqual(stats["protocols"]["http"]["tested"], 10)
        self.assertEqual(stats["sites"]["google"]["total"], 2)
        self.assertEqual(stats["sites"]["google"]["by_protocol"], {"http": 1, "https": 1})
        self.assertEqual(stats["countries"], {"US": 1})

    def test_unknown_address_has_null_geo(self):
        entries, summaries = merge_results(discover_results(self.root))
        entries["9.9.9.9:80"] = Entry(address="9.9.9.9:80")
        catalog, _ = build_catalog(entries, summaries, self.geo)
        unknown = next(item for item in catalog["proxies"] if item["address"] == "9.9.9.9:80")
        self.assertIsNone(unknown["country"])
        self.assertIsNone(unknown["asn"])

    def test_private_addresses_are_rejected(self):
        directory = self.root / "socks5-tested"
        directory.mkdir()
        (directory / "proxies.json").write_text(
            json.dumps(result_payload("socks5", "10.0.0.1:1080", {"google": 10})), encoding="utf-8"
        )
        entries, _ = merge_results(discover_results(self.root))
        self.assertNotIn("10.0.0.1:1080", entries)


class GeoLookupTests(unittest.TestCase):
    def test_lookup_inside_and_outside_ranges(self):
        geo = parse_tsv(GEO_TSV.splitlines())
        self.assertEqual(geo.lookup("8.8.8.8"), ("US", "AS15169", "GOOGLE"))
        self.assertEqual(geo.lookup("1.0.0.1"), ("US", "AS13335", "CLOUDFLARENET"))
        self.assertEqual(geo.lookup("9.9.9.9"), (None, None, None))

    def test_unrouted_range_has_no_country(self):
        geo = parse_tsv(GEO_TSV.splitlines())
        self.assertEqual(geo.lookup("1.0.1.1"), (None, None, None))

    def test_invalid_ip(self):
        geo = parse_tsv(GEO_TSV.splitlines())
        self.assertEqual(geo.lookup("not-an-ip"), (None, None, None))


if __name__ == "__main__":
    unittest.main()
