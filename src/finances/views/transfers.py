from __future__ import annotations

import pandas as pd
import streamlit as st

from finances.services.transfer_service import detect_transfers, get_all_transfers


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
        from_label = (
            f"{t.from_account.alias} ({t.from_account.bank})"
            if t.from_account
            else t.counterpart_identifier or "—"
        )
        to_label = (
            f"{t.to_account.alias} ({t.to_account.bank})"
            if t.to_account
            else t.counterpart_identifier or "—"
        )
        src_desc = t.source_transaction.description if t.source_transaction else "—"
        dst_desc = t.destination_transaction.description if t.destination_transaction else "—"
        linked = t.source_transaction_id is not None and t.destination_transaction_id is not None

        rows.append(
            {
                "Date": t.date,
                "Amount": float(t.amount),
                "Currency": t.currency,
                "Type": t.transfer_type,
                "From": from_label,
                "To": to_label,
                "Source description": src_desc,
                "Dest description": dst_desc,
                "SPEI key": t.spei_tracking_key or "—",
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
