"""Service-agnostic PaySwap economics (commission, fees, TDS, GST).

Product domains (bbps, future dmt/aeps) call settle_success only.
Importers live under economics/importers/.
"""

from domain.payswap.economics.catalogue import ensure_catalogue, list_rate_rows
from domain.payswap.economics.invoices import (
    create_monthly_invoice,
    generate_monthly_invoices,
    retailer_settlement_summary,
    revenue_report,
)
from domain.payswap.economics.policy import (
    get_or_create_service_policy,
    list_service_policies,
    serialize_service_policy,
    update_service_policy,
)
from domain.payswap.economics.settle import settle_success
from domain.payswap.economics.split import compute_economics

__all__ = [
    "settle_success",
    "compute_economics",
    "ensure_catalogue",
    "list_rate_rows",
    "get_or_create_service_policy",
    "serialize_service_policy",
    "update_service_policy",
    "list_service_policies",
    "create_monthly_invoice",
    "generate_monthly_invoices",
    "retailer_settlement_summary",
    "revenue_report",
]
