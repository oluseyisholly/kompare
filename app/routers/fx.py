from fastapi import APIRouter, Body, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import require_admin
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.fx import (
    Currency,
    FxConversionRead,
    FxConversionRequest,
    FxCurrencyRead,
    FxQuoteRead,
    FxQuoteRequest,
    FxStoredRateRead,
)
from app.services.fx import FxService
from app.services.ingestion.fx import FxDiagnosticService

router = APIRouter(prefix="/fx", tags=["FX"])


def get_fx_service(db: Session = Depends(get_db)):
    return FxService(db)


def get_fx_diagnostic_service(db: Session = Depends(get_db)):
    return FxDiagnosticService(db)


@router.post(
    "/convert",
    response_model=ApiResponse[FxConversionRead],
    summary="Estimate a conversion using stored provider data",
    description="All providers use provider, source_currency, target_currency and source_amount. "
    "Legacy rate_side inputs are rejected with 422. No provider calls occur. "
    "Fincra uses a disclosed temporary assumption: provider buys/sells the base currency, "
    "priced in quote units per base unit; confirmation is pending.",
)
def convert(
    request: FxConversionRequest = Body(
        openapi_examples={
            example["provider"]: {
                "summary": f"Stored {example['provider']} conversion",
                "value": example,
            }
            for example in FxConversionRequest.model_config["json_schema_extra"]["examples"]
        }
    ),
    service: FxService = Depends(get_fx_service),
):
    return service.convert(request)


@router.get("/{provider}/rates", response_model=ApiResponse[PaginatedData[FxStoredRateRead]])
def list_rates(
    provider: str = Path(pattern=r"^[a-z][a-z0-9_]{0,63}$", examples=["wise"]),
    source: Currency | None = Query(default=None, examples=["USD"]),
    target: Currency | None = Query(default=None, examples=["NGN"]),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: FxService = Depends(get_fx_service),
):
    return service.list_rates(provider, source=source, target=target, page=page, per_page=per_page)


@router.get(
    "/{provider}/currencies",
    response_model=ApiResponse[PaginatedData[FxCurrencyRead]],
    description="Active currency discovery only; inclusion does not guarantee support "
    "for every conversion direction.",
)
def list_currencies(
    provider: str = Path(pattern=r"^[a-z][a-z0-9_]{0,63}$", examples=["wise"]),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: FxService = Depends(get_fx_service),
):
    return service.list_currencies(provider, page=page, per_page=per_page)


@router.post(
    "/{provider}/quotes",
    response_model=ApiResponse[FxQuoteRead],
    dependencies=[Depends(require_admin)],
    summary="Admin diagnostic: harvest an amount-specific historical observation",
    description="Currently implemented for Wise only. Supply exactly one of source_amount "
    "or target_amount. This diagnostic contacts the provider; it is not an executable quote.",
)
async def illustrative_quote(
    request: FxQuoteRequest = Body(
        openapi_examples={
            ("source_amount" if "source_amount" in example else "target_amount"): {
                "summary": "Specify the source amount"
                if "source_amount" in example
                else "Specify the target amount",
                "value": example,
            }
            for example in FxQuoteRequest.model_config["json_schema_extra"]["examples"]
        }
    ),
    provider: str = Path(pattern=r"^[a-z][a-z0-9_]{0,63}$", examples=["wise"]),
    service: FxDiagnosticService = Depends(get_fx_diagnostic_service),
):
    return await service.request_quote(provider, request)
