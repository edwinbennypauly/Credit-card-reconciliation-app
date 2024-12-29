import streamlit as st
import pandas as pd
import numpy as np
import os

# Application
st.title("Credit Card Reconciliation Application")
st.write("Upload your **Bank File** and **SAP File** below to perform reconciliation.")

st.markdown(
    """
    <style>
    .footer {
        position: fixed;
        bottom: 10px;
        left: 10px;
        font-size: 12px;
        color: gray;
    }
    .footer a {
        color: gray;
        text-decoration: none;
    }
    .footer a:hover {
        text-decoration: underline;
    }
    </style>
    """,
    unsafe_allow_html=True,
)



# File uploads
bank_file = st.file_uploader("Upload Bank File (CSV)", type=["csv", "xls", "xlsx"])
sap_file = st.file_uploader("Upload SAP File (XLSX)", type=["xlsx"])

# Process files
if bank_file and sap_file:
    try:
        # Read files
        bank_file_df = pd.read_csv(bank_file, delimiter='\t') 
        # if bank_file.name.endswith('.csv') else pd.read_excel(bank_file)
        sap_file_df = pd.read_excel(sap_file)

        # Cleaning bank file
        bank_file_df = bank_file_df.dropna(how='all', axis=1)
        bank_file_df = bank_file_df[bank_file_df['Commercial Name'] != 'Total                         ']
        bank_file_df = bank_file_df[['Main Merchant No ', ' Terminal', ' Txn Date', ' Auth Id', 
                                      'Voucher Nbr / RRN', ' Card No', 'Bill Amount', ' Net Amount']]
        bank_file_df['Voucher Nbr / RRN'] = bank_file_df['Voucher Nbr / RRN'].str.replace(
            '=CONCATENATE("', '').str.replace('", " ")', '').str.strip()
        bank_file_df = bank_file_df[~bank_file_df['Bill Amount'].str.startswith('=SUBTOTAL', na=False)]

        # Rename SAP file column
        sap_file_df.rename(columns={'Text': 'Voucher Nbr / RRN'}, inplace=True)

        # Convert Voucher columns to string
        bank_file_df['Voucher Nbr / RRN'] = bank_file_df['Voucher Nbr / RRN'].astype(str)
        sap_file_df['Voucher Nbr / RRN'] = sap_file_df['Voucher Nbr / RRN'].astype(str)

        # Perform Level 1 Matching
        merged_bank_file = pd.merge(bank_file_df, sap_file_df, on='Voucher Nbr / RRN', how='left')
        matched_file = merged_bank_file[merged_bank_file['Document Type'].notna()].copy()
        matched_file[' Net Amount'] = matched_file[' Net Amount'].astype(float)
        matched_file['Net Amount - Amount in Local currency'] = (
            matched_file[' Net Amount'] - matched_file['Amount in Local Currency']).round(3)

        # Multiple Transactions and SUMIF logic
        sum_values = sap_file_df.groupby('Voucher Nbr / RRN')['Amount in Local Currency'].sum()
        multiple_transaction = matched_file.copy()
        multiple_transaction['SUMIF Result'] = multiple_transaction['Voucher Nbr / RRN'].map(sum_values)
        multiple_transaction_no_duplicates = multiple_transaction.drop_duplicates(subset=['Voucher Nbr / RRN'])[
            ['Voucher Nbr / RRN', ' Net Amount', 'SUMIF Result']].copy()
        multiple_transaction_no_duplicates['Difference'] = (
            multiple_transaction_no_duplicates[' Net Amount'] - multiple_transaction_no_duplicates['SUMIF Result']).round(3)

        # Extract matched document numbers and Level 1 remaining
        matched_document_numbers = matched_file['Voucher Nbr / RRN'].tolist()
        level_1_bank_remaining = bank_file_df[~bank_file_df['Voucher Nbr / RRN'].isin(matched_document_numbers)]
        level_1_sap_remaining = sap_file_df[~sap_file_df['Voucher Nbr / RRN'].isin(matched_document_numbers)]

        # Level 2 Matching
        level_1_sap_remaining.rename(columns={'Voucher Nbr / RRN': ' Auth Id'}, inplace=True)
        level_2_matched_file = pd.merge(level_1_bank_remaining, level_1_sap_remaining, on=' Auth Id', how='left')
        level_2_matched_file = level_2_matched_file[level_2_matched_file['Document Type'].notna()].copy()
        level_2_matched_file[' Net Amount'] = level_2_matched_file[' Net Amount'].astype(float)
        level_2_matched_file['Net Amount - Amount in Local currency'] = (
            level_2_matched_file[' Net Amount'] - level_2_matched_file['Amount in Local Currency']).round(3)

        # Perform SUMIF logic for Level 2 Match
        sum_values_lvl2 = level_1_sap_remaining.groupby(' Auth Id')['Amount in Local Currency'].sum()
        level_2_matched_file['SUMIF Result'] = level_2_matched_file[' Auth Id'].map(sum_values_lvl2)

        # Ensure no duplicates for SUMIF in Level 2
        multiple_transaction_no_duplicates_lvl2 = level_2_matched_file.drop_duplicates(subset=[' Auth Id'])[
            [' Auth Id', ' Net Amount', 'SUMIF Result']].copy()
        multiple_transaction_no_duplicates_lvl2['Difference'] = (
            multiple_transaction_no_duplicates_lvl2[' Net Amount'] - multiple_transaction_no_duplicates_lvl2['SUMIF Result']).round(3)
        
        # Save unmatched files
        matched_document_numbers_lvl2 = level_2_matched_file['Voucher Nbr / RRN'].tolist()
        level_2_bank_remaining = level_1_bank_remaining[~level_1_bank_remaining['Voucher Nbr / RRN'].isin(matched_document_numbers_lvl2)]
        level_2_sap_remaining = level_1_sap_remaining[~level_1_sap_remaining[' Auth Id'].isin(matched_document_numbers_lvl2)]

        # Generate downloadable Excel files
        with pd.ExcelWriter('Credit_Card_Reconciliation.xlsx', engine='openpyxl') as writer:
            matched_file.to_excel(writer, sheet_name='Level 1 Match', index=False)
            multiple_transaction_no_duplicates.to_excel(writer, sheet_name='Level 1 SUMIF', index=False)
            level_2_matched_file.to_excel(writer, sheet_name='Level 2 Match', index=False)
            multiple_transaction_no_duplicates_lvl2.to_excel(writer, sheet_name='Level 2 SUMIF', index=False)
            level_2_bank_remaining.to_excel(writer, sheet_name='Bank Remaining', index=False)
            level_2_sap_remaining.to_excel(writer, sheet_name='SAP Remaining', index=False)


        # Offer download link
        with open('Credit_Card_Reconciliation.xlsx', 'rb') as f:
            st.download_button(label="Download Reconciliation Report",
                               data=f,
                               file_name="Credit_Card_Reconciliation.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    except Exception as e:
        st.error(f"An error occurred during processing: {e}")
# Footer with Developer Info
st.markdown(
    """
    <div class="footer">
        Developed by <b>Edwin Benny</b>  
        📸 <a href="https://www.instagram.com/edwinbennypauly" target="_blank">Instagram</a> | 
        💻 <a href="https://github.com/edwinbennypauly" target="_blank">GitHub</a>
    </div>
    """,
    unsafe_allow_html=True,
)
