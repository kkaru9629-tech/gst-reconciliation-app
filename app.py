import streamlit as st
import pandas as pd
import io
from reconciliation_engine import parse_tally, parse_gstr2b, reconcile

st.set_page_config(page_title="GST Reconciliation", layout="wide")

st.title("GST Reconciliation Application")

col1, col2 = st.columns(2)

with col1:
    tally_file = st.file_uploader("Upload Tally Purchase Register", type=["xlsx", "xls", "csv"])

with col2:
    gstr2b_file = st.file_uploader("Upload GSTR-2B", type=["xlsx", "xls", "csv"])


if st.button("Run Reconciliation"):

    if tally_file is None or gstr2b_file is None:
        st.error("Please upload both files.")
    else:
        try:
            if tally_file.name.endswith("csv"):
                tally_raw = pd.read_csv(tally_file)
            else:
                tally_raw = pd.read_excel(tally_file)

            if gstr2b_file.name.endswith("csv"):
                gstr2b_raw = pd.read_csv(gstr2b_file)
            else:
                gstr2b_raw = pd.read_excel(gstr2b_file)

            tally_clean = parse_tally(tally_raw)
            gstr2b_clean = parse_gstr2b(gstr2b_raw)

            results = reconcile(gstr2b_clean, tally_clean)
            st.session_state["results"] = results
            st.success("Reconciliation Completed Successfully.")

        except Exception as e:
            st.error(f"Error: {str(e)}")


if "results" in st.session_state:

    results = st.session_state["results"]

    st.header("Summary")

    st.write(results["summary"])

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Fully Matched",
        "Missing in Books",
        "Missing in 2B",
        "Value Mismatch",
        "Tax Mismatch"
    ])

    with tab1:
        if not results["fully_matched"].empty:
            st.dataframe(results["fully_matched"])
        else:
            st.info("No fully matched invoices.")

    with tab2:
        if not results["missing_in_books"].empty:
            st.dataframe(results["missing_in_books"])
        else:
            st.info("No missing in books.")

    with tab3:
        if not results["missing_in_2b"].empty:
            st.dataframe(results["missing_in_2b"])
        else:
            st.info("No missing in 2B.")

    with tab4:
        if not results["value_mismatch"].empty:
            st.dataframe(results["value_mismatch"])
        else:
            st.info("No value mismatch.")

    with tab5:
        if not results["tax_mismatch"].empty:
            st.dataframe(results["tax_mismatch"])
        else:
            st.info("No tax mismatch.")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        pd.DataFrame([results["summary"]]).T.to_excel(writer, sheet_name="Summary")
        results["fully_matched"].to_excel(writer, sheet_name="Fully Matched", index=False)
        results["missing_in_books"].to_excel(writer, sheet_name="Missing in Books", index=False)
        results["missing_in_2b"].to_excel(writer, sheet_name="Missing in 2B", index=False)
        results["value_mismatch"].to_excel(writer, sheet_name="Value Mismatch", index=False)
        results["tax_mismatch"].to_excel(writer, sheet_name="Tax Mismatch", index=False)

    output.seek(0)

    st.download_button(
        label="Download Excel Report",
        data=output,
        file_name="gst_reconciliation_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
