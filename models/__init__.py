"""
Models package initialization.
Exports all 20 core relational models for the OTT Rights and Royalty Engine.
"""
from database.base import Base

# Table 1: Titles & Title Splits
from models.title import Title, TitleSplit

# Tables 2 & 3: Licensors & Splits
from models.licensor import Licensor, LicensorSplit

# Tables 4, 14, 16: Contracts, Minimum Guarantees, Payment Caps
from models.contract import LicenceContract, MinimumGuarantee, PaymentCap

# Tables 5 & 7: Windows & Holdbacks
from models.window import LicenceWindow, Holdback

# Tables 6 & 17: Territories, Time Zones, and Withholding Tax Rates
from models.territory import Territory, TerritoryTimeZone, WithholdingTaxRate

# Tables 8 & 11: Subscriber Tiers & Monthly Subscription Revenue
from models.subscriber import SubscriberTier, MonthlySubscriptionRevenue

# Tables 9 & 10: View Events & Qualifying Records
from models.viewership import ViewEvent, QualifyingViewRecord

# Tables 12 & 13: Advertisement Revenue & Ad Impressions
from models.advertising import AdvertisementRevenue, AdImpression

# Table: Title Share Records
from models.revenue import TitleShareRecord

# Tables 15, 18, 19: Settlements, Recoupment Records, Payment Transactions
from models.settlement import MonthlySettlement, RecoupmentRecord, PaymentTransaction

# Table 20: Audit Logs
from models.audit import AuditLog

__all__ = [
    "Base",
    "Title",
    "TitleSplit",
    "Licensor",
    "LicensorSplit",
    "LicenceContract",
    "LicenceWindow",
    "Territory",
    "TerritoryTimeZone",
    "Holdback",
    "SubscriberTier",
    "ViewEvent",
    "QualifyingViewRecord",
    "MonthlySubscriptionRevenue",
    "AdvertisementRevenue",
    "AdImpression",
    "TitleShareRecord",
    "MinimumGuarantee",
    "RecoupmentRecord",
    "PaymentCap",
    "WithholdingTaxRate",
    "MonthlySettlement",
    "PaymentTransaction",
    "AuditLog",
]
