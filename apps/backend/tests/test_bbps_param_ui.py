"""Catalogue param UI rules: hide fixed Cir_Id / bank codes; enum selects; no date-format defaults."""

from __future__ import annotations

from django.test import SimpleTestCase

from integrations.bbps import (
    _circle_from_sheet,
    _constant_default,
    _enrich_ad_param,
    _icon_url,
    _parse_enum_options,
)


class BbpsParamUiTests(SimpleTestCase):
    def test_fixed_cir_id_is_default_not_user_prompt(self):
        self.assertEqual(_circle_from_sheet("11"), (False, "11"))
        self.assertEqual(_circle_from_sheet("11.0"), (False, "11"))
        self.assertEqual(_circle_from_sheet(""), (False, ""))
        self.assertEqual(_circle_from_sheet("na"), (False, ""))

    def test_constant_defaults_skip_regex_dates_and_lists(self):
        self.assertEqual(_constant_default("ICIC"), "ICIC")
        self.assertEqual(_constant_default("11.0"), "11")
        self.assertEqual(_constant_default("^[0-9]{10}$"), "")
        self.assertEqual(_constant_default("dd/MM/yyyy"), "")
        self.assertEqual(_constant_default("yyyy-MM-dd"), "")
        self.assertEqual(_constant_default("Monthly,Bimonthly"), "")

    def test_enum_options_from_label_code_and_plain_list(self):
        cities = _parse_enum_options("Agra : 201, Surat : 204, Bhiwandi : 203")
        self.assertEqual(
            [(o["label"], o["value"]) for o in cities],
            [("Agra", "201"), ("Surat", "204"), ("Bhiwandi", "203")],
        )
        bills = _parse_enum_options("Monthly,Bimonthly")
        self.assertEqual([o["value"] for o in bills], ["Monthly", "Bimonthly"])

    def test_enrich_hides_bank_code_and_exposes_city_select(self):
        bank = _enrich_ad_param(
            key="ad3",
            fetch_key="ad3",
            pay_key="ad3",
            label="Bank Code",
            regex_val="SBIN",
            optional=False,
        )
        self.assertTrue(bank["ui_hidden"])
        self.assertEqual(bank["default_value"], "SBIN")
        self.assertEqual(bank["options"], [])

        city = _enrich_ad_param(
            key="ad1",
            fetch_key="ad1",
            pay_key="ad1",
            label="City",
            regex_val="Agra : 201, Ahmedabad : 202",
            optional=False,
        )
        self.assertFalse(city["ui_hidden"])
        self.assertEqual(len(city["options"]), 2)
        self.assertEqual(city["default_value"], "")

        optional_mobile = _enrich_ad_param(
            key="ad22",
            fetch_key="ad22",
            pay_key="ad22",
            label="Mobile Number of Parent",
            regex_val="^[0-9]{10}$",
            optional=True,
        )
        self.assertFalse(optional_mobile["ui_hidden"])
        self.assertTrue(optional_mobile["optional"])

    def test_fastag_icons_reuse_mobikwik_brand_ops(self):
        hdfc = _icon_url("294", category="FASTAG", circle_default="15")
        icici = _icon_url("294", category="FASTAG", circle_default="14")
        airtel = _icon_url("294", category="FASTAG", circle_default="30")
        jk = _icon_url("294", category="FASTAG", circle_default="22")
        generic = _icon_url("294", category="FASTAG", circle_default="")
        self.assertTrue(hdfc.endswith("op285.png"))
        self.assertTrue(icici.endswith("op37.png"))
        self.assertTrue(airtel.endswith("op1.png"))
        self.assertNotEqual(hdfc, icici)
        self.assertIn("gstatic.com", jk)
        self.assertIn("jkbank.com", jk)
        self.assertTrue(generic.endswith("op294.png"))

    def test_credit_card_icons_reuse_brand_ops(self):
        icici = _icon_url("208", category="CREDIT_CARD", circle_default="1")
        axis = _icon_url("208", category="CREDIT_CARD", circle_default="23")
        iob = _icon_url("208", category="CREDIT_CARD", circle_default="7")
        self.assertTrue(icici.endswith("op37.png"))
        self.assertTrue(axis.endswith("op239.png"))
        self.assertIn("gstatic.com", iob)
        self.assertIn("iob.in", iob)
