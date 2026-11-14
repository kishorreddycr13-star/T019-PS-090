"""
Licensor Service Module.
Coordinates licensor onboarding, country/tax domicile registration, profile maintenance, and queries.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import List, Optional

from database.connection import get_db_session
from models.licensor import Licensor
from repositories.licensor_repository import LicensorRepository
from validators import (
    validate_licensor_input,
    EntityNotFoundError,
    ValidationError,
)


class LicensorService:
    """Business service for Studio, Distributor, and Licensor management."""

    def __init__(self, licensor_repo: Optional[LicensorRepository] = None) -> None:
        self.licensor_repo = licensor_repo or LicensorRepository()

    def register_licensor(
        self,
        licensor_name: str,
        country: str,
        licensor_id: Optional[str] = None,
        country_code: Optional[str] = None,
        is_indian: Optional[bool] = None,
        treaty_tds_pct: Optional[Decimal] = None,
        trade_name: Optional[str] = None,
        tax_id: Optional[str] = None,
        settlement_currency: str = "INR",
        iban_swift: Optional[str] = None,
        contact_email: Optional[str] = None,
    ) -> Licensor:
        """
        Registers a new licensor and their country information (Functional Req 3).
        Supports domestic (Indian) and international licensors with tax treaty information.
        """
        lid = licensor_id.strip() if licensor_id and licensor_id.strip() else f"LIC-{uuid.uuid4().hex[:6].upper()}"
        clean_name = licensor_name.strip()
        clean_country = country.strip()

        # Deduce is_indian if not explicitly supplied
        if is_indian is None:
            is_indian = clean_country.lower() in ("india", "in", "ind")

        # Deduce country_code if not supplied
        if not country_code or not country_code.strip():
            c_lower = clean_country.lower()
            if c_lower in ("india", "in", "ind"):
                cc = "IN"
            elif c_lower in ("united states", "usa", "us"):
                cc = "US"
            elif c_lower in ("united kingdom", "uk", "gb"):
                cc = "GB"
            elif c_lower in ("singapore", "sg"):
                cc = "SG"
            elif c_lower in ("uae", "united arab emirates", "ae"):
                cc = "AE"
            else:
                cc = clean_country[:3].upper()
        else:
            cc = country_code.strip().upper()

        # Validate licensor parameters
        validate_licensor_input(
            licensor_id=lid,
            licensor_name=clean_name,
            country=clean_country,
            is_indian=is_indian,
            treaty_tds_pct=treaty_tds_pct,
        )

        with get_db_session() as session:
            existing = self.licensor_repo.get_by_id(session, lid)
            if existing:
                raise ValidationError(f"Licensor with ID '{lid}' already exists.", field="licensor_id")

            licensor = Licensor(
                licensor_id=lid,
                legal_name=clean_name,
                trade_name=trade_name.strip() if trade_name and trade_name.strip() else None,
                country=clean_country,
                country_code=cc,
                is_indian=is_indian,
                treaty_tds_pct=Decimal(str(treaty_tds_pct)) if treaty_tds_pct is not None else None,
                tax_id=tax_id.strip() if tax_id and tax_id.strip() else None,
                settlement_currency=settlement_currency.strip().upper(),
                iban_swift=iban_swift.strip() if iban_swift and iban_swift.strip() else None,
                contact_email=contact_email.strip() if contact_email and contact_email.strip() else None,
                is_active=True,
            )
            self.licensor_repo.save(session, licensor)
            session.refresh(licensor)
            return licensor

    def get_licensor(self, licensor_id: str) -> Licensor:
        """Retrieves a licensor by ID."""
        with get_db_session() as session:
            lic = self.licensor_repo.get_by_id(session, licensor_id.strip())
            if not lic:
                raise EntityNotFoundError("Licensor", licensor_id)
            return lic

    def update_licensor(
        self,
        licensor_id: str,
        licensor_name: Optional[str] = None,
        country: Optional[str] = None,
        country_code: Optional[str] = None,
        is_indian: Optional[bool] = None,
        treaty_tds_pct: Optional[Decimal] = None,
        trade_name: Optional[str] = None,
        tax_id: Optional[str] = None,
        settlement_currency: Optional[str] = None,
        iban_swift: Optional[str] = None,
        contact_email: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Licensor:
        """Updates metadata and tax attributes for an existing licensor."""
        with get_db_session() as session:
            lic = self.licensor_repo.get_by_id(session, licensor_id.strip())
            if not lic:
                raise EntityNotFoundError("Licensor", licensor_id)

            if licensor_name is not None:
                if not licensor_name.strip():
                    raise ValidationError("Licensor name cannot be blank.", field="licensor_name")
                lic.legal_name = licensor_name.strip()

            if country is not None:
                if not country.strip():
                    raise ValidationError("Country cannot be blank.", field="country")
                lic.country = country.strip()

            if country_code is not None:
                lic.country_code = country_code.strip().upper()

            if is_indian is not None:
                lic.is_indian = is_indian

            if treaty_tds_pct is not None:
                dec_val = Decimal(str(treaty_tds_pct))
                if dec_val < Decimal("0.00") or dec_val > Decimal("100.00"):
                    raise ValidationError("Treaty TDS % must be between 0 and 100.", field="treaty_tds_pct")
                lic.treaty_tds_pct = dec_val

            if trade_name is not None:
                lic.trade_name = trade_name.strip() if trade_name.strip() else None

            if tax_id is not None:
                lic.tax_id = tax_id.strip() if tax_id.strip() else None

            if settlement_currency is not None:
                lic.settlement_currency = settlement_currency.strip().upper()

            if iban_swift is not None:
                lic.iban_swift = iban_swift.strip() if iban_swift.strip() else None

            if contact_email is not None:
                lic.contact_email = contact_email.strip() if contact_email.strip() else None

            if is_active is not None:
                lic.is_active = is_active

            self.licensor_repo.save(session, lic)
            session.refresh(lic)
            return lic

    def delete_licensor(self, licensor_id: str) -> bool:
        """Deletes a licensor by ID."""
        with get_db_session() as session:
            lic = self.licensor_repo.get_by_id(session, licensor_id.strip())
            if not lic:
                raise EntityNotFoundError("Licensor", licensor_id)
            return self.licensor_repo.delete(session, lic.licensor_id)

    def search_licensors(
        self,
        query: Optional[str] = None,
        country: Optional[str] = None,
        is_indian: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Licensor]:
        """Searches licensors by query string, country, or residency status."""
        with get_db_session() as session:
            return self.licensor_repo.search(
                session,
                query=query,
                country=country,
                is_indian=is_indian,
                skip=skip,
                limit=limit,
            )

    def list_licensors(self, skip: int = 0, limit: int = 100) -> List[Licensor]:
        """Returns paginated list of licensors."""
        with get_db_session() as session:
            return self.licensor_repo.get_all(session, skip=skip, limit=limit)
