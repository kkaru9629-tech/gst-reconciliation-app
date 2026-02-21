import pandas as pd
import re

# ---------------- COMMON CLEANERS ---------------- #

def clean_string(val):
    if pd.isna(val):
        return ""
    return str(val).strip().upper()

def clean_invoice(inv):
    if pd.isna(inv):
        return ""
    return re.sub(r"[^A-Z0-9/.-]", "", str(inv).upper())


# ---------------- TALLY PARSER ---------------- #

def parse_tally(df):

    df = df.copy()

    # Detect header safely (Tally format)
    header_idx = None
    for i in range(min(len(df), 30)):
        row = " ".join(df.iloc[i].astype(str).str.lower().values)
        if "supplier invoice no" in row and "gstin" in row:
            header_idx = i
            break

    if header_idx is None:
        raise ValueError("Tally header not detected.")

    df.columns = df.iloc[header_idx]
    df = df.iloc[header_idx + 1:].reset_index(drop=True)
    df = df.dropna(how="all")

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
            raise ValueError(f"{col} missing in Tally file.")

    df["GSTIN"] = df["GSTIN"].apply(clean_string)
    df["Invoice_No"] = df["Invoice_No"].apply(clean_invoice)
    df["Invoice_Date"] = pd.to_datetime(df["Invoice_Date"], errors="coerce", dayfirst=True)

    # Detect tax columns
    cgst_cols = [c for c in df.columns if "input_cgst" in str(c).lower()]
    sgst_cols = [c for c in df.columns if "input_sgst" in str(c).lower()]
    igst_cols = [c for c in df.columns if "input igst" in str(c).lower()]

    df["CGST"] = df[cgst_cols].apply(pd.to_numeric, errors="coerce").sum(axis=1) if cgst_cols else 0
    df["SGST"] = df[sgst_cols].apply(pd.to_numeric, errors="coerce").sum(axis=1) if sgst_cols else 0
    df["IGST"] = df[igst_cols].apply(pd.to_numeric, errors="coerce").sum(axis=1) if igst_cols else 0

    df["Invoice_Value"] = pd.to_numeric(df["Invoice_Value"], errors="coerce")
    df["TOTAL_TAX"] = df["CGST"] + df["SGST"] + df["IGST"]
    df["Taxable_Value"] = df["Invoice_Value"] - df["TOTAL_TAX"]

    df = df.drop_duplicates(subset=["GSTIN", "Invoice_No"])
    df = df[df["Invoice_Date"].notna()]

    return df[[
        "GSTIN",
        "Trade_Name",
        "Invoice_No",
        "Invoice_Date",
        "Taxable_Value",
        "Invoice_Value",
        "IGST",
        "CGST",
        "SGST",
        "TOTAL_TAX"
    ]]


# ---------------- GSTR-2B PARSER (FIXED FORMAT) ---------------- #

def parse_gstr2b(df):

    df = df.copy()
    df = df.dropna(how="all")

    # Header assumed in first row (as confirmed)
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
            raise ValueError(
                "GSTR-2B format incorrect. Please use the confirmed structured format."
            )

    df["GSTIN"] = df["GSTIN"].apply(clean_string)
    df["Invoice_No"] = df["Invoice_No"].apply(clean_invoice)
    df["Invoice_Date"] = pd.to_datetime(df["Invoice_Date"], errors="coerce", dayfirst=True)

    for col in ["Taxable_Value", "IGST", "CGST", "SGST"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        else:
            df[col] = 0

    df["TOTAL_TAX"] = df["IGST"] + df["CGST"] + df["SGST"]
    df["Invoice_Value"] = df["Taxable_Value"] + df["TOTAL_TAX"]

    df = df.drop_duplicates(subset=["GSTIN", "Invoice_No"])
    df = df[df["Invoice_Date"].notna()]

    return df[[
        "GSTIN",
        "Trade_Name",
        "Invoice_No",
        "Invoice_Date",
        "Taxable_Value",
        "Invoice_Value",
        "IGST",
        "CGST",
        "SGST",
        "TOTAL_TAX"
    ]]


# ---------------- RECONCILIATION ---------------- #

def reconcile(gstr2b_df, tally_df):

    gstr2b_df["KEY"] = gstr2b_df["GSTIN"] + "|" + gstr2b_df["Invoice_No"]
    tally_df["KEY"] = tally_df["GSTIN"] + "|" + tally_df["Invoice_No"]

    missing_books = gstr2b_df[~gstr2b_df["KEY"].isin(tally_df["KEY"])]
    missing_2b = tally_df[~tally_df["KEY"].isin(gstr2b_df["KEY"])]

    merged = pd.merge(gstr2b_df, tally_df, on="KEY", suffixes=("_2B", "_Tally"))

    merged["VALUE_MATCH"] = abs(merged["Taxable_Value_2B"] - merged["Taxable_Value_Tally"]) <= 1
    merged["TAX_MATCH"] = abs(merged["TOTAL_TAX_2B"] - merged["TOTAL_TAX_Tally"]) <= 1

    fully_matched = merged[merged["VALUE_MATCH"] & merged["TAX_MATCH"]]
    value_mismatch = merged[~merged["VALUE_MATCH"]]
    tax_mismatch = merged[merged["VALUE_MATCH"] & ~merged["TAX_MATCH"]]

    summary = {
        "Total_Invoices_Books": len(tally_df),
        "Total_Invoices_2B": len(gstr2b_df),
        "Total_Matched": len(fully_matched),
        "Total_Missing_Books": len(missing_books),
        "Total_Missing_2B": len(missing_2b),
        "Total_ITC_Books": tally_df["TOTAL_TAX"].sum(),
        "Total_ITC_2B": gstr2b_df["TOTAL_TAX"].sum(),
        "ITC_Difference": gstr2b_df["TOTAL_TAX"].sum() - tally_df["TOTAL_TAX"].sum()
    }

    return {
        "fully_matched": fully_matched,
        "missing_in_books": missing_books,
        "missing_in_2b": missing_2b,
        "value_mismatch": value_mismatch,
        "tax_mismatch": tax_mismatch,
        "summary": summary
    }
