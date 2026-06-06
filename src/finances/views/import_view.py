import hashlib
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from finances.schemas.import_schemas import ImportError, ImportResult, ParsedPdfData
from finances.services.import_service import (
    get_existing_account,
    get_statement_transactions,
    import_parsed,
    parse_pdf,
)

_SESSION_KEY = "parsed_pdf"


def _get_cached(file_hash: str) -> ParsedPdfData | None:
    """Return the cached ParsedPdfData if it matches the current file hash."""
    cached: ParsedPdfData | None = st.session_state.get(_SESSION_KEY)
    if cached and cached.file_hash == file_hash:
        return cached
    return None


def _clabe_input(parsed: ParsedPdfData) -> str | None:
    """Render CLABE input for banks that don't print it in their statements."""
    existing = get_existing_account(parsed.bank, parsed.account_type)
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
        st.session_state.pop(_SESSION_KEY, None)
        return

    # Compute hash from the uploaded bytes to detect file changes without re-parsing
    raw_bytes = uploaded.read()
    file_hash = hashlib.md5(raw_bytes).hexdigest()

    parsed = _get_cached(file_hash)
    if parsed is None:
        # First time seeing this file — write to temp and parse once
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp_path = Path(tmp.name)

        with st.spinner("Reading PDF…"):
            result = parse_pdf(tmp_path)
            tmp_path.unlink(missing_ok=True)

        if isinstance(result, ImportError):
            st.error(f"Could not read PDF: {result.reason}")
            return

        parsed = result
        st.session_state[_SESSION_KEY] = parsed

    st.info(f"Detected bank: **{parsed.bank_label}**")

    clabe = _clabe_input(parsed) if parsed.needs_clabe else None
    if parsed.needs_clabe and not clabe:
        st.warning("Provide the CLABE to continue.")
        return

    if st.button("Import", type="primary"):
        # Write to temp again only for archiving — no re-parse
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(raw_bytes)
            source_path = Path(tmp.name)

        with st.spinner("Importing…"):
            import_result = import_parsed(parsed, source_path, clabe_override=clabe)
        source_path.unlink(missing_ok=True)

        if isinstance(import_result, ImportError):
            st.error(f"Import failed: {import_result.reason}")
            return

        assert isinstance(import_result, ImportResult)
        st.success("Import complete!")
        st.session_state.pop(_SESSION_KEY, None)

        col1, col2, col3 = st.columns(3)
        col1.metric("Transactions", import_result.transactions_inserted)
        col2.metric("Pocket movements", import_result.pocket_movements_inserted)
        col3.metric("PDF archived", import_result.pdf_stored_path.name)
        st.caption(f"Stored at: `{import_result.pdf_stored_path}`")

        _show_transactions(import_result.statement_id)


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
