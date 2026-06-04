import streamlit as st


def main() -> None:
    st.set_page_config(page_title="Personal Finance", layout="wide")

    page = st.sidebar.radio(
        "Navigation",
        ["Dashboard", "Import Statement", "Transactions"],
    )

    if page == "Dashboard":
        st.title("Dashboard")
        st.info("Coming soon.")

    elif page == "Import Statement":
        from finances.views.import_view import render

        render()

    elif page == "Transactions":
        st.title("Transactions")
        st.info("Coming soon.")


if __name__ == "__main__":
    main()
