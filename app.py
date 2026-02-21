import streamlit as st
import pandas as pd
import io
from reconciliation_engine import parse_tally, parse_gstr2b, reconcile

st.set_page_config(page_title="GST Reconciliation", layout="wide")

st.title("GST Reconciliation Application")
st.markdown("Upload Purchase Register (Tally) and GSTR-2B Excel files to reconcile invoices.")

# File uploads
col1, col2 = st.columns(2)

with col1:
    st.subheader("Purchase Register (Tally)")
    tally_file = st.file_uploader("Upload Tally Excel/CSV", type=["xlsx", "xls", "csv"], key="tally")

with col2:
    st.subheader("GSTR-2B")
    gstr2b_file = st.file_uploader("Upload GSTR-2B Excel/CSV", type=["xlsx", "xls", "csv"], key="gstr2b")

# Reconcile button
if st.button("Run Reconciliation", type="primary", use_container_width=True):
    if tally_file is None or gstr2b_file is None:
        st.error("Please upload both files")
    else:
        with st.spinner("Processing and reconciling..."):
            try:
                # Load files
                if tally_file.name.endswith('.csv'):
                    tally_raw = pd.read_csv(tally_file)
                else:
                    tally_raw = pd.read_excel(tally_file)
                
                if gstr2b_file.name.endswith('.csv'):
                    gstr2b_raw = pd.read_csv(gstr2b_file)
                else:
                    gstr2b_raw = pd.read_excel(gstr2b_file)
                
                # Parse and clean
                tally_clean = parse_tally(tally_raw)
                gstr2b_clean = parse_gstr2b(gstr2b_raw)
                
                # Reconcile
                results = reconcile(gstr2b_clean, tally_clean)
                
                st.session_state.results = results
                st.session_state.tally_clean = tally_clean
                st.session_state.gstr2b_clean = gstr2b_clean
                
                st.success("Reconciliation complete!")
                
            except Exception as e:
                st.error(f"Error: {str(e)}")

# Display results
if 'results' in st.session_state:
    results = st.session_state.results
    
    # Summary
    st.header("Summary")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Books Invoices", results['summary']['Total_Invoices_Books'])
    with col2:
        st.metric("2B Invoices", results['summary']['Total_Invoices_2B'])
    with col3:
        st.metric("Matched", results['summary']['Total_Matched'])
    with col4:
        st.metric("Missing in Books", results['summary']['Total_Missing_Books'])
    with col5:
        st.metric("Missing in 2B", results['summary']['Total_Missing_2B'])
    
    st.markdown("---")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("ITC (Books)", f"₹{results['summary']['Total_ITC_Books']:,.2f}")
    with col2:
        st.metric("ITC (2B)", f"₹{results['summary']['Total_ITC_2B']:,.2f}")
    with col3:
        diff = results['summary']['ITC_Difference']
        st.metric("ITC Difference", f"₹{diff:,.2f}", delta=f"{diff:,.2f}")
    
    st.markdown("---")
    
    # Reports
    st.header("Detailed Reports")
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Fully Matched",
        "Missing in Books",
        "Missing in 2B",
        "Value Mismatch",
        "Tax Mismatch"
    ])
    
    with tab1:
        st.subheader("Fully Matched Invoices")
        matched_display = results['fully_matched'][[
            'GSTIN', 'Invoice_No', 'Invoice_Date_2B', 'Taxable_Value_2B', 
            'IGST_2B', 'CGST_2B', 'SGST_2B', 'TOTAL_TAX_2B'
        ]].copy()
        matched_display.columns = ['GSTIN', 'Invoice No', 'Date', 'Taxable Value', 'IGST', 'CGST', 'SGST', 'Total Tax']
        st.dataframe(matched_display, use_container_width=True)
        st.write(f"Total: {len(results['fully_matched'])} invoices")
    
    with tab2:
        st.subheader("Missing in Books (Present in 2B)")
        missing_books_display = results['missing_in_books'][[
            'GSTIN', 'Invoice_No', 'Invoice_Date', 'Taxable_Value', 
            'IGST', 'CGST', 'SGST', 'TOTAL_TAX'
        ]].copy()
        missing_books_display.columns = ['GSTIN', 'Invoice No', 'Date', 'Taxable Value', 'IGST', 'CGST', 'SGST', 'Total Tax']
        st.dataframe(missing_books_display, use_container_width=True)
        st.write(f"Total: {len(results['missing_in_books'])} invoices")
    
    with tab3:
        st.subheader("Missing in 2B (Present in Books)")
        missing_2b_display = results['missing_in_2b'][[
            'GSTIN', 'Invoice_No', 'Invoice_Date', 'Taxable_Value', 
            'IGST', 'CGST', 'SGST', 'TOTAL_TAX'
        ]].copy()
        missing_2b_display.columns = ['GSTIN', 'Invoice No', 'Date', 'Taxable Value', 'IGST', 'CGST', 'SGST', 'Total Tax']
        st.dataframe(missing_2b_display, use_container_width=True)
        st.write(f"Total: {len(results['missing_in_2b'])} invoices")
    
    with tab4:
        st.subheader("Taxable Value Mismatch")
        if len(results['value_mismatch']) > 0:
            value_display = results['value_mismatch'][[
                'GSTIN', 'Invoice_No', 'Taxable_Value_2B', 'Taxable_Value_Tally', 'Taxable_Value_Diff'
            ]].copy()
            value_display.columns = ['GSTIN', 'Invoice No', 'Value (2B)', 'Value (Books)', 'Difference']
            st.dataframe(value_display, use_container_width=True)
            st.write(f"Total: {len(results['value_mismatch'])} invoices")
        else:
            st.info("No value mismatches found")
    
    with tab5:
        st.subheader("Tax Amount Mismatch")
        if len(results['tax_mismatch']) > 0:
            tax_display = results['tax_mismatch'][[
                'GSTIN', 'Invoice_No', 'IGST_2B', 'IGST_Tally', 'CGST_2B', 'CGST_Tally', 'SGST_2B', 'SGST_Tally'
            ]].copy()
            tax_display.columns = ['GSTIN', 'Invoice No', 'IGST (2B)', 'IGST (Books)', 'CGST (2B)', 'CGST (Books)', 'SGST (2B)', 'SGST (Books)']
            st.dataframe(tax_display, use_container_width=True)
            st.write(f"Total: {len(results['tax_mismatch'])} invoices")
        else:
            st.info("No tax mismatches found")
    
    st.markdown("---")
    
    # Download button
    st.header("Download Report")
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Summary sheet
        summary_df = pd.DataFrame([results['summary']]).T
        summary_df.columns = ['Value']
        summary_df.to_excel(writer, sheet_name='Summary')
        
        # Matched
        matched_export = results['fully_matched'][[
            'GSTIN', 'Invoice_No', 'Invoice_Date_2B', 'Taxable_Value_2B', 
            'IGST_2B', 'CGST_2B', 'SGST_2B', 'TOTAL_TAX_2B'
        ]].copy()
        matched_export.columns = ['GSTIN', 'Invoice No', 'Date', 'Taxable Value', 'IGST', 'CGST', 'SGST', 'Total Tax']
        matched_export.to_excel(writer, sheet_name='Matched', index=False)
        
        # Missing in Books
        missing_books_export = results['missing_in_books'][[
            'GSTIN', 'Invoice_No', 'Invoice_Date', 'Taxable_Value', 
            'IGST', 'CGST', 'SGST', 'TOTAL_TAX'
        ]].copy()
        missing_books_export.columns = ['GSTIN', 'Invoice No', 'Date', 'Taxable Value', 'IGST', 'CGST', 'SGST', 'Total Tax']
        missing_books_export.to_excel(writer, sheet_name='Missing in Books', index=False)
        
        # Missing in 2B
        missing_2b_export = results['missing_in_2b'][[
            'GSTIN', 'Invoice_No', 'Invoice_Date', 'Taxable_Value', 
            'IGST', 'CGST', 'SGST', 'TOTAL_TAX'
        ]].copy()
        missing_2b_export.columns = ['GSTIN', 'Invoice No', 'Date', 'Taxable Value', 'IGST', 'CGST', 'SGST', 'Total Tax']
        missing_2b_export.to_excel(writer, sheet_name='Missing in 2B', index=False)
        
        # Value Mismatch
        if len(results['value_mismatch']) > 0:
            value_export = results['value_mismatch'][[
                'GSTIN', 'Invoice_No', 'Taxable_Value_2B', 'Taxable_Value_Tally', 'Taxable_Value_Diff'
            ]].copy()
            value_export.columns = ['GSTIN', 'Invoice No', 'Value (2B)', 'Value (Books)', 'Difference']
            value_export.to_excel(writer, sheet_name='Value Mismatch', index=False)
        
        # Tax Mismatch
        if len(results['tax_mismatch']) > 0:
            tax_export = results['tax_mismatch'][[
                'GSTIN', 'Invoice_No', 'IGST_2B', 'IGST_Tally', 'CGST_2B', 'CGST_Tally', 'SGST_2B', 'SGST_Tally'
            ]].copy()
            tax_export.columns = ['GSTIN', 'Invoice No', 'IGST (2B)', 'IGST (Books)', 'CGST (2B)', 'CGST (Books)', 'SGST (2B)', 'SGST (Books)']
            tax_export.to_excel(writer, sheet_name='Tax Mismatch', index=False)
    
    output.seek(0)
    
    st.download_button(
        label="Download Excel Report",
        data=output,
        file_name="gst_reconciliation_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
