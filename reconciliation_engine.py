import pandas as pd
import re
import numpy as np


def clean_string(val):
    if pd.isna(val):
        return ""
    return str(val).strip().upper()


def clean_invoice_number(inv_no):
    if pd.isna(inv_no):
        return ""
    return re.sub(r'[^A-Z0-9]', '', str(inv_no).strip().upper())


def parse_numeric(value):
    if pd.isna(value):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s_value = str(value).replace('Dr', '').replace('Cr', '').replace(',', '').strip()
    try:
        return float(s_value)
    except:
        return 0.0


# -------------------- TALLY PARSER (Customized for your format) -------------------- #

def parse_tally(df):

    df = df.copy()

    # Find the actual header row (where column names are)
    header_idx = None
    for i in range(min(len(df), 15)):
        row_values = df.iloc[i].astype(str).values
        # Look for the row that contains "Date" and "Particulars" and "Supplier Invoice No."
        if any("date" in str(x).lower() for x in row_values) and any("particular" in str(x).lower() for x in row_values):
            header_idx = i
            break

    if header_idx is None:
        # If not found, try first row
        header_idx = 0

    # Set the header
    df.columns = df.iloc[header_idx]
    df = df.iloc[header_idx + 1:].reset_index(drop=True)

    # Remove completely empty rows
    df = df.dropna(how='all')
    
    # Clean column names
    df.columns = [str(col).strip() for col in df.columns]

    # EXACT COLUMN MAPPING for your format
    column_mapping = {
        'Date': 'Invoice_Date',
        'Particulars': 'Trade_Name',
        'Supplier Invoice No.': 'Invoice_No',
        'GSTIN/UIN': 'GSTIN',
        'Gross Total': 'Invoice_Value'
    }

    # Apply mapping for columns that exist
    rename_dict = {}
    for col in df.columns:
        if col in column_mapping:
            rename_dict[col] = column_mapping[col]
    
    df.rename(columns=rename_dict, inplace=True)

    # Check required columns
    required = ['GSTIN', 'Invoice_No', 'Invoice_Date']
    missing_cols = [col for col in required if col not in df.columns]
    
    if missing_cols:
        raise ValueError(f"Required columns not found: {missing_cols}. Found columns: {list(df.columns)}")

    # Clean data
    df['GSTIN'] = df['GSTIN'].apply(clean_string)
    df['Invoice_No'] = df['Invoice_No'].apply(clean_invoice_number)
    df['Invoice_Date'] = pd.to_datetime(df['Invoice_Date'], format='%d-%b-%y', errors='coerce')

    # Extract tax columns from your format
    # Look for Input_CGST, Input_SGST, Input IGST columns
    cgst_col = None
    sgst_col = None
    igst_col = None
    
    for col in df.columns:
        col_lower = str(col).lower()
        if 'input_cgst' in col_lower:
            cgst_col = col
        elif 'input_sgst' in col_lower:
            sgst_col = col
        elif 'input igst' in col_lower:
            igst_col = col

    # Calculate taxes
    df['CGST'] = parse_numeric(df[cgst_col]) if cgst_col else 0
    df['SGST'] = parse_numeric(df[sgst_col]) if sgst_col else 0
    df['IGST'] = parse_numeric(df[igst_col]) if igst_col else 0

    # Calculate Invoice Value if not present
    if 'Invoice_Value' in df.columns:
        df['Invoice_Value'] = df['Invoice_Value'].apply(parse_numeric)
    else:
        # Try to find value column
        value_cols = [c for c in df.columns if 'value' in str(c).lower() or 'total' in str(c).lower()]
        if value_cols:
            df['Invoice_Value'] = df[value_cols[0]].apply(parse_numeric)
        else:
            df['Invoice_Value'] = 0

    # Calculate totals
    df['TOTAL_TAX'] = df['CGST'] + df['SGST'] + df['IGST']
    df['Taxable_Value'] = df['Invoice_Value'] - df['TOTAL_TAX']

    # Add Month column
    df['Month'] = df['Invoice_Date'].dt.to_period('M').astype(str)

    # Remove duplicates and null dates
    df = df.drop_duplicates(subset=['GSTIN', 'Invoice_No'])
    df = df[df['Invoice_Date'].notna()]

    return df[[
        'GSTIN',
        'Trade_Name',
        'Invoice_No',
        'Invoice_Date',
        'Month',
        'Taxable_Value',
        'Invoice_Value',
        'IGST',
        'CGST',
        'SGST',
        'TOTAL_TAX'
    ]].reset_index(drop=True)


# -------------------- GSTR2B PARSER -------------------- #

def parse_gstr2b(df):

    df = df.copy()

    # -------- HEADER DETECTION -------- #
    header_idx = None

    for i in range(min(len(df), 30)):
        # Check for GSTIN related text
        row_values = df.iloc[i].astype(str).str.lower().values
        if any("gstin" in str(x) for x in row_values):
            header_idx = i
            break

    if header_idx is None:
        # Try alternate detection
        for i in range(min(len(df), 30)):
            row_values = df.iloc[i].astype(str).str.lower().values
            if any(keyword in str(x) for x in row_values for keyword in ['invoice', 'taxable', 'gst']):
                header_idx = i
                break

    if header_idx is None:
        raise ValueError("GSTR-2B header not detected. Make sure original GST portal file is uploaded.")

    # Handle multi-row headers (common in GSTR-2B)
    if header_idx + 1 < len(df):
        # Check if next row also has column info
        next_row = df.iloc[header_idx + 1].astype(str)
        if not all(pd.isna(x) or x == 'nan' for x in next_row):
            # Combine two header rows
            header_row1 = df.iloc[header_idx].fillna("")
            header_row2 = df.iloc[header_idx + 1].fillna("")
            
            combined_headers = []
            for h1, h2 in zip(header_row1, header_row2):
                col_name = f"{h1} {h2}".strip()
                combined_headers.append(col_name)
            
            df.columns = combined_headers
            df = df.iloc[header_idx + 2:].reset_index(drop=True)
        else:
            df.columns = df.iloc[header_idx]
            df = df.iloc[header_idx + 1:].reset_index(drop=True)
    else:
        df.columns = df.iloc[header_idx]
        df = df.iloc[header_idx + 1:].reset_index(drop=True)

    df = df.dropna(how="all")
    df.columns = [str(c).strip() for c in df.columns]

    # -------- RENAME COLUMNS -------- #
    column_mapping = {}

    for col in df.columns:
        col_lower = col.lower()

        # GSTIN detection
        if "gstin" in col_lower:
            column_mapping[col] = "GSTIN"

        # Trade/Legal Name detection
        elif any(keyword in col_lower for keyword in ['trade', 'legal', 'name', 'supplier', 'party']):
            column_mapping[col] = "Trade_Name"

        # Invoice Number detection
        elif any(keyword in col_lower for keyword in ['invoice number', 'inv no', 'invoice no', 'bill no']):
            column_mapping[col] = "Invoice_No"

        # Invoice Date detection
        elif any(keyword in col_lower for keyword in ['invoice date', 'inv date', 'bill date']):
            column_mapping[col] = "Invoice_Date"

        # Taxable Value detection
        elif any(keyword in col_lower for keyword in ['taxable value', 'taxable amt', 'taxable amount']):
            column_mapping[col] = "Taxable_Value"

        # Tax detection
        elif any(keyword in col_lower for keyword in ['integrated tax', 'igst']):
            column_mapping[col] = "IGST"
        elif any(keyword in col_lower for keyword in ['central tax', 'cgst']):
            column_mapping[col] = "CGST"
        elif any(keyword in col_lower for keyword in ['state', 'sgst', 'utgst']):
            column_mapping[col] = "SGST"

    df.rename(columns=column_mapping, inplace=True)

    # -------- REQUIRED CHECK -------- #
    required = ["GSTIN", "Invoice_No", "Invoice_Date"]
    missing_cols = [col for col in required if col not in df.columns]
    
    if missing_cols:
        raise ValueError(f"Required columns not found in GSTR-2B: {missing_cols}. Found columns: {list(df.columns)}")

    # -------- CLEAN DATA -------- #
    df["GSTIN"] = df["GSTIN"].astype(str).str.strip().str.upper()
    df["Invoice_No"] = df["Invoice_No"].astype(str).apply(clean_invoice_number)
    df["Invoice_Date"] = pd.to_datetime(df["Invoice_Date"], errors="coerce", dayfirst=True)

    # Add Trade_Name if missing
    if "Trade_Name" not in df.columns:
        df["Trade_Name"] = df["GSTIN"]

    # Numeric handling
    for col in ["Taxable_Value", "IGST", "CGST", "SGST"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        else:
            df[col] = 0.0

    df["TOTAL_TAX"] = df["IGST"] + df["CGST"] + df["SGST"]
    df["Invoice_Value"] = df["Taxable_Value"] + df["TOTAL_TAX"]

    # Add Month column
    df['Month'] = df['Invoice_Date'].dt.to_period("M").astype(str)

    df = df.drop_duplicates(subset=["GSTIN", "Invoice_No"])
    df = df[df["Invoice_Date"].notna()]

    return df[[
        "GSTIN",
        "Trade_Name",
        "Invoice_No",
        "Invoice_Date",
        "Month",
        "Taxable_Value",
        "Invoice_Value",
        "IGST",
        "CGST",
        "SGST",
        "TOTAL_TAX"
    ]].reset_index(drop=True)


# -------------------- RECONCILIATION -------------------- #

def reconcile(gstr2b_df, tally_df):

    gstr2b_df['Match_Key'] = gstr2b_df['GSTIN'] + '|' + gstr2b_df['Invoice_No']
    tally_df['Match_Key'] = tally_df['GSTIN'] + '|' + tally_df['Invoice_No']

    missing_in_books = gstr2b_df[~gstr2b_df['Match_Key'].isin(tally_df['Match_Key'])].copy()
    missing_in_2b = tally_df[~tally_df['Match_Key'].isin(gstr2b_df['Match_Key'])].copy()

    common = set(gstr2b_df['Match_Key']) & set(tally_df['Match_Key'])

    merged = pd.merge(
        gstr2b_df[gstr2b_df['Match_Key'].isin(common)],
        tally_df[tally_df['Match_Key'].isin(common)],
        on='Match_Key',
        suffixes=('_2B','_Tally')
    )

    merged['Date_Match'] = (abs((merged['Invoice_Date_2B'] - merged['Invoice_Date_Tally']).dt.days) <= 5)
    merged['Value_Match'] = (abs(merged['Taxable_Value_2B'] - merged['Taxable_Value_Tally']) <= 1)
    merged['Tax_Match'] = (abs(merged['TOTAL_TAX_2B'] - merged['TOTAL_TAX_Tally']) <= 1)
    
    # Calculate differences for reporting
    merged['Difference_Value'] = merged['Taxable_Value_2B'] - merged['Taxable_Value_Tally']
    merged['Difference_Tax'] = merged['TOTAL_TAX_2B'] - merged['TOTAL_TAX_Tally']

    fully_matched = merged[merged['Date_Match'] & merged['Value_Match'] & merged['Tax_Match']]
    value_mismatch = merged[merged['Date_Match'] & ~merged['Value_Match']]
    tax_mismatch = merged[merged['Date_Match'] & merged['Value_Match'] & ~merged['Tax_Match']]
    
    # Both mismatch - include in value mismatch
    both_mismatch = merged[merged['Date_Match'] & ~merged['Value_Match'] & ~merged['Tax_Match']]
    value_mismatch = pd.concat([value_mismatch, both_mismatch]).drop_duplicates()

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
