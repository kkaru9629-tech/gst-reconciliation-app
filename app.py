import streamlit as st
import pandas as pd
import io
from reconciliation_engine import parse_tally, parse_gstr2b, reconcile

st.set_page_config(page_title="GST Reconciliation", layout="wide")

st.title("GST Reconciliation Application")
st.markdown("Upload Purchase Register (Tally) and GSTR-2B Excel files.")

# ---------------- FILE UPLOAD ---------------- #

col1, col2 = st.columns(2)

with col1:
    tally_file = st.file_uploader(
        "Upload Tally Purchase Register",
        type=["xlsx", "xls", "csv"]
    )

with col2:
    gstr2b_file = st.file_uploader(
        "Upload GSTR-2B",
        type=["xlsx", "xls", "csv"]
    )


# ---------------- RUN RECONCILIATION ---------------- #

if st.button("Run Reconciliation", type="primary", use_container_width=True):

    # ✅ SAFE CHECK
    if tally_file is None or gstr2b_file is None:
        st.error("Please upload both files.")
    else:
        try:
            with st.spinner("Processing files..."):

                # ✅ SAFE FILE READ
                if tally_file.name.lower().endswith(".csv"):
                    tally_raw = pd.read_csv(tally_file)
                else:
                    tally_raw = pd.read_excel(tally_file)

                if gstr2b_file.name.lower().endswith(".csv"):
                    gstr2b_raw = pd.read_csv(gstr2b_file)
                else:
                    gstr2b_raw = pd.read_excel(gstr2b_file)

                # Parse data
                tally_clean = parse_tally(tally_raw)
                gstr2b_clean = parse_gstr2b(gstr2b_raw)

                # Reconcile
                results = reconcile(gstr2b_clean, tally_clean)

                st.session_state["results"] = results

                st.success("Reconciliation Completed Successfully.")

        except Exception as e:
            st.error(f"Error occurred: {str(e)}")


# ---------------- DISPLAY RESULTS ---------------- #

if "results" in st.session_state:

    results = st.session_state["results"]

    st.header("Summary")

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Books", results["summary"]["Total_Invoices_Books"])
    col2.metric("2B", results["summary"]["Total_Invoices_2B"])
    col3.metric("Matched", results["summary"]["Total_Matched"])
    col4.metric("Missing in Books", results["summary"]["Total_Missing_Books"])
    col5.metric("Missing in 2B", results["summary"]["Total_Missing_2B"])

    st.markdown("---")

    col1, col2, col3 = st.columns(3)

    col1.metric("ITC (Books)", f"₹{results['summary']['Total_ITC_Books']:,.2f}")
    col2.metric("ITC (2B)", f"₹{results['summary']['Total_ITC_2B']:,.2f}")
    col3.metric("ITC Difference", f"₹{results['summary']['ITC_Difference']:,.2f}")

    st.markdown("---")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Fully Matched",
        "Missing in Books",
        "Missing in 2B",
        "Value Mismatch",
        "Tax Mismatch"
    ])

    # ✅ SAFELY DISPLAY DATAFRAMES

    with tab1:
        if not results["fully_matched"].empty:
            st.dataframe(results["fully_matched"], use_container_width=True)
        else:
            st.info("No fully matched invoices.")

    with tab2:
        if not results["missing_in_books"].empty:
            st.dataframe(results["missing_in_books"], use_container_width=True)
        else:
            st.info("No invoices missing in books.")

    with tab3:
        if not results["missing_in_2b"].empty:
            st.dataframe(results["missing_in_2b"], use_container_width=True)
        else:
            st.info("No invoices missing in 2B.")

    with tab4:
        if not results["value_mismatch"].empty:
            st.dataframe(results["value_mismatch"], use_container_width=True)
        else:
            st.info("No value mismatches.")

    with tab5:
        if not results["tax_mismatch"].empty:
            st.dataframe(results["tax_mismatch"], use_container_width=True)
        else:
            st.info("No tax mismatches.")

    st.markdown("---")

    # ---------------- DOWNLOAD REPORT ---------------- #

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:

        pd.DataFrame([results["summary"]]).T.to_excel(
            writer,
            sheet_name="Summary"
        )

        results["fully_matched"].to_excel(
            writer,
            sheet_name="Fully Matched",
            index=False
        )

        results["missing_in_books"].to_excel(
            writer,
            sheet_name="Missing in Books",
            index=False
        )

        results["missing_in_2b"].to_excel(
            writer,
            sheet_name="Missing in 2B",
            index=False
        )

        results["value_mismatch"].to_excel(
            writer,
            sheet_name="Value Mismatch",
            index=False
        )

        results["tax_mismatch"].to_excel(
            writer,
            sheet_name="Tax Mismatch",
            index=False
        )

    output.seek(0)

    st.download_button(
        label="Download Excel Report",
        data=output,
        file_name="gst_reconciliation_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
