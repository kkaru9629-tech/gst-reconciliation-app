import pandas as pd
import re

# ---------------- CLEANING FUNCTIONS ---------------- #

def clean_string(val):
    return "" if pd.isna(val) else str(val).strip().upper()

def clean_invoice_number(val):
    return "" if pd.isna(val) else re.sub(r"[^A-Z0-9]", "", str(val).upper())

def parse_numeric(val):
    if pd.isna(val):
        return 0.0
    val = str(val).replace(",", "").replace("Dr", "").replace("Cr", "").strip()
    try:
        return float(val)
    except:
        return 0.0


# ---------------- TALLY PARSER ---------------- #

def parse_tally(df):

    df = df.dropna(how="all")
    df.columns = df.columns.astype(str)

    col_map = {}

    for col in df.columns:
        col_lower = col.lower()

        if "gstin" in col_lower:
            col_map[col] = "GSTIN"
        elif "invoice" in col_lower:
            col_map[col] = "Invoice_No"
        elif "date" in col_lower:
            col_map[col] = "Invoice_Date"
        elif "gross" in col_lower:
            col_map[col] = "Invoice_Value"
        elif "particular" in col_lower:
            col_map[col] = "Trade_Name"

    df.rename(columns=col_map, inplace=True)

    required = ["GSTIN", "Invoice_No", "Invoice_Date"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"{col} column not found in Tally")

    df["GSTIN"] = df["GSTIN"].apply(clean_string)
    df["Invoice_No"] = df["Invoice_No"].apply(clean_invoice_number)
    df["Invoice_Date"] = pd.to_datetime(df["Invoice_Date"], errors="coerce", dayfirst=True)

    igst = [c for c in df.columns if "igst" in c.lower()]
    cgst = [c for c in df.columns if "cgst" in c.lower()]
    sgst = [c for c in df.columns if "sgst" in c.lower()]

    df["IGST"] = df[igst].sum(axis=1) if igst else 0
    df["CGST"] = df[cgst].sum(axis=1) if cgst else 0
    df["SGST"] = df[sgst].sum(axis=1) if sgst else 0

    df["TOTAL_TAX"] = df["IGST"] + df["CGST"] + df["SGST"]
    df["Taxable_Value"] = df.get("Invoice_Value", 0) - df["TOTAL_TAX"]

    return df[["GSTIN", "Trade_Name", "Invoice_No", "Invoice_Date", "Taxable_Value", "TOTAL_TAX"]]


# ---------------- GSTR2B PARSER ---------------- #

def parse_gstr2b(df):

    df = df.dropna(how="all")

    header_idx = None
    for i in range(min(30, len(df))):
        if df.iloc[i].astype(str).str.contains("GSTIN", case=False).any():
            header_idx = i
            break

    if header_idx is None:
        raise ValueError("GSTR-2B header not detected")

    df.columns = df.iloc[header_idx]
    df = df.iloc[header_idx + 1:].reset_index(drop=True)

    col_map = {}

    for col in df.columns:
        col_lower = str(col).lower()

        if "gstin" in col_lower:
            col_map[col] = "GSTIN"
        elif "trade" in col_lower:
            col_map[col] = "Trade_Name"
        elif "invoice number" in col_lower:
            col_map[col] = "Invoice_No"
        elif "invoice date" in col_lower:
            col_map[col] = "Invoice_Date"
        elif "taxable value" in col_lower:
            col_map[col] = "Taxable_Value"
        elif "integrated tax" in col_lower:
            col_map[col] = "IGST"
        elif "central tax" in col_lower:
            col_map[col] = "CGST"
        elif "state" in col_lower:
            col_map[col] = "SGST"

    df.rename(columns=col_map, inplace=True)

    required = ["GSTIN", "Invoice_No", "Invoice_Date"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"{col} column not found in 2B")

    df["GSTIN"] = df["GSTIN"].apply(clean_string)
    df["Invoice_No"] = df["Invoice_No"].apply(clean_invoice_number)
    df["Invoice_Date"] = pd.to_datetime(df["Invoice_Date"], errors="coerce", dayfirst=True)

    df["IGST"] = df.get("IGST", 0)
    df["CGST"] = df.get("CGST", 0)
    df["SGST"] = df.get("SGST", 0)

    df["TOTAL_TAX"] = df["IGST"] + df["CGST"] + df["SGST"]

    return df[["GSTIN", "Trade_Name", "Invoice_No", "Invoice_Date", "Taxable_Value", "TOTAL_TAX"]]


# ---------------- RECONCILIATION ---------------- #

def reconcile(gstr2b, tally):

    gstr2b["Key"] = gstr2b["GSTIN"] + "|" + gstr2b["Invoice_No"]
    tally["Key"] = tally["GSTIN"] + "|" + tally["Invoice_No"]

    missing_books = gstr2b[~gstr2b["Key"].isin(tally["Key"])]
    missing_2b = tally[~tally["Key"].isin(gstr2b["Key"])]

    merged = pd.merge(gstr2b, tally, on="Key", suffixes=("_2B", "_Books"))

    merged["Value_Diff"] = merged["Taxable_Value_2B"] - merged["Taxable_Value_Books"]
    merged["Tax_Diff"] = merged["TOTAL_TAX_2B"] - merged["TOTAL_TAX_Books"]

    fully_matched = merged[(merged["Value_Diff"].abs() <= 1) & (merged["Tax_Diff"].abs() <= 1)]
    value_mismatch = merged[merged["Value_Diff"].abs() > 1]
    tax_mismatch = merged[merged["Tax_Diff"].abs() > 1]

    summary = {
        "Total_Invoices_Books": len(tally),
        "Total_Invoices_2B": len(gstr2b),
        "Total_Matched": len(fully_matched),
        "Total_Missing_Books": len(missing_books),
        "Total_Missing_2B": len(missing_2b),
        "Total_ITC_Books": tally["TOTAL_TAX"].sum(),
        "Total_ITC_2B": gstr2b["TOTAL_TAX"].sum(),
        "ITC_Difference": gstr2b["TOTAL_TAX"].sum() - tally["TOTAL_TAX"].sum()
    }

    return {
        "fully_matched": fully_matched,
        "missing_in_books": missing_books,
        "missing_in_2b": missing_2b,
        "value_mismatch": value_mismatch,
        "tax_mismatch": tax_mismatch,
        "summary": summary
    }
