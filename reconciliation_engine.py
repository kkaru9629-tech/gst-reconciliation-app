import pandas as pd
import re
import numpy as np
from datetime import timedelta

def clean_string(val):
    """Clean and standardize string values"""
    if pd.isna(val):
        return ""
    return str(val).strip().upper()

def clean_invoice_number(inv_no):
    """Clean invoice number: remove spaces, special chars, convert to uppercase"""
    if pd.isna(inv_no):
        return ""
    cleaned = re.sub(r'[^A-Z0-9]', '', str(inv_no).strip().upper())
    return cleaned

def parse_numeric(value):
    """Convert value to numeric, handling Dr/Cr and commas"""
    if pd.isna(value):
        return 0.0
    s_value = str(value).replace('Dr', '').replace('Cr', '').replace(',', '').strip()
    try:
        return float(s_value)
    except (ValueError, TypeError):
        return 0.0

def parse_tally(df):
    """Parse and clean Tally Purchase Register"""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    
    # Drop completely empty rows
    df = df.dropna(how='all')
    
    # Standardize column names
    column_mapping = {}
    for col in df.columns:
        col_lower = col.lower()
        if 'gstin' in col_lower or 'uin' in col_lower:
            column_mapping[col] = 'GSTIN'
        elif 'supplier invoice' in col_lower or 'invoice no' in col_lower:
            column_mapping[col] = 'Invoice_No'
        elif col_lower == 'date':
            column_mapping[col] = 'Invoice_Date'
        elif col_lower == 'value' and 'Taxable_Value' not in df.columns:
            column_mapping[col] = 'Taxable_Value'
        elif col_lower in ['gross total', 'total']:
            column_mapping[col] = 'Invoice_Value'
    
    df.rename(columns=column_mapping, inplace=True)
    
    # Ensure required columns exist
    if 'GSTIN' not in df.columns:
        raise ValueError("GSTIN column not found in Tally file")
    if 'Invoice_No' not in df.columns:
        raise ValueError("Invoice Number column not found in Tally file")
    if 'Invoice_Date' not in df.columns:
        raise ValueError("Invoice Date column not found in Tally file")
    
    # Clean GSTIN and Invoice Number
    df['GSTIN'] = df['GSTIN'].apply(clean_string)
    df['Invoice_No'] = df['Invoice_No'].apply(clean_invoice_number)
    
    # Parse date
    df['Invoice_Date'] = pd.to_datetime(df['Invoice_Date'], errors='coerce', dayfirst=True)
    
    # Parse numeric columns
    if 'Taxable_Value' not in df.columns:
        df['Taxable_Value'] = 0.0
    else:
        df['Taxable_Value'] = df['Taxable_Value'].apply(parse_numeric)
    
    if 'Invoice_Value' not in df.columns:
        df['Invoice_Value'] = 0.0
    else:
        df['Invoice_Value'] = df['Invoice_Value'].apply(parse_numeric)
    
    # Find and sum all tax columns
    igst_cols = [c for c in df.columns if re.search(r'igst', c, re.I)]
    cgst_cols = [c for c in df.columns if re.search(r'cgst', c, re.I)]
    sgst_cols = [c for c in df.columns if re.search(r'sgst', c, re.I)]
    
    df['IGST'] = 0.0
    df['CGST'] = 0.0
    df['SGST'] = 0.0
    
    if igst_cols:
        df['IGST'] = df[igst_cols].apply(lambda row: sum(parse_numeric(v) for v in row), axis=1)
    if cgst_cols:
        df['CGST'] = df[cgst_cols].apply(lambda row: sum(parse_numeric(v) for v in row), axis=1)
    if sgst_cols:
        df['SGST'] = df[sgst_cols].apply(lambda row: sum(parse_numeric(v) for v in row), axis=1)
    
    df['TOTAL_TAX'] = df['IGST'] + df['CGST'] + df['SGST']
    
    # Remove duplicates
    df = df.drop_duplicates(subset=['GSTIN', 'Invoice_No'], keep='first')
    
    # Remove rows with empty GSTIN or Invoice_No
    df = df[df['GSTIN'].str.len() > 0]
    df = df[df['Invoice_No'].str.len() > 0]
    df = df[df['Invoice_Date'].notna()]
    
    return df[['GSTIN', 'Invoice_No', 'Invoice_Date', 'Taxable_Value', 'Invoice_Value', 'IGST', 'CGST', 'SGST', 'TOTAL_TAX']].reset_index(drop=True)

def parse_gstr2b(df):
    """Parse and clean GSTR-2B file"""
    df = df.copy()
    
    # Find header row (contains GSTIN and Invoice number)
    header_idx = 0
    for i in range(min(len(df), 20)):
        row_vals = [str(x).lower() for x in df.iloc[i].values]
        if any('gstin' in str(x) for x in row_vals) and any('invoice' in str(x) for x in row_vals):
            header_idx = i
            break
    
    if header_idx > 0:
        df.columns = df.iloc[header_idx]
        df = df.iloc[header_idx+1:].reset_index(drop=True)
    
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how='all')
    
    # Standardize column names
    column_mapping = {}
    for col in df.columns:
        col_lower = col.lower()
        if 'gstin' in col_lower:
            column_mapping[col] = 'GSTIN'
        elif 'invoice number' in col_lower or 'invoice no' in col_lower:
            column_mapping[col] = 'Invoice_No'
        elif 'invoice date' in col_lower:
            column_mapping[col] = 'Invoice_Date'
        elif 'taxable value' in col_lower:
            column_mapping[col] = 'Taxable_Value'
        elif 'invoice value' in col_lower:
            column_mapping[col] = 'Invoice_Value'
        elif 'integrated tax' in col_lower:
            column_mapping[col] = 'IGST'
        elif 'central tax' in col_lower:
            column_mapping[col] = 'CGST'
        elif 'state/ut tax' in col_lower or 'state tax' in col_lower:
            column_mapping[col] = 'SGST'
    
    df.rename(columns=column_mapping, inplace=True)
    
    # Ensure required columns exist
    if 'GSTIN' not in df.columns:
        raise ValueError("GSTIN column not found in GSTR-2B file")
    if 'Invoice_No' not in df.columns:
        raise ValueError("Invoice Number column not found in GSTR-2B file")
    if 'Invoice_Date' not in df.columns:
        raise ValueError("Invoice Date column not found in GSTR-2B file")
    
    # Clean GSTIN and Invoice Number
    df['GSTIN'] = df['GSTIN'].apply(clean_string)
    df['Invoice_No'] = df['Invoice_No'].apply(clean_invoice_number)
    
    # Parse date
    df['Invoice_Date'] = pd.to_datetime(df['Invoice_Date'], errors='coerce', dayfirst=True)
    
    # Parse numeric columns
    for col in ['Taxable_Value', 'Invoice_Value', 'IGST', 'CGST', 'SGST']:
        if col not in df.columns:
            df[col] = 0.0
        else:
            df[col] = df[col].apply(parse_numeric)
    
    df['TOTAL_TAX'] = df['IGST'] + df['CGST'] + df['SGST']
    
    # Remove duplicates
    df = df.drop_duplicates(subset=['GSTIN', 'Invoice_No'], keep='first')
    
    # Remove rows with empty GSTIN or Invoice_No
    df = df[df['GSTIN'].str.len() > 0]
    df = df[df['Invoice_No'].str.len() > 0]
    df = df[df['Invoice_Date'].notna()]
    
    return df[['GSTIN', 'Invoice_No', 'Invoice_Date', 'Taxable_Value', 'Invoice_Value', 'IGST', 'CGST', 'SGST', 'TOTAL_TAX']].reset_index(drop=True)

def reconcile(gstr2b_df, tally_df):
    """Perform reconciliation between GSTR-2B and Tally"""
    
    # Create match keys
    gstr2b_df['Match_Key'] = gstr2b_df['GSTIN'] + '|' + gstr2b_df['Invoice_No']
    tally_df['Match_Key'] = tally_df['GSTIN'] + '|' + tally_df['Invoice_No']
    
    # 1. Missing in Books (in 2B but not in Tally)
    missing_in_books = gstr2b_df[~gstr2b_df['Match_Key'].isin(tally_df['Match_Key'])].copy()
    
    # 2. Missing in 2B (in Tally but not in 2B)
    missing_in_2b = tally_df[~tally_df['Match_Key'].isin(gstr2b_df['Match_Key'])].copy()
    
    # 3. Potential matches
    common_keys = set(gstr2b_df['Match_Key']) & set(tally_df['Match_Key'])
    
    # Merge for comparison
    gstr2b_matched = gstr2b_df[gstr2b_df['Match_Key'].isin(common_keys)].copy()
    tally_matched = tally_df[tally_df['Match_Key'].isin(common_keys)].copy()
    
    merged = pd.merge(
        gstr2b_matched,
        tally_matched,
        on='Match_Key',
        suffixes=('_2B', '_Tally')
    )
    
    # Check secondary conditions
    merged['Date_Diff'] = np.abs((merged['Invoice_Date_2B'] - merged['Invoice_Date_Tally']).dt.days)
    merged['Date_Match'] = merged['Date_Diff'] <= 5
    
    merged['Taxable_Value_Diff'] = np.abs(merged['Taxable_Value_2B'] - merged['Taxable_Value_Tally'])
    merged['Taxable_Value_Match'] = merged['Taxable_Value_Diff'] <= 1
    
    merged['IGST_Diff'] = np.abs(merged['IGST_2B'] - merged['IGST_Tally'])
    merged['IGST_Match'] = merged['IGST_Diff'] <= 1
    
    merged['CGST_Diff'] = np.abs(merged['CGST_2B'] - merged['CGST_Tally'])
    merged['CGST_Match'] = merged['CGST_Diff'] <= 1
    
    merged['SGST_Diff'] = np.abs(merged['SGST_2B'] - merged['SGST_Tally'])
    merged['SGST_Match'] = merged['SGST_Diff'] <= 1
    
    merged['TOTAL_TAX_Diff'] = np.abs(merged['TOTAL_TAX_2B'] - merged['TOTAL_TAX_Tally'])
    merged['TOTAL_TAX_Match'] = merged['TOTAL_TAX_Diff'] <= 1
    
    # Fully matched
    fully_matched = merged[
        merged['Date_Match'] &
        merged['Taxable_Value_Match'] &
        merged['IGST_Match'] &
        merged['CGST_Match'] &
        merged['SGST_Match']
    ].copy()
    
    # Value mismatches
    value_mismatch = merged[
        merged['Date_Match'] &
        ~merged['Taxable_Value_Match']
    ].copy()
    
    # Tax mismatches
    tax_mismatch = merged[
        merged['Date_Match'] &
        (~merged['IGST_Match'] | ~merged['CGST_Match'] | ~merged['SGST_Match'])
    ].copy()
    
    # Summary
    summary = {
        'Total_Invoices_Books': len(tally_df),
        'Total_Invoices_2B': len(gstr2b_df),
        'Total_Matched': len(fully_matched),
        'Total_Missing_Books': len(missing_in_books),
        'Total_Missing_2B': len(missing_in_2b),
        'Total_ITC_Books': tally_df['TOTAL_TAX'].sum(),
        'Total_ITC_2B': gstr2b_df['TOTAL_TAX'].sum(),
        'ITC_Difference': gstr2b_df['TOTAL_TAX'].sum() - tally_df['TOTAL_TAX'].sum()
    }
    
    return {
        'fully_matched': fully_matched,
        'missing_in_books': missing_in_books,
        'missing_in_2b': missing_in_2b,
        'value_mismatch': value_mismatch,
        'tax_mismatch': tax_mismatch,
        'summary': summary
    }
