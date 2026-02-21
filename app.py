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
                st.success("Reconciliation Complete!")

        except Exception as e:
            st.error(f"Error: {str(e)}")

# ---------------- DISPLAY RESULTS ---------------- #

if "results" in st.session_state:

    results = st.session_state.results

    # ---------- SUMMARY ---------- #
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

    # ---------- TABS ---------- #
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Fully Matched",
        "Missing in Books",
        "Missing in 2B",
        "Value Mismatch",
        "Tax Mismatch"
    ])

    with tab1:
        df = results["fully_matched"]
        if not df.empty:
            st.dataframe(df.drop(columns=["Match_Key"], errors="ignore"), use_container_width=True)
        else:
            st.info("No fully matched invoices found.")

    with tab2:
        df = results["missing_in_books"]
        if not df.empty:
            st.dataframe(df.drop(columns=["Match_Key"], errors="ignore"), use_container_width=True)
        else:
            st.info("No invoices missing in books.")

    with tab3:
        df = results["missing_in_2b"]
        if not df.empty:
            st.dataframe(df.drop(columns=["Match_Key"], errors="ignore"), use_container_width=True)
        else:
            st.info("No invoices missing in 2B.")

    with tab4:
        df = results["value_mismatch"]
        if not df.empty:
            st.dataframe(df.drop(columns=["Match_Key"], errors="ignore"), use_container_width=True)
        else:
            st.info("No value mismatches found.")

    with tab5:
        df = results["tax_mismatch"]
        if not df.empty:
            st.dataframe(df.drop(columns=["Match_Key"], errors="ignore"), use_container_width=True)
        else:
            st.info("No tax mismatches found.")

    st.markdown("---")

    # ---------------- PROFESSIONAL DOWNLOAD ---------------- #

    st.header("Download Professional Report")

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:

        workbook = writer.book

        header_format = workbook.add_format({
            "bold": True,
            "font_name": "Times New Roman",
            "font_size": 11,
            "bg_color": "#D9D9D9",
            "border": 1,
            "align": "center"
        })

        text_format = workbook.add_format({
            "font_name": "Times New Roman",
            "font_size": 11
        })

        money_format = workbook.add_format({
            "font_name": "Times New Roman",
            "font_size": 11,
            "num_format": "#,##0.00"
        })

        date_format = workbook.add_format({
            "font_name": "Times New Roman",
            "font_size": 11,
            "num_format": "dd-mmm-yyyy"
        })

        def write_sheet(df, sheet_name):

            df = df.drop(columns=["Match_Key"], errors="ignore")

            if df.empty:
                pd.DataFrame({"Message": ["No data available"]}).to_excel(writer, sheet_name=sheet_name, index=False)
                writer.sheets[sheet_name].set_column(0, 0, 30, text_format)
                return

            df.to_excel(writer, sheet_name=sheet_name, index=False, header=False, startrow=1)
            worksheet = writer.sheets[sheet_name]

            for col_num, col_name in enumerate(df.columns):
                worksheet.write(0, col_num, col_name, header_format)

            for col_num, col_name in enumerate(df.columns):
                max_len = max(df[col_name].astype(str).map(len).max(), len(col_name)) + 2
                max_len = min(max_len, 50)

                if "date" in col_name.lower():
                    worksheet.set_column(col_num, col_num, max_len, date_format)
                elif "tax" in col_name.lower() or "value" in col_name.lower():
                    worksheet.set_column(col_num, col_num, max_len, money_format)
                else:
                    worksheet.set_column(col_num, col_num, max_len, text_format)

        # Write sheets
        summary_df = pd.DataFrame([results["summary"]]).T.reset_index()
        summary_df.columns = ["Metric", "Value"]
        write_sheet(summary_df, "Summary")

        write_sheet(results["fully_matched"], "Fully Matched")
        write_sheet(results["missing_in_books"], "Missing in Books")
        write_sheet(results["missing_in_2b"], "Missing in 2B")
        write_sheet(results["value_mismatch"], "Value Mismatch")
        write_sheet(results["tax_mismatch"], "Tax Mismatch")

        # Cover Sheet
        cover_df = pd.DataFrame({
            "GST Reconciliation Report": [
                f"Generated On: {pd.Timestamp.now().strftime('%d-%b-%Y %H:%M')}",
                "",
                f"Total Books Invoices: {results['summary']['Total_Invoices_Books']}",
                f"Total 2B Invoices: {results['summary']['Total_Invoices_2B']}",
                f"Matched: {results['summary']['Total_Matched']}",
                f"Missing in Books: {results['summary']['Total_Missing_Books']}",
                f"Missing in 2B: {results['summary']['Total_Missing_2B']}",
                f"ITC Difference: ₹{results['summary']['ITC_Difference']:,.2f}"
            ]
        })

        cover_df.to_excel(writer, sheet_name="Cover", index=False)
        writer.sheets["Cover"].set_column(0, 0, 60, text_format)

    output.seek(0)

    st.download_button(
        label="Download Excel Report",
        data=output,
        file_name=f"gst_reconciliation_report_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
