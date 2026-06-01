import streamlit as st


def main() -> None:
    st.set_page_config(page_title="Personal Finance", layout="wide")
    st.title("Personal Finance")
    st.write("Welcome to your personal finance dashboard.")


if __name__ == "__main__":
    main()
