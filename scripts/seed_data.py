"""
Comprehensive Seed Data Script for OTT Rights & Royalty Engine (PS-090).
Populates realistic sample data across all 20 relational database tables.
"""
from __future__ import annotations

import sys
import hashlib
import json
from pathlib import Path
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from database.connection import get_db_session, init_database, engine
from models import (
    Territory,
    TerritoryTimeZone,
    WithholdingTaxRate,
    Title,
    Licensor,
    LicensorSplit,
    LicenceContract,
    MinimumGuarantee,
    PaymentCap,
    LicenceWindow,
    Holdback,
    SubscriberTier,
    MonthlySubscriptionRevenue,
    ViewEvent,
    QualifyingViewRecord,
    AdvertisementRevenue,
    AdImpression,
    MonthlySettlement,
    RecoupmentRecord,
    PaymentTransaction,
    AuditLog,
)
from services.split_validator import validate_contract_splits


def seed_database() -> None:
    print("Beginning database seeding across all 20 entities...")
    init_database(engine)

    with get_db_session() as session:
        # Check if already seeded
        existing = session.query(Territory).first()
        if existing:
            print("Database already contains data. Skipping re-seed.")
            return

        now_utc = datetime.now(timezone.utc)

        # ---------------------------------------------------------------------
        # 1. Territories & Time Zones (Table 6)
        # ---------------------------------------------------------------------
        print("Seeding Territories & IANA Time Zones...")
        t_us = Territory(
            country_code="US",
            country_name="United States of America",
            default_currency="USD",
            primary_iana_timezone="America/New_York",
            is_sanctioned=False,
            is_active=True
        )
        t_gb = Territory(
            country_code="GB",
            country_name="United Kingdom",
            default_currency="GBP",
            primary_iana_timezone="Europe/London",
            is_sanctioned=False,
            is_active=True
        )
        t_in = Territory(
            country_code="IN",
            country_name="Republic of India",
            default_currency="INR",
            primary_iana_timezone="Asia/Kolkata",
            is_sanctioned=False,
            is_active=True
        )
        t_de = Territory(
            country_code="DE",
            country_name="Federal Republic of Germany",
            default_currency="EUR",
            primary_iana_timezone="Europe/Berlin",
            is_sanctioned=False,
            is_active=True
        )
        t_jp = Territory(
            country_code="JP",
            country_name="Japan",
            default_currency="JPY",
            primary_iana_timezone="Asia/Tokyo",
            is_sanctioned=False,
            is_active=True
        )
        session.add_all([t_us, t_gb, t_in, t_de, t_jp])
        session.flush()

        # Multi-zone entries for US
        us_tz_list = [
            TerritoryTimeZone(country_code="US", iana_timezone="America/New_York", zone_description="Eastern Time", is_primary=True),
            TerritoryTimeZone(country_code="US", iana_timezone="America/Chicago", zone_description="Central Time", is_primary=False),
            TerritoryTimeZone(country_code="US", iana_timezone="America/Denver", zone_description="Mountain Time", is_primary=False),
            TerritoryTimeZone(country_code="US", iana_timezone="America/Los_Angeles", zone_description="Pacific Time", is_primary=False),
            TerritoryTimeZone(country_code="GB", iana_timezone="Europe/London", zone_description="Greenwich Mean Time", is_primary=True),
            TerritoryTimeZone(country_code="IN", iana_timezone="Asia/Kolkata", zone_description="Indian Standard Time", is_primary=True),
            TerritoryTimeZone(country_code="DE", iana_timezone="Europe/Berlin", zone_description="Central European Time", is_primary=True),
            TerritoryTimeZone(country_code="JP", iana_timezone="Asia/Tokyo", zone_description="Japan Standard Time", is_primary=True),
        ]
        session.add_all(us_tz_list)

        # ---------------------------------------------------------------------
        # 2. Withholding Tax Rates & Treaties (Table 17)
        # ---------------------------------------------------------------------
        print("Seeding Withholding Tax & DTAA Treaty Rates...")
        wht_rules = [
            WithholdingTaxRate(
                source_country_code="US",
                recipient_country_code="US",
                statutory_wht_rate=Decimal("0.00"),
                treaty_wht_rate=Decimal("0.00"),
                effective_wht_rate=Decimal("0.00"),
                treaty_reference="Domestic US Entity Exemption",
                effective_from=date(2020, 1, 1),
                is_active=True
            ),
            WithholdingTaxRate(
                source_country_code="US",
                recipient_country_code="GB",
                statutory_wht_rate=Decimal("30.00"),
                treaty_wht_rate=Decimal("0.00"),
                effective_wht_rate=Decimal("0.00"),
                treaty_reference="US-UK Income Tax Treaty Article 12 (Royalties)",
                effective_from=date(2020, 1, 1),
                is_active=True
            ),
            WithholdingTaxRate(
                source_country_code="US",
                recipient_country_code="DE",
                statutory_wht_rate=Decimal("30.00"),
                treaty_wht_rate=Decimal("0.00"),
                effective_wht_rate=Decimal("0.00"),
                treaty_reference="US-Germany DTAA Article 12",
                effective_from=date(2020, 1, 1),
                is_active=True
            ),
            WithholdingTaxRate(
                source_country_code="US",
                recipient_country_code="IN",
                statutory_wht_rate=Decimal("30.00"),
                treaty_wht_rate=Decimal("15.00"),
                effective_wht_rate=Decimal("15.00"),
                treaty_reference="US-India DTAA Article 12 (Royalties & Fees)",
                effective_from=date(2020, 1, 1),
                is_active=True
            ),
            WithholdingTaxRate(
                source_country_code="US",
                recipient_country_code="JP",
                statutory_wht_rate=Decimal("30.00"),
                treaty_wht_rate=Decimal("0.00"),
                effective_wht_rate=Decimal("0.00"),
                treaty_reference="US-Japan Tax Convention Article 12",
                effective_from=date(2020, 1, 1),
                is_active=True
            ),
        ]
        session.add_all(wht_rules)

        # ---------------------------------------------------------------------
        # 3. Titles (Table 1)
        # ---------------------------------------------------------------------
        print("Seeding Audiovisual Titles...")
        title1 = Title(
            isan_code="0000-0001-8A3F-0000-Z-0000-0000-A",
            title_name="Chronicles of Nebula",
            content_type="FILM",
            duration_seconds=7200,  # 120 minutes
            production_year=2024,
            original_language="en",
            age_rating="PG-13",
            is_active=True
        )
        title2 = Title(
            isan_code="0000-0002-9B4C-0000-Y-0000-0000-B",
            title_name="Cyberpunk Odyssey: Neo Tokyo",
            content_type="FILM",
            duration_seconds=6300,  # 105 minutes
            production_year=2025,
            original_language="ja",
            age_rating="TV-MA",
            is_active=True
        )
        title3 = Title(
            isan_code="0000-0003-7C5D-0000-X-0000-0000-C",
            title_name="The Silicon Heist",
            content_type="SERIES_EPISODE",
            duration_seconds=3600,  # 60 minutes pilot
            production_year=2026,
            original_language="en",
            age_rating="TV-14",
            is_active=True
        )
        session.add_all([title1, title2, title3])
        session.flush()

        # ---------------------------------------------------------------------
        # 4. Licensors (Table 2)
        # ---------------------------------------------------------------------
        print("Seeding Licensors & Studios...")
        licensor_apex = Licensor(
            legal_name="Apex Pictures Global Inc.",
            trade_name="Apex Studios",
            tax_id="EIN-12-3456789",
            country="United States",
            country_code="US",
            is_indian=False,
            settlement_currency="USD",
            iban_swift="CHASUS33XXX",
            contact_email="royalties@apexpictures.com",
            is_active=True
        )
        licensor_solaris = Licensor(
            legal_name="Solaris Media Productions Ltd.",
            trade_name="Solaris Films",
            tax_id="GB-987654321",
            country="United Kingdom",
            country_code="GB",
            is_indian=False,
            settlement_currency="GBP",
            iban_swift="BARCGB22XXX",
            contact_email="accounts@solarismedia.co.uk",
            is_active=True
        )
        licensor_tokyo = Licensor(
            legal_name="Tokyo Motion Arts K.K.",
            trade_name="TMA Studios",
            tax_id="JP-1029384756",
            country="Japan",
            country_code="JP",
            is_indian=False,
            settlement_currency="USD",
            iban_swift="BOTKJPJTXXX",
            contact_email="licensing@tokyomotion.jp",
            is_active=True
        )
        licensor_guild = Licensor(
            legal_name="Directors & Writers Residuals Escrow Fund",
            trade_name="Industry Guilds Trust",
            tax_id="EIN-98-7654321",
            country="United States",
            country_code="US",
            is_indian=False,
            settlement_currency="USD",
            iban_swift="WELLUS66XXX",
            contact_email="disbursements@guildstrust.org",
            is_active=True
        )
        session.add_all([licensor_apex, licensor_solaris, licensor_tokyo, licensor_guild])
        session.flush()

        # ---------------------------------------------------------------------
        # 5. Licence Contracts (Table 4)
        # ---------------------------------------------------------------------
        print("Seeding Licence Contracts...")
        contract1 = LicenceContract(
            contract_number="LIC-2026-APEX-001",
            licensor_id=licensor_apex.licensor_id,
            title_id=title1.title_id,
            deal_type="SVOD_PRO_RATA",
            rev_share_percentage=Decimal("70.00"),
            technical_fee_percentage=Decimal("1.50"),
            effective_date=date(2026, 1, 1),
            expiration_date=date(2027, 12, 31),
            settlement_frequency="MONTHLY",
            contract_currency="USD",
            status="ACTIVE"
        )
        contract2 = LicenceContract(
            contract_number="LIC-2026-SOLARIS-002",
            licensor_id=licensor_solaris.licensor_id,
            title_id=title3.title_id,
            deal_type="HYBRID_MG",
            rev_share_percentage=Decimal("65.00"),
            technical_fee_percentage=Decimal("0.00"),
            effective_date=date(2026, 3, 1),
            expiration_date=date(2028, 2, 28),
            settlement_frequency="MONTHLY",
            contract_currency="USD",
            status="ACTIVE"
        )
        contract3 = LicenceContract(
            contract_number="LIC-2026-TOKYO-003",
            licensor_id=licensor_tokyo.licensor_id,
            title_id=title2.title_id,
            deal_type="AVOD_REVENUE_SHARE",
            rev_share_percentage=Decimal("60.00"),
            technical_fee_percentage=Decimal("2.00"),
            effective_date=date(2026, 6, 1),
            expiration_date=date(2027, 5, 31),
            settlement_frequency="MONTHLY",
            contract_currency="USD",
            status="ACTIVE"
        )
        session.add_all([contract1, contract2, contract3])
        session.flush()

        # ---------------------------------------------------------------------
        # 6. Licensor Splits (Table 3) - Validating 100% Rule
        # ---------------------------------------------------------------------
        print("Seeding Licensor Splits & Validating 100% Constraints...")
        c1_splits = [
            LicensorSplit(
                contract_id=contract1.contract_id,
                licensor_id=licensor_apex.licensor_id,
                stakeholder_role="STUDIO",
                split_percentage=Decimal("70.00"),
                is_primary_payee=True
            ),
            LicensorSplit(
                contract_id=contract1.contract_id,
                licensor_id=licensor_solaris.licensor_id,
                stakeholder_role="PRODUCER",
                split_percentage=Decimal("20.00"),
                is_primary_payee=False
            ),
            LicensorSplit(
                contract_id=contract1.contract_id,
                licensor_id=licensor_guild.licensor_id,
                stakeholder_role="TALENT_RESIDUAL",
                split_percentage=Decimal("10.00"),
                is_primary_payee=False
            )
        ]
        # Validate that splits sum to exactly 100.00%
        validate_contract_splits(c1_splits, contract1.contract_id)
        session.add_all(c1_splits)

        c2_splits = [
            LicensorSplit(
                contract_id=contract2.contract_id,
                licensor_id=licensor_solaris.licensor_id,
                stakeholder_role="STUDIO",
                split_percentage=Decimal("85.00"),
                is_primary_payee=True
            ),
            LicensorSplit(
                contract_id=contract2.contract_id,
                licensor_id=licensor_guild.licensor_id,
                stakeholder_role="TALENT_RESIDUAL",
                split_percentage=Decimal("15.00"),
                is_primary_payee=False
            )
        ]
        validate_contract_splits(c2_splits, contract2.contract_id)
        session.add_all(c2_splits)

        c3_splits = [
            LicensorSplit(
                contract_id=contract3.contract_id,
                licensor_id=licensor_tokyo.licensor_id,
                stakeholder_role="STUDIO",
                split_percentage=Decimal("100.00"),
                is_primary_payee=True
            )
        ]
        validate_contract_splits(c3_splits, contract3.contract_id)
        session.add_all(c3_splits)
        session.flush()

        # ---------------------------------------------------------------------
        # 7. Minimum Guarantees (Table 14) & Payment Caps (Table 16)
        # ---------------------------------------------------------------------
        print("Seeding Minimum Guarantees & Payment Caps...")
        mg1 = MinimumGuarantee(
            contract_id=contract2.contract_id,
            mg_amount=Decimal("150000.0000"),
            unrecouped_balance=Decimal("150000.0000"),
            currency="USD",
            recoupment_scope="CROSS_COLLATERALIZED",
            effective_from=date(2026, 3, 1),
            effective_to=date(2028, 2, 28),
            status="ACTIVE"
        )
        session.add(mg1)

        cap1 = PaymentCap(
            contract_id=contract1.contract_id,
            cap_amount=Decimal("500000.0000"),
            currency="USD",
            cap_period="MONTHLY",
            is_hard_cap=False,
            is_active=True
        )
        session.add(cap1)
        session.flush()

        # ---------------------------------------------------------------------
        # 8. Licence Windows (Table 5 - Multiple Windows) & Holdbacks (Table 7)
        # ---------------------------------------------------------------------
        print("Seeding Multi-Territory Licence Windows & Holdbacks...")
        win_c1_us = LicenceWindow(
            contract_id=contract1.contract_id,
            title_id=title1.title_id,
            territory_code="US",
            window_type="SVOD",
            start_time_utc=datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc),
            end_time_utc=datetime(2027, 5, 31, 23, 59, 59, tzinfo=timezone.utc),
            exclusivity="EXCLUSIVE",
            allowed_devices="ALL",
            grace_period_minutes=15,
            status="ACTIVE"
        )
        win_c1_gb = LicenceWindow(
            contract_id=contract1.contract_id,
            title_id=title1.title_id,
            territory_code="GB",
            window_type="SVOD",
            start_time_utc=datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc),
            end_time_utc=datetime(2027, 6, 30, 23, 59, 59, tzinfo=timezone.utc),
            exclusivity="NON_EXCLUSIVE",
            allowed_devices="ALL",
            grace_period_minutes=15,
            status="ACTIVE"
        )
        win_c1_de = LicenceWindow(
            contract_id=contract1.contract_id,
            title_id=title1.title_id,
            territory_code="DE",
            window_type="SVOD",
            start_time_utc=datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc),
            end_time_utc=datetime(2027, 6, 30, 23, 59, 59, tzinfo=timezone.utc),
            exclusivity="NON_EXCLUSIVE",
            allowed_devices="ALL",
            grace_period_minutes=15,
            status="ACTIVE"
        )
        win_c2_us = LicenceWindow(
            contract_id=contract2.contract_id,
            title_id=title3.title_id,
            territory_code="US",
            window_type="SVOD",
            start_time_utc=datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc),
            end_time_utc=datetime(2027, 3, 31, 23, 59, 59, tzinfo=timezone.utc),
            exclusivity="EXCLUSIVE",
            allowed_devices="ALL",
            grace_period_minutes=15,
            status="ACTIVE"
        )
        win_c3_us = LicenceWindow(
            contract_id=contract3.contract_id,
            title_id=title2.title_id,
            territory_code="US",
            window_type="AVOD_FAST",
            start_time_utc=datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc),
            end_time_utc=datetime(2027, 7, 31, 23, 59, 59, tzinfo=timezone.utc),
            exclusivity="NON_EXCLUSIVE",
            allowed_devices="ALL",
            grace_period_minutes=15,
            status="ACTIVE"
        )
        session.add_all([win_c1_us, win_c1_gb, win_c1_de, win_c2_us, win_c3_us])

        hb1 = Holdback(
            contract_id=contract1.contract_id,
            title_id=title1.title_id,
            prior_window_type="THEATRICAL",
            subsequent_window_type="SVOD",
            holdback_days=90,
            territory_code="US",
            enforcement_type="STRICT_BLACKOUT",
            is_active=True
        )
        hb2 = Holdback(
            contract_id=contract2.contract_id,
            title_id=title3.title_id,
            prior_window_type="TVOD",
            subsequent_window_type="SVOD",
            holdback_days=45,
            territory_code="US",
            enforcement_type="STRICT_BLACKOUT",
            is_active=True
        )
        session.add_all([hb1, hb2])
        session.flush()

        # ---------------------------------------------------------------------
        # 9. Subscriber Tiers (Table 8)
        # ---------------------------------------------------------------------
        print("Seeding Subscriber Tiers...")
        tier_mob = SubscriberTier(
            tier_code="MOBILE",
            tier_name="Mobile Only",
            monthly_price=Decimal("4.99"),
            currency="USD",
            max_concurrent_streams=1,
            max_resolution="SD",
            is_ad_supported=False,
            is_active=True
        )
        tier_std = SubscriberTier(
            tier_code="STANDARD_HD",
            tier_name="Standard HD",
            monthly_price=Decimal("12.99"),
            currency="USD",
            max_concurrent_streams=2,
            max_resolution="HD",
            is_ad_supported=False,
            is_active=True
        )
        tier_prem = SubscriberTier(
            tier_code="PREMIUM_4K",
            tier_name="Premium 4K Family Plan",
            monthly_price=Decimal("19.99"),
            currency="USD",
            max_concurrent_streams=4,
            max_resolution="4K_UHD",
            is_ad_supported=False,
            is_active=True
        )
        tier_ad = SubscriberTier(
            tier_code="BASIC_AD",
            tier_name="Basic with Ads",
            monthly_price=Decimal("6.99"),
            currency="USD",
            max_concurrent_streams=2,
            max_resolution="HD",
            is_ad_supported=True,
            is_active=True
        )
        session.add_all([tier_mob, tier_std, tier_prem, tier_ad])
        session.flush()

        # ---------------------------------------------------------------------
        # 10. Monthly Subscription Revenue (Table 11)
        # ---------------------------------------------------------------------
        print("Seeding Monthly Subscription Revenue Pool...")
        rev_pool_std_us = MonthlySubscriptionRevenue(
            period_key="2026-10",
            tier_id=tier_std.tier_id,
            territory_code="US",
            currency="USD",
            subscriber_count=100000,
            gross_billing_amount=Decimal("1299000.0000"),
            refunds_chargebacks=Decimal("12990.0000"),      # 1%
            statutory_taxes=Decimal("64950.0000"),          # 5%
            app_store_commissions=Decimal("194850.0000"),   # 15%
            payment_processing_fees=Decimal("25980.0000"),  # 2%
            platform_tech_fee=Decimal("12990.0000"),        # 1%
            net_distributable_pool=Decimal("987240.0000"),  # Net Pool
            is_finalized=True
        )
        session.add(rev_pool_std_us)
        session.flush()

        # ---------------------------------------------------------------------
        # 11. View Events (Table 9) & Qualifying Records (Table 10)
        # ---------------------------------------------------------------------
        print("Seeding Telemetry Playback Events & Qualifying Records...")
        # Event 1: Legitimate full movie stream (7200 seconds)
        ev1 = ViewEvent(
            session_id="sess_us_alpha_101",
            user_id="usr_9871101",
            title_id=title1.title_id,
            tier_id=tier_std.tier_id,
            territory_code="US",
            device_category="SMART_TV",
            playback_start_utc=datetime(2026, 10, 15, 20, 0, 0, tzinfo=timezone.utc),
            playback_end_utc=datetime(2026, 10, 15, 22, 0, 0, tzinfo=timezone.utc),
            raw_watch_seconds=7200,
            ip_address="72.14.201.55",
            is_vpn_detected=False
        )
        # Event 2: Sub-threshold play (15 seconds, disqualified per BR-06)
        ev2 = ViewEvent(
            session_id="sess_us_beta_102",
            user_id="usr_9871102",
            title_id=title1.title_id,
            tier_id=tier_std.tier_id,
            territory_code="US",
            device_category="MOBILE",
            playback_start_utc=datetime(2026, 10, 16, 14, 0, 0, tzinfo=timezone.utc),
            playback_end_utc=datetime(2026, 10, 16, 14, 0, 15, tzinfo=timezone.utc),
            raw_watch_seconds=15,
            ip_address="72.14.201.56",
            is_vpn_detected=False
        )
        # Event 3: Pilot episode stream (3600 seconds)
        ev3 = ViewEvent(
            session_id="sess_us_gamma_103",
            user_id="usr_9871103",
            title_id=title3.title_id,
            tier_id=tier_std.tier_id,
            territory_code="US",
            device_category="DESKTOP",
            playback_start_utc=datetime(2026, 10, 17, 19, 0, 0, tzinfo=timezone.utc),
            playback_end_utc=datetime(2026, 10, 17, 20, 0, 0, tzinfo=timezone.utc),
            raw_watch_seconds=3600,
            ip_address="72.14.201.57",
            is_vpn_detected=False
        )
        session.add_all([ev1, ev2, ev3])
        session.flush()

        qv1 = QualifyingViewRecord(
            view_event_id=ev1.event_id,
            period_key="2026-10",
            title_id=title1.title_id,
            tier_id=tier_std.tier_id,
            territory_code="US",
            qualified_watch_seconds=7200,
            is_qualified=True,
            qualification_status="QUALIFIED"
        )
        qv2 = QualifyingViewRecord(
            view_event_id=ev2.event_id,
            period_key="2026-10",
            title_id=title1.title_id,
            tier_id=tier_std.tier_id,
            territory_code="US",
            qualified_watch_seconds=0,
            is_qualified=False,
            qualification_status="DISQUALIFIED_UNDER_30S"
        )
        qv3 = QualifyingViewRecord(
            view_event_id=ev3.event_id,
            period_key="2026-10",
            title_id=title3.title_id,
            tier_id=tier_std.tier_id,
            territory_code="US",
            qualified_watch_seconds=3600,
            is_qualified=True,
            qualification_status="QUALIFIED"
        )
        session.add_all([qv1, qv2, qv3])
        session.flush()

        # ---------------------------------------------------------------------
        # 12. Advertisement Revenue (Table 12) & Impressions (Table 13)
        # ---------------------------------------------------------------------
        print("Seeding Ad Revenue & Impressions...")
        ad_rev = AdvertisementRevenue(
            period_key="2026-10",
            territory_code="US",
            ad_network_name="Google Ad Manager",
            currency="USD",
            total_impressions_served=5000000,
            gross_ad_revenue=Decimal("85000.0000"),
            agency_commissions=Decimal("12750.0000"),     # 15%
            ad_server_tech_fees=Decimal("4250.0000"),     # 5%
            net_distributable_ad_pool=Decimal("68000.0000"),
            is_finalized=True
        )
        session.add(ad_rev)
        session.flush()

        ad_imp1 = AdImpression(
            view_event_id=ev1.event_id,
            title_id=title1.title_id,
            territory_code="US",
            ad_campaign_id="CAMP-Q4-TECH-901",
            placement_type="MIDROLL",
            impression_time_utc=datetime(2026, 10, 15, 20, 45, 0, tzinfo=timezone.utc),
            effective_cpm=Decimal("17.5000"),
            ad_duration_seconds=15,
            was_completed=True,
            gross_value=Decimal("0.0175")
        )
        session.add(ad_imp1)
        session.flush()

        # ---------------------------------------------------------------------
        # 13. Monthly Settlements (Table 18) & Recoupment Records (Table 15)
        # ---------------------------------------------------------------------
        print("Seeding Monthly Settlements, Recoupments, & Remittances...")
        # Let's say in October 2026, total catalog qualified seconds = 10,800s (7,200 for title1 + 3,600 for title3)
        # Title1 consumption share = 7,200 / 10,800 = 66.666667%
        # Pool allocated to Title1 = $987,240 * (7200 / 10800) = $658,160.00
        # Contract 1 rev share = 70% -> Gross royalty = $658,160 * 70% = $460,712.00
        # Less tech fee 1.5% = $6,910.68 -> Net gross royalty = $453,801.32
        # Apex is US resident -> Withholding tax = 0%
        # Net payable to Apex = $453,801.32 * 70% (Studio split) = $317,660.92

        settlement_apex = MonthlySettlement(
            settlement_run_number="RUN-202610-001",
            period_key="2026-10",
            contract_id=contract1.contract_id,
            licensor_id=licensor_apex.licensor_id,
            title_id=title1.title_id,
            total_qualified_seconds=7200,
            catalog_total_seconds=10800,
            consumption_share_ratio=Decimal("0.66666667"),
            distributable_pool_amount=Decimal("987240.0000"),
            gross_royalty_amount=Decimal("317660.9200"),
            mg_recouped_amount=Decimal("0.0000"),
            withholding_tax_amount=Decimal("0.0000"),
            net_payable_amount=Decimal("317660.9200"),
            settlement_currency="USD",
            fx_rate_applied=Decimal("1.000000"),
            status="LOCKED",
            locked_at_utc=datetime(2026, 11, 2, 0, 0, 0, tzinfo=timezone.utc),
            cryptographic_hash=hashlib.sha256(b"RUN-202610-001-APEX-LOCKED").hexdigest()
        )
        session.add(settlement_apex)

        # Title3 for Solaris (Contract 2 with MG Recoupment):
        # Consumption share = 3,600 / 10,800 = 33.333333%
        # Pool allocated = $987,240 * 0.33333333 = $329,080.00
        # Contract 2 rev share = 65% -> Gross royalty = $213,902.00
        # Solaris Studio share (85%) = $181,816.70
        # MG Recoupment: MG has $150,000 balance. We recoup full $150,000!
        # Remaining gross = $181,816.70 - $150,000.00 = $31,816.70
        # UK resident -> US-UK Treaty WHT = 0%
        # Net payable to Solaris = $31,816.70
        settlement_solaris = MonthlySettlement(
            settlement_run_number="RUN-202610-001",
            period_key="2026-10",
            contract_id=contract2.contract_id,
            licensor_id=licensor_solaris.licensor_id,
            title_id=title3.title_id,
            total_qualified_seconds=3600,
            catalog_total_seconds=10800,
            consumption_share_ratio=Decimal("0.33333333"),
            distributable_pool_amount=Decimal("987240.0000"),
            gross_royalty_amount=Decimal("181816.7000"),
            mg_recouped_amount=Decimal("150000.0000"),
            withholding_tax_amount=Decimal("0.0000"),
            net_payable_amount=Decimal("31816.7000"),
            settlement_currency="USD",
            fx_rate_applied=Decimal("1.000000"),
            status="LOCKED",
            locked_at_utc=datetime(2026, 11, 2, 0, 0, 0, tzinfo=timezone.utc),
            cryptographic_hash=hashlib.sha256(b"RUN-202610-001-SOLARIS-LOCKED").hexdigest()
        )
        session.add(settlement_solaris)
        session.flush()

        # Recoupment Record (Table 15)
        rec_record = RecoupmentRecord(
            mg_id=mg1.mg_id,
            settlement_id=settlement_solaris.settlement_id,
            period_key="2026-10",
            opening_unrecouped_balance=Decimal("150000.0000"),
            amount_recouped=Decimal("150000.0000"),
            closing_unrecouped_balance=Decimal("0.0000")
        )
        # Update MG balance and status
        mg1.unrecouped_balance = Decimal("0.0000")
        mg1.status = "FULLY_RECOUPED"
        session.add(rec_record)

        # ---------------------------------------------------------------------
        # 14. Payment Transactions (Table 19)
        # ---------------------------------------------------------------------
        pay_apex = PaymentTransaction(
            settlement_id=settlement_apex.settlement_id,
            licensor_id=licensor_apex.licensor_id,
            payment_reference="PAY-202611-0001",
            disbursed_amount=Decimal("317660.9200"),
            currency="USD",
            payment_method="ACH",
            payment_status="SETTLED",
            disbursed_at_utc=datetime(2026, 11, 3, 14, 30, 0, tzinfo=timezone.utc)
        )
        pay_solaris = PaymentTransaction(
            settlement_id=settlement_solaris.settlement_id,
            licensor_id=licensor_solaris.licensor_id,
            payment_reference="PAY-202611-0002",
            disbursed_amount=Decimal("31816.7000"),
            currency="USD",
            payment_method="WIRE_TRANSFER",
            payment_status="SETTLED",
            disbursed_at_utc=datetime(2026, 11, 3, 15, 0, 0, tzinfo=timezone.utc)
        )
        session.add_all([pay_apex, pay_solaris])

        # ---------------------------------------------------------------------
        # 15. Audit Logs (Table 20)
        # ---------------------------------------------------------------------
        print("Seeding Audit Log Ledger...")
        audit_entry1 = AuditLog(
            table_name="licence_contracts",
            record_id=contract1.contract_id,
            action="INSERT",
            performed_by="contract_admin@ottplatform.com",
            new_values_json=json.dumps({"contract_number": "LIC-2026-APEX-001", "rev_share": "70.00"}),
            cryptographic_hash=hashlib.sha256(b"AUDIT-001-CONTRACT-INSERT").hexdigest()
        )
        audit_entry2 = AuditLog(
            table_name="monthly_settlements",
            record_id=settlement_apex.settlement_id,
            action="SETTLEMENT_LOCK",
            performed_by="royalty_finance_lead@ottplatform.com",
            new_values_json=json.dumps({"period": "2026-10", "status": "LOCKED", "net_payable": "317660.92"}),
            cryptographic_hash=hashlib.sha256(b"AUDIT-002-SETTLEMENT-LOCK").hexdigest()
        )
        session.add_all([audit_entry1, audit_entry2])

        print("[OK] All 20 tables successfully seeded with compliant domain records.")


if __name__ == "__main__":
    seed_database()
