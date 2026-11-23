"""Regression tests for ASE endpoint selection and browser cleanup."""

import ast
from contextlib import closing
from datetime import datetime
from pathlib import Path
import re
import unittest
from unittest.mock import Mock, call
from urllib.parse import urljoin

from bs4 import BeautifulSoup


APP_PATH = Path(__file__).resolve().parents[1] / "scraper_app.py"
PRIMARY_URL = "https://www.ase.com.jo/en/disclosure"
FALLBACK_URL = "https://www.exchange.jo/en/disclosure"
DISCLOSURE_VIEW = '<div class="view-ase-circulars-disclosures view-display-id-page_2">{}</div>'


class ASEDisclosureTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
        names = {
            "ASEDisclosureUnavailable", "iter_jordan_disclosures", "parse_ase_disclosure_page",
            "process_updates",
        }
        definitions = [
            node for node in tree.body
            if getattr(node, "name", None) in names
            or (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id.startswith("ASE_"))
        ]
        self.driver = Mock()
        self.close_driver = Mock()
        self.scrape_symbol = Mock()
        self.namespace = {
            "make_ase_driver": Mock(return_value=self.driver),
            "_close_ase_driver": self.close_driver,
            "scrape_jordan_disclosures": self.scrape_symbol,
            "print": Mock(),
            "BeautifulSoup": BeautifulSoup,
            "re": re,
            "urljoin": urljoin,
            "closing": closing,
        }
        # Load the scraper functions without starting Streamlit or its scheduler.
        exec(compile(ast.Module(body=definitions, type_ignores=[]), str(APP_PATH), "exec"), self.namespace)

    def test_valid_empty_search_stays_on_primary(self):
        filing = {"Symbol": "AAIN"}
        self.scrape_symbol.side_effect = [[], [filing]]

        self.assertEqual(list(self.namespace["iter_jordan_disclosures"](["MEIN", "AAIN"])), [filing])
        self.assertEqual(self.scrape_symbol.call_args_list, [
            call(PRIMARY_URL, "MEIN", self.driver), call(PRIMARY_URL, "AAIN", self.driver),
        ])
        self.close_driver.assert_called_once_with(self.driver)

    def test_retries_failed_symbol_then_reuses_fallback(self):
        unavailable = self.namespace["ASEDisclosureUnavailable"]
        filings = [{"Symbol": "MEIN"}, {"Symbol": "AAIN"}]
        self.scrape_symbol.side_effect = [unavailable("page unavailable"), filings[:1], filings[1:]]

        self.assertEqual(list(self.namespace["iter_jordan_disclosures"](["MEIN", "AAIN"])), filings)
        self.assertEqual(self.scrape_symbol.call_args_list, [
            call(PRIMARY_URL, "MEIN", self.driver), call(FALLBACK_URL, "MEIN", self.driver),
            call(FALLBACK_URL, "AAIN", self.driver),
        ])
        self.namespace["make_ase_driver"].assert_called_once_with()

    def test_both_endpoints_unavailable_raise_and_close_driver(self):
        unavailable = self.namespace["ASEDisclosureUnavailable"]
        self.scrape_symbol.side_effect = [unavailable("primary down"), unavailable("fallback down")]

        with self.assertRaises(unavailable):
            list(self.namespace["iter_jordan_disclosures"](["MEIN"]))
        self.close_driver.assert_called_once_with(self.driver)

    def test_recovers_when_preferred_endpoint_changes_during_sweep(self):
        unavailable = self.namespace["ASEDisclosureUnavailable"]
        self.scrape_symbol.side_effect = [unavailable("primary down"), [], unavailable("fallback down"), []]

        self.assertEqual(list(self.namespace["iter_jordan_disclosures"](["MEIN", "AAIN"])), [])
        self.assertEqual(self.scrape_symbol.call_args_list, [
            call(PRIMARY_URL, "MEIN", self.driver), call(FALLBACK_URL, "MEIN", self.driver),
            call(FALLBACK_URL, "AAIN", self.driver), call(PRIMARY_URL, "AAIN", self.driver),
        ])

    def test_explicit_empty_view_is_a_success(self):
        html = DISCLOSURE_VIEW.format('<div class="view-empty">No results found</div>')

        self.assertEqual(self.namespace["parse_ase_disclosure_page"](html, PRIMARY_URL), [])

    def test_missing_results_view_is_an_endpoint_failure(self):
        html = DISCLOSURE_VIEW.format('<input id="edit-symbol" value="MEIN">')

        with self.assertRaises(self.namespace["ASEDisclosureUnavailable"]):
            self.namespace["parse_ase_disclosure_page"](html, PRIMARY_URL)

    def test_attachment_links_use_the_serving_host(self):
        html = DISCLOSURE_VIEW.format(
            '<table class="cols-9"><tbody><tr><td>Quarterly report</td><td>MEIN</td>'
            '<td>Middle East Insurance</td><td>Quarterly Report</td><td>29/10/2026</td>'
            '<td><a href="/en/download/disclosure/1">PDF</a></td>'
            '<td><a href="https://xbrljordan.jo/iweb/index">XBRL</a></td><td></td><td></td>'
            '</tr></tbody></table>'
        )

        filings = self.namespace["parse_ase_disclosure_page"](html, FALLBACK_URL)

        self.assertEqual(filings[0]["File_Links"], {
            "pdf": "https://www.exchange.jo/en/download/disclosure/1",
            "xbrl": "https://xbrljordan.jo/iweb/index",
        })

    def test_ase_report_skips_untracked_related_symbols(self):
        market = "Jordan (Amman Stock Exchange)"
        report_date = datetime(2026, 10, 29)
        self.namespace.update(
            MARKETS={market: {"companies": {"MEIN": "Middle East Insurance"}}},
            get_app_state=Mock(return_value=(report_date, [], False, {})),
            parse_universal_date=Mock(return_value=report_date),
        )
        filing = {"Disclosure": "Quarterly report", "Date": "29/10/2026", "Category": "Quarterly Report", "File_Links": {}}
        self.scrape_symbol.return_value = [dict(filing, Symbol="BROKER23-MEIN"), dict(filing, Symbol="MEIN")]

        _, _, count, rows = self.namespace["process_updates"](
            market, manual_start=report_date.date(), manual_end=report_date.date(),
        )

        self.assertEqual(count, 1)
        self.assertEqual(rows[0]["Symbol"], "MEIN")
