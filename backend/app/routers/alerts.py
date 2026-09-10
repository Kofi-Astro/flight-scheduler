"""Price-drop alert endpoints (nice-to-have feature).

    GET    /api/alerts               list
    POST   /api/alerts               create (computes a baseline price)
    GET    /api/alerts/{id}          one
    POST   /api/alerts/{id}/pause    deactivate
    POST   /api/alerts/{id}/resume   reactivate
    DELETE /api/alerts/{id}          delete
    POST   /api/alerts/check         re-price all alerts, fire matches (CRON)

``/check`` is protected by the ``X-Cron-Secret`` header when
``ALERTS_CRON_SECRET`` is set, so you can safely call it from a Railway cron.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.alerts import Alert, AlertCheckResult, AlertCreate
from app.services import alert_service
from app.storage.db import get_session

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[Alert], summary="List alerts")
def list_alerts(db: Session = Depends(get_session)) -> list[Alert]:
    return alert_service.list_alerts(db)


@router.post("", response_model=Alert, status_code=201, summary="Create an alert")
async def create_alert(payload: AlertCreate, db: Session = Depends(get_session)) -> Alert:
    try:
        return await alert_service.create(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{alert_id}", response_model=Alert, summary="Get an alert")
def get_alert(alert_id: int, db: Session = Depends(get_session)) -> Alert:
    alert = alert_service.get(db, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("/{alert_id}/pause", response_model=Alert, summary="Pause an alert")
def pause_alert(alert_id: int, db: Session = Depends(get_session)) -> Alert:
    alert = alert_service.set_active(db, alert_id, False)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("/{alert_id}/resume", response_model=Alert, summary="Resume an alert")
def resume_alert(alert_id: int, db: Session = Depends(get_session)) -> Alert:
    alert = alert_service.set_active(db, alert_id, True)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.delete("/{alert_id}", summary="Delete an alert")
def delete_alert(alert_id: int, db: Session = Depends(get_session)) -> dict:
    if not alert_service.delete(db, alert_id):
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"deleted": alert_id}


@router.post("/check", response_model=AlertCheckResult, summary="Run the alert checker (cron)")
async def check_alerts(
    x_cron_secret: str | None = Header(default=None),
    db: Session = Depends(get_session),
) -> AlertCheckResult:
    """Re-price every active alert and fire the ones at/below target.

    Point a Railway Cron service at this endpoint (see DEPLOYMENT.md). When
    ``ALERTS_CRON_SECRET`` is configured it must be sent as ``X-Cron-Secret``.
    """
    secret = get_settings().alerts_cron_secret
    if secret and x_cron_secret != secret:
        raise HTTPException(status_code=401, detail="Bad or missing X-Cron-Secret")
    return await alert_service.check_all(db)
