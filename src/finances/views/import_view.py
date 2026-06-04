import tempfile
from pathlib import Path

import streamlit as st

from finances.core.database import SessionLocal
from finances.models.account import Account
from finances.services.import_service import ImportError, ImportResult, import_pdf


def _clabe_input(bank: str) -> str | None:
    """Show CLABE input only for banks that don't print it in their statements."""
    if bank != "mercadopago":
        return None

    st.info(
        "MercadoPago statements do not include the CLABE. "
        "Enter it below — it can be found in your Nu Débito SPEI deposit history."
    )

    existing = _existing_mp_clabe()
    if existing:
        st.success(f"Existing MercadoPago account found — CLABE: `{existing}`")
        use_existing = st.checkbox("Use existing CLABE", value=True)
        if use_existing:
            return existing

    clabe = st.text_input("CLABE (18 digits)", max_chars=18, placeholder="722969XXXXXXXXXXXX")
    if clabe and (not clabe.isdigit() or len(clabe) != 18):
        st.error("CLABE must be exactly 18 digits.")
        return None
    return clabe or None


def _existing_mp_clabe() -> str | None:
    """Return the CLABE of an existing MercadoPago account if one is already in the DB."""
    db = SessionLocal()
    try:
        account = db.query(Account).filter_by(bank="mercadopago", account_type="debit").first()
        return account.clabe if account else None
    finally:
        db.close()


def _detect_bank(path: Path) -> str | None:
    """Run bank detection and return the bank name, or None on failure."""
    from finances.parsers.detector import detect_bank_and_type

    try:
        bank, _ = detect_bank_and_type(path)
        return bank
    except ValueError:
        return None


def render() -> None:
    st.header("Import Statement")
    st.write("Upload a PDF bank statement to import its transactions into the database.")

    uploaded = st.file_uploader("Select PDF", type=["pdf"])

    if not uploaded:
        return

    # Write to a temp file so pdfplumber can open it by path
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(uploaded.read())
        tmp_path = Path(tmp.name)

    # Detect bank early so we can ask for CLABE if needed
    bank = _detect_bank(tmp_path)
    if bank is None:
        st.error("Unrecognized PDF format. Only Nu, BBVA, Banamex and MercadoPago are supported.")
        tmp_path.unlink(missing_ok=True)
        return

    bank_labels = {
        "nu": "Nu",
        "bbva": "BBVA",
        "banamex": "Banamex",
        "mercadopago": "Mercado Pago",
    }
    st.info(f"Detected bank: **{bank_labels.get(bank, bank)}**")

    clabe = _clabe_input(bank)

    # For MP, block import until CLABE is provided
    if bank == "mercadopago" and not clabe:
        st.warning("Provide the CLABE to continue.")
        tmp_path.unlink(missing_ok=True)
        return

    if st.button("Import", type="primary"):
        with st.spinner("Importing…"):
            db = SessionLocal()
            try:
                result = import_pdf(db, tmp_path, clabe_override=clabe)
            finally:
                db.close()
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

        _show_transactions(result.statement.id)


def _show_transactions(statement_id: int) -> None:
    import pandas as pd

    from finances.core.database import SessionLocal
    from finances.models.transaction import Transaction

    db = SessionLocal()
    try:
        txns = (
            db.query(Transaction)
            .filter_by(statement_id=statement_id)
            .order_by(Transaction.date)
            .all()
        )
    finally:
        db.close()

    if not txns:
        return

    st.subheader("Imported transactions")
    rows = [
        {
            "Date": t.date,
            "Description": t.description,
            "Amount (MXN)": float(t.amount),
            "Type": t.transaction_type,
            "Reference": t.bank_reference or "",
        }
        for t in txns
    ]
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
