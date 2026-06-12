from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st

from finances.models.transfer import Transfer
from finances.services.transfer_service import detect_transfers, get_all_transfers


def _txn_date(t: Transfer) -> date | None:
    if t.source_transaction:
        return t.source_transaction.date
    if t.destination_transaction:
        return t.destination_transaction.date
    return None


def _txn_amount(t: Transfer) -> Decimal:
    if t.source_transaction:
        return abs(t.source_transaction.amount)
    if t.destination_transaction:
        return t.destination_transaction.amount
    return Decimal("0")


def _txn_currency(t: Transfer) -> str:
    txn = t.source_transaction or t.destination_transaction
    return txn.currency if txn else "MXN"


def _txn_spei_key(t: Transfer) -> str | None:
    if t.source_transaction and t.source_transaction.spei_tracking_key:
        return t.source_transaction.spei_tracking_key
    if t.destination_transaction and t.destination_transaction.spei_tracking_key:
        return t.destination_transaction.spei_tracking_key
    return None


def render() -> None:
    st.title("Transfers")

    with st.spinner("Detecting transfers…"):
        touched = detect_transfers()

    if touched:
        st.success(f"{touched} transfer record(s) created or updated.")

    transfers = get_all_transfers()

    if not transfers:
        st.info("No transfers found. Import statements from Nu and Mercado Pago first.")
        return

    rows = []
    for t in transfers:
        src_counterpart = (
            t.source_transaction.counterpart_identifier if t.source_transaction else None
        )
        dst_counterpart = (
            t.destination_transaction.counterpart_identifier if t.destination_transaction else None
        )
        from_account = t.source_transaction.account if t.source_transaction else None
        to_account = t.destination_transaction.account if t.destination_transaction else None

        from_label = (
            f"{from_account.alias} ({from_account.bank})"
            if from_account
            else src_counterpart or "—"
        )
        to_label = (
            f"{to_account.alias} ({to_account.bank})" if to_account else dst_counterpart or "—"
        )
        src_desc = t.source_transaction.description if t.source_transaction else "—"
        dst_desc = t.destination_transaction.description if t.destination_transaction else "—"
        linked = t.source_transaction_id is not None and t.destination_transaction_id is not None

        rows.append(
            {
                "Date": _txn_date(t),
                "Amount": float(_txn_amount(t)),
                "Currency": _txn_currency(t),
                "Type": t.transfer_type,
                "From": from_label,
                "To": to_label,
                "Source description": src_desc,
                "Dest description": dst_desc,
                "SPEI key": _txn_spei_key(t) or "—",
                "Linked": "✓" if linked else "·",
            }
        )

    df = pd.DataFrame(rows)

    col1, col2, col3 = st.columns(3)
    linked_count = sum(1 for r in rows if r["Linked"] == "✓")
    col1.metric("Total", len(rows))
    col2.metric("Fully linked", linked_count)
    col3.metric("Partial", len(rows) - linked_count)

    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config={
            "Amount": st.column_config.NumberColumn(format="$%.2f"),
            "Date": st.column_config.DateColumn(),
        },
    )
