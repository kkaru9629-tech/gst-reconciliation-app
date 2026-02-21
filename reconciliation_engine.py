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
