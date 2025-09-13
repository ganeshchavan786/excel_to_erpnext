import pandas as pd

def read_rows_from_buffer(filepath):
    """Read Excel/CSV file and return rows + columns."""
    try:
        if str(filepath).lower().endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            # Pandas स्वतः engine निवडेल (.xls साठी xlrd, .xlsx साठी openpyxl)
            df = pd.read_excel(filepath)
    except Exception as e:
        raise Exception(f"Unsupported or corrupt file: {str(e)}")

    df = df.fillna('')
    rows = df.to_dict('records')
    columns = list(df.columns)
    return rows, columns
