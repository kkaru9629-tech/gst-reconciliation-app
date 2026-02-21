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
    s_value = str(value).replace('Dr', '').replace('Cr', '').replace(',', '').strip()
    try:
        return float(s_value)
    except:
        return 0.0


# -------------------- TALLY PARSER -------------------- #

def parse_tally(df):

    df = df.copy()

    # 🔍 Auto-detect header row
    header_idx = None
    for i in range(min(len(df), 25)):
        row = [str(x).lower() for x in df.iloc[i].values]
        if any("gstin" in x for x in row) and any("invoice" in x for x in row):
            header_idx = i
            break

    if header_idx is not None:
        df.columns = df.iloc[header_idx]
        df = df.iloc[header_idx + 1:].reset_index(drop=True)
    else:
        df.columns = df.columns.astype(str)

    df = df.dropna(how="all")
    df.columns = [str(c).strip() for c in df.columns]

    column_mapping = {}

    for col in df.columns:
        col_lower = col.lower()

        if "gstin" in col_lower or "uin" in col_lower:
            column_mapping[col] = "GSTIN"

        elif "supplier invoice" in col_lower or "invoice no" in col_lower:
            column_mapping[col] = "Invoice_No"

        elif col_lower.strip() == "date":
            column_mapping[col] = "Invoice_Date"

        elif "gross total" in col_lower or "total" in col_lower:
            column_mapping[col] = "Invoice_Value"

        elif "particular" in col_lower:
            column_mapping[col] = "Trade_Name"

    df.rename(columns=column_mapping, inplace=True)

    required = ["GSTIN", "Invoice_No", "Invoice_Date"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"{col} column not found in Tally")

    # Clean fields
    df["GSTIN"] = df["GSTIN"].apply(clean_string)
    df["Invoice_No"] = df["Invoice_No"].apply(clean_invoice_number)
    df["Invoice_Date"] = pd.to_datetime(df["Invoice_Date"], errors="coerce", dayfirst=True)

    # Detect tax columns automatically
    igst_cols = [c for c in df.columns if "igst" in c.lower()]
    cgst_cols = [c for c in df.columns if "cgst" in c.lower()]
    sgst_cols = [c for c in df.columns if "sgst" in c.lower()]

    df["IGST"] = df[igst_cols].sum(axis=1) if igst_cols else 0
    df["CGST"] = df[cgst_cols].sum(axis=1) if cgst_cols else 0
    df["SGST"] = df[sgst_cols].sum(axis=1) if sgst_cols else 0

    if "Invoice_Value" in df.columns:
        df["Invoice_Value"] = df["Invoice_Value"].apply(parse_numeric)
    else:
        df["Invoice_Value"] = 0

    df["TOTAL_TAX"] = df["IGST"] + df["CGST"] + df["SGST"]
    df["Taxable_Value"] = df["Invoice_Value"] - df["TOTAL_TAX"]

    df = df.drop_duplicates(subset=["GSTIN", "Invoice_No"])
    df = df[df["Invoice_Date"].notna()]

    return df[
        [
            "GSTIN",
            "Trade_Name" if "Trade_Name" in df.columns else "GSTIN",
            "Invoice_No",
            "Invoice_Date",
            "Taxable_Value",
            "Invoice_Value",
            "TOTAL_TAX",
        ]
    ].reset_index(drop=True)
def parse_gstr2b(df):

    df = df.copy()

    # 🔍 Find first header row containing GSTIN
    header_idx = None
    for i in range(min(len(df), 30)):
        row = [str(x).lower() for x in df.iloc[i].values]
        if any("gstin" in x for x in row):
            header_idx = i
            break

    if header_idx is None:
        raise ValueError("GSTR-2B header not detected")

    # Combine TWO header rows
    header_row1 = df.iloc[header_idx].fillna("")
    header_row2 = df.iloc[header_idx + 1].fillna("")

    combined_headers = []
    for h1, h2 in zip(header_row1, header_row2):
        col_name = f"{h1} {h2}".strip()
        combined_headers.append(col_name)

    df.columns = combined_headers
    df = df.iloc[header_idx + 2:].reset_index(drop=True)

    df = df.dropna(how='all')
    df.columns = [str(c).strip() for c in df.columns]

    # 🔄 Rename dynamically
    column_mapping = {}

    for col in df.columns:
        col_lower = col.lower()

        if "gstin" in col_lower:
            column_mapping[col] = "GSTIN"

        elif "trade" in col_lower or "legal" in col_lower or "name" in col_lower or "supplier" in col_lower:
            column_mapping[col] = "Trade_Name"

        elif "invoice number" in col_lower or "inv no" in col_lower:
            column_mapping[col] = "Invoice_No"

        elif "invoice date" in col_lower or "inv date" in col_lower:
            column_mapping[col] = "Invoice_Date"

        elif "taxable value" in col_lower or "taxable amt" in col_lower:
            column_mapping[col] = "Taxable_Value"

        elif "integrated tax" in col_lower or "igst" in col_lower:
            column_mapping[col] = "IGST"

        elif "central tax" in col_lower or "cgst" in col_lower:
            column_mapping[col] = "CGST"

        elif "state" in col_lower or "sgst" in col_lower or "utgst" in col_lower:
            column_mapping[col] = "SGST"

    df.rename(columns=column_mapping, inplace=True)

    # Validate required columns
    required = ["GSTIN", "Invoice_No", "Invoice_Date"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"{col} column not found in GSTR-2B")

    # Clean data
    df["GSTIN"] = df["GSTIN"].apply(clean_string)
    df["Invoice_No"] = df["Invoice_No"].apply(clean_invoice_number)
    df["Invoice_Date"] = pd.to_datetime(df["Invoice_Date"], errors="coerce", dayfirst=True)

    # Add Trade_Name if missing
    if 'Trade_Name' not in df.columns:
        df['Trade_Name'] = df['GSTIN']  # Fallback to GSTIN

    for col in ["Taxable_Value", "IGST", "CGST", "SGST"]:
        if col in df.columns:
            df[col] = df[col].apply(parse_numeric)
        else:
            df[col] = 0.0

    df["TOTAL_TAX"] = df["IGST"] + df["CGST"] + df["SGST"]
    df["Invoice_Value"] = df["Taxable_Value"] + df["TOTAL_TAX"]

    df = df.drop_duplicates(subset=["GSTIN", "Invoice_No"])
    df = df[df["Invoice_Date"].notna()]

    # Add Month column
    df['Month'] = df['Invoice_Date'].dt.to_period("M").astype(str)

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
    value_mismatch = merged[merged['Date_Match'] & ~merged['Value_Match'] & merged['Tax_Match']]
    tax_mismatch = merged[merged['Date_Match'] & merged['Value_Match'] & ~merged['Tax_Match']]
    
    # Both mismatch
    both_mismatch = merged[merged['Date_Match'] & ~merged['Value_Match'] & ~merged['Tax_Match']]
    
    # Combine mismatches
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
