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
            with st.spinner("Processing..."):

                tally_raw = pd.read_csv(tally_file) if tally_file.name.endswith(".csv") else pd.read_excel(tally_file)
                gstr2b_raw = pd.read_csv(gstr2b_file) if gstr2b_file.name.endswith(".csv") else pd.read_excel(gstr2b_file)

                tally_clean = parse_tally(tally_raw)
                gstr2b_clean = parse_gstr2b(gstr2b_raw)

                results = reconcile(gstr2b_clean, tally_clean)

                st.session_state.results = results
                st.success("Reconciliation Completed Successfully!")

        except Exception as e:
            st.error(f"Error: {str(e)}")

# ---------------- DISPLAY RESULTS ---------------- #

if "results" in st.session_state:

    results = st.session_state.results

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
    col3.metric("ITC Difference", f"₹{results['summary']['ITC_Difference']:,.2f}")

    st.markdown("---")

    tabs = st.tabs(["Matched", "Missing in Books", "Missing in 2B", "Value Mismatch", "Tax Mismatch"])

    for tab, key in zip(tabs, ["fully_matched", "missing_in_books", "missing_in_2b", "value_mismatch", "tax_mismatch"]):
        with tab:
            df = results[key]
            if not df.empty:
                st.dataframe(df, use_container_width=True)
                st.write(f"Total: {len(df)} invoices")
            else:
                st.info("No data found.")

    # ---------------- DOWNLOAD ---------------- #

    st.header("Download Professional Report")

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:

        workbook = writer.book

        header_format = workbook.add_format({
            "bold": True,
            "font_name": "Times New Roman",
            "font_size": 11,
            "border": 1
        })

        data_format = workbook.add_format({
            "font_name": "Times New Roman",
            "font_size": 11
        })

        def write_sheet(df, sheet_name):
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            worksheet = writer.sheets[sheet_name]

            for col_num, value in enumerate(df.columns):
                worksheet.write(0, col_num, value, header_format)

            for i, col in enumerate(df.columns):
                max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.set_column(i, i, max_len, data_format)

        write_sheet(pd.DataFrame([results["summary"]]).T.reset_index(), "Summary")
        write_sheet(results["fully_matched"], "Matched")
        write_sheet(results["missing_in_books"], "Missing in Books")
        write_sheet(results["missing_in_2b"], "Missing in 2B")

        if not results["value_mismatch"].empty:
            write_sheet(results["value_mismatch"], "Value Mismatch")

        if not results["tax_mismatch"].empty:
            write_sheet(results["tax_mismatch"], "Tax Mismatch")

    output.seek(0)

    st.download_button(
        label="Download Excel Report",
        data=output,
        file_name="GST_Reconciliation_Report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
