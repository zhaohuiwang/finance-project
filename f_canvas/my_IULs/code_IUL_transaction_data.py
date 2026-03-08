



"""
Pyhton code to process the Nationwide IUL transaction data resulting a pandas.The expected structure of the resulting DataFrame: 
>>> df.dtypes
effective               datetime64[ns]
processed               datetime64[ns]
type                            object
amount($)                      float64
is_interest                       bool
is_segment_fee                    bool
is_monthly_deduction              bool
is_payment                        bool
dtype: object
>>> 
Here are all the transactions for October 2025
09/15/2025	09/15/2025	Sweep - Segment Fee - One-Year Choice Plus NYSE® Zebra Edge® Index	($47.54)
09/15/2025	09/15/2025	Sweep - Segment Fee - One-Year Choice Plus J.P. Morgan Mozaic II℠ Index®	($46.61)    
09/15/2025	09/15/2025	Sweep - Segment Maturity Value Allocation - One-Year Choice Plus NYSE® Zebra Edge® Index	$3,759.57
09/15/2025	09/15/2025	Sweep - Segment Maturity Value Allocation - One-Year Choice Plus J.P. Morgan Mozaic II℠ Index®	$3,666.19
09/15/2025	09/15/2025	Sweep - Net Premium Allocation - One-Year Choice Plus NYSE® Zebra Edge® Index	$994.72
09/15/2025	09/15/2025	Sweep - Net Premium Allocation - One-Year Choice Plus J.P. Morgan Mozaic II℠ Index®	$994.72
09/15/2025	09/15/2025	Sweep - Minimum Required Fixed Interest Strategy Amount	$130.26
09/15/2025	09/15/2025	Sweep - Interest Credit to Segment - One-Year Choice Plus NYSE® Zebra Edge® Index	$0.00
09/15/2025	09/15/2025	Sweep - Interest Credit to Segment - One-Year Choice Plus J.P. Morgan Mozaic II℠ Index®	$0.00
09/13/2025	09/15/2025	Monthly Deduction	($137.05)
09/13/2025	09/15/2025	Payment	$2,255.00
"""


import pandas as pd

# Read the transactions data from a csv file into pandas dataframe
try:
    df = pd.read_csv("f_canvas/my_IULs/NW_IUL_transactions.csv")
except FileNotFoundError:
    print("File not found. Please check the file path.")

# Convert two variables from string to pandas.Datetime
df["effective"] = pd.to_datetime(df["effective"], format="%m/%d/%Y")
df["processed"] = pd.to_datetime(df["processed"], format="%m/%d/%Y")

# In the original records, there was '$' prefix for all values in the transaction amount records. All deductions and fees are in parenthesis (to different from payment, interest earened). This line removes the '$' prefix, takes out each of the value from the parenthesis and prefixs it with a '-' character. The resulting values are then converted from string type to float. 
df["amount($)"] = df["amount($)"].replace({'\\$': '', '\\(': '-', '\\)': '', ',': ''}, regex=True).astype(float)

# Create new boolean indicator variables 
df["is_interest"] = df["type"].str.contains("Interest Credit", case=True, na=False)
df["is_segment_fee"] = df["type"].str.contains("Segment Fee", case=True, na=False)

df["is_monthly_deduction"] = df["type"].str.contains("Monthly Deduction", case=True, na=False)

df["is_payment"] = df["type"].str.contains("Payment", case=True, na=False)


# Summarize each of the categories
df[df["is_interest"]].reset_index(drop=True)['amount($)'].sum()
# 3882
df[df["is_payment"]].reset_index(drop=True)['amount($)'].sum()
# 89311
df[df["is_segment_fee"]].reset_index(drop=True)['amount($)'].sum()
# -2105
df[df["is_monthly_deduction"]].reset_index(drop=True)['amount($)'].sum()
# -7175
# total deduction and fees
-2105 - 7175 = -9280
# interest and payment
3882 + 89311 = 93193
# balance money in - money out
93193 -9280 = 83913
89311 + 3882 -2105 - 7175
78643.44 - 83913 