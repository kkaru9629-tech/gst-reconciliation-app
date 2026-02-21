import pandas as pd
import re

# -------------------------------------------------------
# COMMON CLEAN FUNCTIONS
# -------------------------------------------------------

def clean_string(val):
    if pd.isna(val):
        return ""
    return str(val).strip().upper()


def clean_invoice_number(inv_no):
    if pd.isna(inv_no):
        return ""
    return re.sub(r'[^A-Z0-9]', '', str(inv_no).upper())


def parse_numeric(value):
    if pd.isna(value):
        return 0.0
    return pd.to_numeric(str(value).replace(',', ''), errors="coerce")


# -------------------------------------------------------
# TALLY PARSER (Custom for your exact format)
# -------------------------------------------------------

def parse_tally(df):

    df = df.copy()

    # -------- HEADER DETECTION -------- #
    header_idx = None

    for i in range(min(len(df), 20)):
        row_values = df.iloc[i].astype(str).str.lower().values

        if ("date" in " ".join(row_values)
            and "particular" in " ".join(row_values)
            and "supplier invoice" in " ".join(row_values)):
            
            header_idx = i
            break

    if header_idx is None:
        raise ValueError("Tally header not detected")

    # Set header properly
    df.columns = df.iloc[header_idx]
    df = df.iloc[header_idx + 1:].reset_index(drop=True)

    df = df.dropna(how="all")
    df.columns = [str(c).strip() for c in df.columns]

    # -------- RENAME COLUMNS -------- #
    df.rename(columns={
        "Date": "Invoice_Date",
        "Particulars": "Trade_Name",
        "Supplier Invoice No.": "Invoice_No",
        "GSTIN/UIN": "GSTIN",
        "Gross Total": "Invoice_Value"
    }, inplace=True)

    required = ["GSTIN", "Invoice_No", "Invoice_Date"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"{col} column not found in Tally file")

    # -------- CLEAN DATA -------- #
    df["GSTIN"] = df["GSTIN"].astype(str).str.strip().str.upper()
    df["Invoice_No"] = df["Invoice_No"].astype(str).str.replace(r'[^A-Z0-9]', '', regex=True).str.upper()
    df["Invoice_Date"] = pd.to_datetime(df["Invoice_Date"], errors="coerce", dayfirst=True)

    # -------- TAX EXTRACTION -------- #
    cgst_cols = [c for c in df.columns if "input_cgst" in c.lower()]
    sgst_cols = [c for c in df.columns if "input_sgst" in c.lower()]
    igst_cols = [c for c in df.columns if "input igst" in c.lower()]

    df["CGST"] = df[cgst_cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1) if cgst_cols else 0
    df["SGST"] = df[sgst_cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1) if sgst_cols else 0
    df["IGST"] = df[igst_cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1) if igst_cols else 0

    df["Invoice_Value"] = pd.to_numeric(df["Invoice_Value"], errors="coerce").fillna(0)

    df["TOTAL_TAX"] = df["CGST"] + df["SGST"] + df["IGST"]
    df["Taxable_Value"] = df["Invoice_Value"] - df["TOTAL_TAX"]

    df["Month"] = df["Invoice_Date"].dt.to_period("M").astype(str)

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
def parse_gstr2b(df):

    df = df.copy()

    # Skip first rows until header appears
    header_row = None

    for i in range(20):
        if str(df.iloc[i, 0]).strip().lower() == "gstin of supplier":
            header_row = i
            break

    if header_row is None:
        raise ValueError("GSTR-2B header not detected")

    df.columns = df.iloc[header_row]
    df = df.iloc[header_row + 1:].reset_index(drop=True)

    df = df.dropna(how="all")
    df.columns = [str(c).strip() for c in df.columns]

    # Rename columns
    df.rename(columns={
        "GSTIN of supplier": "GSTIN",
        "Trade/Legal name": "Trade_Name",
        "Invoice number": "Invoice_No",
        "Invoice Date": "Invoice_Date",
        "Taxable Value (₹)": "Taxable_Value",
        "Integrated Tax(₹)": "IGST",
        "Central Tax(₹)": "CGST",
        "State/UT Tax(₹)": "SGST"
    }, inplace=True)

    required = ["GSTIN", "Invoice_No", "Invoice_Date"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"{col} column missing in GSTR-2B")

    # Cleaning
    df["GSTIN"] = df["GSTIN"].apply(clean_string)
    df["Invoice_No"] = df["Invoice_No"].apply(clean_invoice_number)
    df["Invoice_Date"] = pd.to_datetime(df["Invoice_Date"], errors="coerce", dayfirst=True)

    for col in ["Taxable_Value", "IGST", "CGST", "SGST"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        else:
            df[col] = 0.0

    df["TOTAL_TAX"] = df["IGST"] + df["CGST"] + df["SGST"]
    df["Invoice_Value"] = df["Taxable_Value"] + df["TOTAL_TAX"]

    df = df.drop_duplicates(subset=["GSTIN", "Invoice_No"])
    df = df[df["Invoice_Date"].notna()]

    df["Month"] = df["Invoice_Date"].dt.to_period("M").astype(str)

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
    ]]


# -------------------------------------------------------
# RECONCILIATION
# -------------------------------------------------------

def reconcile(gstr2b_df, tally_df):

    gstr2b_df["Match_Key"] = gstr2b_df["GSTIN"] + "|" + gstr2b_df["Invoice_No"]
    tally_df["Match_Key"] = tally_df["GSTIN"] + "|" + tally_df["Invoice_No"]

    missing_in_books = gstr2b_df[~gstr2b_df["Match_Key"].isin(tally_df["Match_Key"])]
    missing_in_2b = tally_df[~tally_df["Match_Key"].isin(gstr2b_df["Match_Key"])]

    merged = pd.merge(
        gstr2b_df,
        tally_df,
        on="Match_Key",
        suffixes=("_2B", "_Tally")
    )

    merged["Value_Match"] = abs(merged["Taxable_Value_2B"] - merged["Taxable_Value_Tally"]) <= 1
    merged["Tax_Match"] = abs(merged["TOTAL_TAX_2B"] - merged["TOTAL_TAX_Tally"]) <= 1

    fully_matched = merged[merged["Value_Match"] & merged["Tax_Match"]]
    value_mismatch = merged[~merged["Value_Match"]]
    tax_mismatch = merged[merged["Value_Match"] & ~merged["Tax_Match"]]

    summary = {
        "Total_Invoices_Books": len(tally_df),
        "Total_Invoices_2B": len(gstr2b_df),
        "Total_Matched": len(fully_matched),
        "Total_Missing_Books": len(missing_in_books),
        "Total_Missing_2B": len(missing_in_2b),
        "Total_ITC_Books": tally_df["TOTAL_TAX"].sum(),
        "Total_ITC_2B": gstr2b_df["TOTAL_TAX"].sum(),
        "ITC_Difference": gstr2b_df["TOTAL_TAX"].sum() - tally_df["TOTAL_TAX"].sum()
    }

    return {
        "fully_matched": fully_matched,
        "missing_in_books": missing_in_books,
        "missing_in_2b": missing_in_2b,
        "value_mismatch": value_mismatch,
        "tax_mismatch": tax_mismatch,
        "summary": summary
    }
