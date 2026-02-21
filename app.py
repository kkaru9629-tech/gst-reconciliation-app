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

    # -------- MONTH FILTER (for multi-month data) -------- #
    if not results['fully_matched'].empty and 'Invoice_Date_2B' in results['fully_matched'].columns:
        available_months = results['fully_matched']['Invoice_Date_2B'].dt.to_period("M").astype(str).unique()
        
        if len(available_months) > 0:
            month_options = ["All Months"] + sorted(available_months)
            selected_month = st.selectbox("📅 Filter by Month", month_options)
            
            if selected_month != "All Months":
                for key in ['fully_matched', 'missing_in_books', 'missing_in_2b', 'value_mismatch', 'tax_mismatch']:
                    if key in results and not results[key].empty:
                        df = results[key]
                        
                        # Handle different date column names
                        if 'Invoice_Date_2B' in df.columns:
                            date_col = 'Invoice_Date_2B'
                        elif 'Invoice_Date_Tally' in df.columns:
                            date_col = 'Invoice_Date_Tally'
                        elif 'Invoice_Date' in df.columns:
                            date_col = 'Invoice_Date'
                        else:
                            continue
                            
                        results[key] = df[df[date_col].dt.to_period("M").astype(str) == selected_month]

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
        "✅ Fully Matched",
        "❌ Missing in Books",
        "⚠️ Missing in 2B",
        "💰 Value Mismatch",
        "💸 Tax Mismatch"
    ])

    # -------- FULLY MATCHED -------- #
    with tab1:
        st.subheader("Fully Matched Invoices")

        if not results['fully_matched'].empty:
            df = results['fully_matched'].copy()
            
            # Select and rename columns for display
            display_cols = []
            if 'GSTIN_2B' in df.columns:
                display_cols.extend(['GSTIN_2B', 'Trade_Name_2B' if 'Trade_Name_2B' in df.columns else 'GSTIN_2B'])
                display_cols.extend(['Invoice_No_2B', 'Invoice_Date_2B', 'Taxable_Value_2B', 'TOTAL_TAX_2B'])
                
                df_display = df[display_cols].copy()
                df_display.columns = ['GSTIN', 'Trade Name', 'Invoice No', 'Date', 'Taxable Value', 'Total Tax']
            else:
                df_display = df[['GSTIN', 'Trade_Name', 'Invoice_No', 'Invoice_Date', 'Taxable_Value', 'TOTAL_TAX']].copy()
                df_display.columns = ['GSTIN', 'Trade Name', 'Invoice No', 'Date', 'Taxable Value', 'Total Tax']
            
            # Format date
            if 'Date' in df_display.columns:
                df_display['Date'] = df_display['Date'].dt.strftime('%d-%b-%Y')
            
            st.dataframe(df_display, use_container_width=True)
            st.write(f"**Total:** {len(df_display)} invoices")
        else:
            st.info("No fully matched invoices found.")

    # -------- MISSING IN BOOKS -------- #
    with tab2:
        st.subheader("Missing in Books (Present in 2B)")

        df = results["missing_in_books"]
        if not df.empty:
            display_cols = ['GSTIN', 'Trade_Name', 'Invoice_No', 'Invoice_Date', 'Taxable_Value', 'TOTAL_TAX']
            display_cols = [c for c in display_cols if c in df.columns]
            
            df_display = df[display_cols].copy()
            if 'Invoice_Date' in df_display.columns:
                df_display['Invoice_Date'] = df_display['Invoice_Date'].dt.strftime('%d-%b-%Y')
            
            st.dataframe(df_display, use_container_width=True)
            st.write(f"**Total:** {len(df_display)} invoices")
        else:
            st.info("No invoices missing in books.")

    # -------- MISSING IN 2B -------- #
    with tab3:
        st.subheader("Missing in 2B (Present in Books)")

        df = results["missing_in_2b"]
        if not df.empty:
            display_cols = ['GSTIN', 'Trade_Name', 'Invoice_No', 'Invoice_Date', 'Taxable_Value', 'TOTAL_TAX']
            display_cols = [c for c in display_cols if c in df.columns]
            
            df_display = df[display_cols].copy()
            if 'Invoice_Date' in df_display.columns:
                df_display['Invoice_Date'] = df_display['Invoice_Date'].dt.strftime('%d-%b-%Y')
            
            st.dataframe(df_display, use_container_width=True)
            st.write(f"**Total:** {len(df_display)} invoices")
        else:
            st.info("No invoices missing in 2B.")

    # -------- VALUE MISMATCH -------- #
    with tab4:
        st.subheader("Taxable Value Mismatch")

        df = results["value_mismatch"]
        if not df.empty:
            display_cols = []
            if 'GSTIN_2B' in df.columns:
                display_cols = ['GSTIN_2B', 'Trade_Name_2B' if 'Trade_Name_2B' in df.columns else 'GSTIN_2B', 
                               'Invoice_No_2B', 'Taxable_Value_2B', 'Taxable_Value_Tally', 'Difference_Value']
                
                df_display = df[display_cols].copy()
                df_display.columns = ['GSTIN', 'Trade Name', 'Invoice No', '2B Value', 'Tally Value', 'Difference']
            else:
                st.dataframe(df, use_container_width=True)
            
            st.dataframe(df_display, use_container_width=True)
            st.write(f"**Total:** {len(df_display)} invoices")
        else:
            st.info("No value mismatches found.")

    # -------- TAX MISMATCH -------- #
    with tab5:
        st.subheader("Tax Amount Mismatch")

        df = results["tax_mismatch"]
        if not df.empty:
            display_cols = []
            if 'GSTIN_2B' in df.columns:
                display_cols = ['GSTIN_2B', 'Trade_Name_2B' if 'Trade_Name_2B' in df.columns else 'GSTIN_2B',
                               'Invoice_No_2B', 'TOTAL_TAX_2B', 'TOTAL_TAX_Tally', 'Difference_Tax']
                
                df_display = df[display_cols].copy()
                df_display.columns = ['GSTIN', 'Trade Name', 'Invoice No', '2B Tax', 'Tally Tax', 'Difference']
            else:
                st.dataframe(df, use_container_width=True)
            
            st.dataframe(df_display, use_container_width=True)
            st.write(f"**Total:** {len(df_display)} invoices")
        else:
            st.info("No tax mismatches found.")

    st.markdown("---")

    # -------- DOWNLOAD REPORT (PROFESSIONAL FORMAT) -------- #

    st.header("📥 Download Professional Report")

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:

        workbook = writer.book

        # Define formats
        header_format = workbook.add_format({
            "bold": True,
            "font_name": "Times New Roman",
            "font_size": 11,
            "bg_color": "#D3D3D3",
            "border": 1,
            "align": "center",
            "valign": "vcenter"
        })

        data_format = workbook.add_format({
            "font_name": "Times New Roman",
            "font_size": 11
        })

        money_format = workbook.add_format({
            "num_format": "#,##0.00",
            "font_name": "Times New Roman",
            "font_size": 11
        })

        date_format = workbook.add_format({
            "num_format": "dd-mmm-yyyy",
            "font_name": "Times New Roman",
            "font_size": 11
        })

        def write_sheet(df, sheet_name):
            # Remove Match_Key if present
            if 'Match_Key' in df.columns:
                df = df.drop(columns=['Match_Key'])
            
            if df.empty:
                empty_df = pd.DataFrame({"Message": ["No data available"]})
                empty_df.to_excel(writer, sheet_name=sheet_name, index=False)
                worksheet = writer.sheets[sheet_name]
                worksheet.set_column(0, 0, 30, data_format)
                return
            
            df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=1)
            worksheet = writer.sheets[sheet_name]

            # Write headers with format
            for col_num, value in enumerate(df.columns):
                worksheet.write(0, col_num, value, header_format)

            # Auto-fit columns and apply formats
            for i, col in enumerate(df.columns):
                # Calculate max width
                max_length = max(
                    df[col].astype(str).map(len).max() if not df.empty else 0,
                    len(str(col))
                ) + 2
                
                # Cap at 50 characters
                max_length = min(max_length, 50)
                
                # Determine column format
                col_lower = col.lower()
                if any(term in col_lower for term in ['tax', 'value', 'amount', 'itc', 'igst', 'cgst', 'sgst']):
                    if df[col].dtype in ['float64', 'int64']:
                        worksheet.set_column(i, i, max_length, money_format)
                    else:
                        worksheet.set_column(i, i, max_length, data_format)
                elif 'date' in col_lower:
                    worksheet.set_column(i, i, max_length, date_format)
                else:
                    worksheet.set_column(i, i, max_length, data_format)

        # Write all sheets
        summary_df = pd.DataFrame([results["summary"]]).T.reset_index()
        summary_df.columns = ["Metric", "Value"]
        write_sheet(summary_df, "Summary")
        
        write_sheet(results["fully_matched"], "Fully Matched")
        write_sheet(results["missing_in_books"], "Missing in Books")
        write_sheet(results["missing_in_2b"], "Missing in 2B")

        if not results["value_mismatch"].empty:
            write_sheet(results["value_mismatch"], "Value Mismatch")

        if not results["tax_mismatch"].empty:
            write_sheet(results["tax_mismatch"], "Tax Mismatch")

        # Add a cover sheet with instructions
        cover_data = {
            "Info": [
                "GST RECONCILIATION REPORT",
                f"Generated on: {pd.Timestamp.now().strftime('%d-%b-%Y %H:%M')}",
                "",
                "SUMMARY",
                f"Total Books Invoices: {results['summary']['Total_Invoices_Books']}",
                f"Total 2B Invoices: {results['summary']['Total_Invoices_2B']}",
                f"Matched: {results['summary']['Total_Matched']}",
                f"Missing in Books: {results['summary']['Total_Missing_Books']}",
                f"Missing in 2B: {results['summary']['Total_Missing_2B']}",
                f"ITC Difference: ₹{results['summary']['ITC_Difference']:,.2f}"
            ]
        }
        cover_df = pd.DataFrame(cover_data)
        cover_df.to_excel(writer, sheet_name="Cover", index=False, header=False)
        
        cover_sheet = writer.sheets["Cover"]
        cover_sheet.set_column(0, 0, 60, data_format)

    output.seek(0)

    st.download_button(
        label="📊 Download Excel Report (Professional Format)",
        data=output,
        file_name=f"gst_reconciliation_report_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
