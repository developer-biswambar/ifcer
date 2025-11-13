"""Certificate management endpoints for InfoCert API.

This module provides endpoints to retrieve certificate information from InfoCert,
including certificate details, status, and expiration dates.
"""

from typing import List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.services.certificate_service import CertificateService
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/certificates", tags=["certificates"])


# ============================================================================
# Response Models
# ============================================================================


class CertificateDetail(BaseModel):
    """Certificate details from InfoCert API."""

    certificate: str  # Base64-encoded certificate
    ids: List[str]  # Certificate IDs
    subject: str  # Certificate subject (DN)
    issuer: str  # Certificate issuer (DN)
    status: str  # Certificate status (active, expired, revoked, etc.)
    expiration_date: datetime  # Certificate expiration date


class CertificatesResponse(BaseModel):
    """Response containing list of certificates."""

    certificates: List[CertificateDetail]
    total_count: int


# ============================================================================
# Endpoints
# ============================================================================


@router.get("", response_model=CertificatesResponse)
async def get_certificates():
    """
    Retrieve all certificates from InfoCert API.

    This endpoint fetches certificate details from InfoCert including:
    - Certificate subject and issuer
    - Certificate status (active, expired, revoked)
    - Expiration date
    - Base64-encoded certificate data
    - Certificate IDs

    Authentication: Uses mTLS + SAT Bearer token + X-signer-id

    Returns:
        CertificatesResponse: List of certificate details

    Raises:
        HTTPException: If certificate retrieval fails
    """
    try:
        logger.info("[GET CERTIFICATES] Fetching certificates from InfoCert")

        # Initialize certificate service
        cert_service = CertificateService()

        # Fetch certificates
        certificates = cert_service.get_certificates()

        logger.info(f"[GET CERTIFICATES] ✓ Retrieved {len(certificates)} certificate(s)")

        return CertificatesResponse(
            certificates=certificates,
            total_count=len(certificates)
        )

    except Exception as e:
        logger.error(f"[GET CERTIFICATES] × Failed to retrieve certificates: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve certificates from InfoCert: {str(e)}"
        )


@router.get("/active", response_model=CertificatesResponse)
async def get_active_certificates():
    """
    Retrieve only active certificates from InfoCert API.

    This endpoint filters and returns only certificates with status='active'.

    Returns:
        CertificatesResponse: List of active certificate details

    Raises:
        HTTPException: If certificate retrieval fails
    """
    try:
        logger.info("[GET ACTIVE CERTIFICATES] Fetching active certificates from InfoCert")

        # Initialize certificate service
        cert_service = CertificateService()

        # Fetch all certificates
        all_certificates = cert_service.get_certificates()

        # Filter for active certificates
        active_certificates = [
            cert for cert in all_certificates
            if cert.get("status", "").lower() == "active"
        ]

        logger.info(
            f"[GET ACTIVE CERTIFICATES] ✓ Retrieved {len(active_certificates)} "
            f"active certificate(s) out of {len(all_certificates)} total"
        )

        return CertificatesResponse(
            certificates=active_certificates,
            total_count=len(active_certificates)
        )

    except Exception as e:
        logger.error(f"[GET ACTIVE CERTIFICATES] × Failed to retrieve active certificates: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve active certificates from InfoCert: {str(e)}"
        )
