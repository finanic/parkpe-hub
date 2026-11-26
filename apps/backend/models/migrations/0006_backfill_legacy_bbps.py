from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation

from django.db import migrations


def _to_paise(amount_val) -> int:
    try:
        return max(0, int((Decimal(str(amount_val or "0")) * 100).quantize(Decimal("1"))))
    except (InvalidOperation, ValueError, TypeError):
        return 0


def _json_after_header(text: str) -> dict:
    if not text:
        return {}
    idx = text.find("{")
    if idx < 0:
        return {}
    try:
        parsed = json.loads(text[idx:])
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def backfill_legacy_bbps(apps, schema_editor):
    IdempotencyRecord = apps.get_model("hub_models", "IdempotencyRecord")
    BbpsTransaction = apps.get_model("hub_models", "BbpsTransaction")
    HubAction = apps.get_model("hub_models", "HubAction")

    for rec in IdempotencyRecord.objects.filter(
        app_context="payswap",
        endpoint="/api/v1/payswap/bbps/pay",
        state="done",
    ).order_by("created_at"):
        body = rec.body if isinstance(rec.body, dict) else {}
        ref = str(body.get("reference") or "").strip()
        if not ref or BbpsTransaction.objects.filter(reference=ref).exists():
            continue

        state = str(body.get("state") or "pending").lower()
        vendor_status = str(body.get("vendor_status") or "")
        vendor_txn_id = str(body.get("transaction_id") or "")

        for act in HubAction.objects.filter(target_id=ref).order_by("id"):
            payload = _json_after_header(act.response or "")
            if act.action == "integration.bbps.pay" and payload.get("success") and isinstance(payload.get("data"), dict):
                d = payload["data"]
                if d.get("txId"):
                    vendor_txn_id = str(d["txId"])
                if str(d.get("status") or "").upper() == "SUCCESS":
                    state = "success"
                    vendor_status = "SUCCESS"
            elif act.action == "integration.bbps.status" and payload.get("success") and isinstance(payload.get("data"), dict):
                d = payload["data"]
                if d.get("mobikwikrefno"):
                    vendor_txn_id = str(d["mobikwikrefno"])
                tx_st = str(d.get("txStatus") or "").upper()
                if tx_st in {"RECHARGESUCCESS", "SUCCESS"}:
                    state = "success"
                    vendor_status = tx_st
                elif tx_st in {"RECHARGEFAILURE", "FAILURE", "FAILED"}:
                    state = "failed"
                    vendor_status = tx_st
            elif act.action == "payswap.bbps.status":
                if payload.get("state") in {"success", "failed", "pending"}:
                    st = payload["state"]
                    if st != "pending" or state == "pending":
                        state = st
                if payload.get("vendor_status") and payload.get("vendor_status") != "UNKNOWN":
                    vendor_status = str(payload["vendor_status"])

        if state not in {"success", "pending", "failed"}:
            state = "pending"

        obj = BbpsTransaction.objects.create(
            reference=ref,
            user_id=str(rec.user_id or "").strip().lower(),
            operator_id=str(body.get("operator_id") or ""),
            biller_name=str(body.get("biller") or body.get("operator_id") or "BBPS"),
            account_mask=str(body.get("account") or ""),
            amount_paise=_to_paise(body.get("amount")),
            payment_channel="wallet",
            payment_mode=str(body.get("payment_mode") or "Cash"),
            state=state,
            vendor_status=vendor_status,
            vendor_txn_id=vendor_txn_id[:80],
            idempotency_key=str(rec.idempotency_key or "")[:200],
        )
        BbpsTransaction.objects.filter(pk=obj.pk).update(created_at=rec.created_at)


class Migration(migrations.Migration):

    dependencies = [
        ("hub_models", "0005_bbpstransaction_defaultservicepolicy_pgorder_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_legacy_bbps, migrations.RunPython.noop),
    ]
