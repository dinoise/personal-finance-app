import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from finances.services.import_service import (
    ImportError,
    ImportResult,
    detect_bank_label,
    get_existing_account,
    get_statement_transactions,
    import_pdf,
    needs_clabe,
)


def _clabe_input(path: Path, bank_raw: str) -> str | None:
    """Render CLABE input for banks that don't print it in their statements."""
    if not needs_clabe(path):
        return None

    existing = get_existing_account(bank_raw, "debit")
    if existing:
        clabe_str, alias = existing
        st.success(f"Existing account found — **{alias}** · CLABE: `{clabe_str}`")
        if st.checkbox("Use existing CLABE", value=True):
            return clabe_str

    st.info("MercadoPago statements do not include the CLABE. Enter it below.")
    clabe = st.text_input("CLABE (18 digits)", max_chars=18, placeholder="722969XXXXXXXXXXXX")
    if clabe and (not clabe.isdigit() or len(clabe) != 18):
        st.error("CLABE must be exactly 18 digits.")
        return None
    return clabe or None


def render() -> None:
    st.header("Import Statement")
    st.write("Upload a PDF bank statement to import its transactions into the database.")

    uploaded = st.file_uploader("Select PDF", type=["pdf"])
    if not uploaded:
        return

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(uploaded.read())
        tmp_path = Path(tmp.name)

    bank_label = detect_bank_label(tmp_path)
    if bank_label is None:
        st.error("Unrecognized PDF. Only Nu, BBVA, Banamex and MercadoPago are supported.")
        tmp_path.unlink(missing_ok=True)
        return

    st.info(f"Detected bank: **{bank_label}**")

    _label_to_key = {
        "Nu": "nu",
        "BBVA": "bbva",
        "Banamex": "banamex",
        "Mercado Pago": "mercadopago",
    }
    bank_raw = _label_to_key.get(bank_label, bank_label.lower())

    clabe = _clabe_input(tmp_path, bank_raw)
    if needs_clabe(tmp_path) and not clabe:
        st.warning("Provide the CLABE to continue.")
        tmp_path.unlink(missing_ok=True)
        return

    if st.button("Import", type="primary"):
        with st.spinner("Importing…"):
            result = import_pdf(tmp_path, clabe_override=clabe)
        tmp_path.unlink(missing_ok=True)

        if isinstance(result, ImportError):
            st.error(f"Import failed: {result.reason}")
            return

        assert isinstance(result, ImportResult)
        st.success("Import complete!")

        col1, col2, col3 = st.columns(3)
        col1.metric("Transactions", result.transactions_inserted)
        col2.metric("Pocket movements", result.pocket_movements_inserted)
        col3.metric("PDF archived", result.pdf_stored_path.name)
        st.caption(f"Stored at: `{result.pdf_stored_path}`")

        _show_transactions(result.statement_id)


def _show_transactions(statement_id: int) -> None:
    txns = get_statement_transactions(statement_id)
    if not txns:
        return

    st.subheader("Imported transactions")
    df = pd.DataFrame(
        [
            {
                "Date": t.date,
                "Description": t.description,
                "Amount (MXN)": float(t.amount),
                "Type": t.transaction_type,
                "Reference": t.bank_reference or "",
            }
            for t in txns
        ]
    )
    st.dataframe(df, width="stretch", hide_index=True)
