import streamlit as st
import pandas as pd
import io
from reconciliation_engine import parse_tally, parse_gstr2b, reconcile

st.set_page_config(page_title="GST Reconciliation", layout="wide")

st.title("GST Reconciliation Application")
st.markdown("Upload Purchase Register (Tally) and GSTR-2B Excel files to reconcile invoices.")

# ---------------- FILE UPLOAD ---------------- #

col1, col2 = st.columns(2)

with col1:
    st.subheader("Purchase Register (Tally)")
    tally_file = st.file_uploader("Upload Tally Excel/CSV", type=["xlsx", "xls", "csv"])

with col2:
    st.subheader("GSTR-2B")
    gstr2b_file = st.file_uploader("Upload GSTR-2B Excel/CSV", type=["xlsx", "xls", "csv"])

# ---------------- RUN RECONCILIATION ---------------- #

if st.button("Run Reconciliation", type="primary", use_container_width=True):

    if tally_file is None or gstr2b_file is None:
        st.error("Please upload both files")
    else:
        try:
            with st.spinner("Processing and reconciling..."):

                # Load files
                tally_raw = pd.read_csv(tally_file) if tally_file.name.endswith(".csv") else pd.read_excel(tally_file)
                gstr2b_raw = pd.read_csv(gstr2b_file) if gstr2b_file.name.endswith(".csv") else pd.read_excel(gstr2b_file)

                # Clean
                tally_clean = parse_tally(tally_raw)
                gstr2b_clean = parse_gstr2b(gstr2b_raw)

                # Reconcile
                results = reconcile(gstr2b_clean, tally_clean)

                st.session_state.results = results
                st.success("Reconciliation Complete!")

        except Exception as e:
            st.error(f"Error: {str(e)}")

# ---------------- DISPLAY RESULTS ---------------- #

if "results" in st.session_state:

    results = st.session_state.results

    # -------- SUMMARY -------- #
    st.header("Summary")

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Books", results['summary']['Total_Invoices_Books'])
    col2.metric("2B", results['summary']['Total_Invoices_2B'])
    col3.metric("Matched", results['summary']['Total_Matched'])
    col4.metric("Missing in Books", results['summary']['Total_Missing_Books'])
    col5.metric("Missing in 2B", results['summary']['Total_Missing_2B'])

    st.markdown("---")

    col1, col2, col3 = st.columns(3)

    col1.metric("ITC (Books)", f"₹{results['summary']['Total_ITC_Books']:,.2f}")
    col2.metric("ITC (2B)", f"₹{results['summary']['Total_ITC_2B']:,.2f}")
    diff = results['summary']['ITC_Difference']
    col3.metric("ITC Difference", f"₹{diff:,.2f}")

    st.markdown("---")

    # -------- TABS -------- #

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Fully Matched",
        "Missing in Books",
        "Missing in 2B",
        "Value Mismatch",
        "Tax Mismatch"
    ])

    # -------- FULLY MATCHED -------- #
    with tab1:
        st.subheader("Fully Matched Invoices")

        if not results['fully_matched'].empty:

            df = results['fully_matched'][[
                "GSTIN_2B",
                "Invoice_No_2B",
                "Invoice_Date_2B",
                "Taxable_Value_2B",
                "TOTAL_TAX_2B"
            ]].copy()

            df.columns = ["GSTIN", "Invoice No", "Date", "Taxable Value", "Total Tax"]
            st.dataframe(df, use_container_width=True)
            st.write(f"Total: {len(df)}")

        else:
            st.info("No fully matched invoices found.")

    # -------- MISSING IN BOOKS -------- #
    with tab2:
        st.subheader("Missing in Books (Present in 2B)")

        df = results["missing_in_books"]
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No invoices missing in books.")

    # -------- MISSING IN 2B -------- #
    with tab3:
        st.subheader("Missing in 2B (Present in Books)")

        df = results["missing_in_2b"]
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No invoices missing in 2B.")

    # -------- VALUE MISMATCH -------- #
    with tab4:
        st.subheader("Taxable Value Mismatch")

        df = results["value_mismatch"]
        if not df.empty:
            display = df[[
                "Invoice_No_2B",
                "Taxable_Value_2B",
                "Taxable_Value_Tally"
            ]]
            st.dataframe(display, use_container_width=True)
        else:
            st.info("No value mismatches found.")

    # -------- TAX MISMATCH -------- #
    with tab5:
        st.subheader("Tax Amount Mismatch")

        df = results["tax_mismatch"]
        if not df.empty:
            display = df[[
                "Invoice_No_2B",
                "TOTAL_TAX_2B",
                "TOTAL_TAX_Tally"
            ]]
            st.dataframe(display, use_container_width=True)
        else:
            st.info("No tax mismatches found.")

    st.markdown("---")

    # -------- DOWNLOAD REPORT -------- #

    st.header("Download Report")

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:

        pd.DataFrame([results["summary"]]).T.to_excel(writer, sheet_name="Summary")

        results["fully_matched"].to_excel(writer, sheet_name="Matched", index=False)
        results["missing_in_books"].to_excel(writer, sheet_name="Missing in Books", index=False)
        results["missing_in_2b"].to_excel(writer, sheet_name="Missing in 2B", index=False)

        if not results["value_mismatch"].empty:
            results["value_mismatch"].to_excel(writer, sheet_name="Value Mismatch", index=False)

        if not results["tax_mismatch"].empty:
            results["tax_mismatch"].to_excel(writer, sheet_name="Tax Mismatch", index=False)

    output.seek(0)

    st.download_button(
        label="Download Excel Report",
        data=output,
        file_name="gst_reconciliation_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
