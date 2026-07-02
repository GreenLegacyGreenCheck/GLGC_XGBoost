import pandas as pd
from models import CO2_PER_KWH, CO2_PER_MJ

AVG_ELEC_KWH = 100.0
STD_ELEC_KWH = 50.0
Q1, Q2, Q3 = 1.5, 2.3, 3.0
DF_DATA = pd.DataFrame()

def initialize_data():
    global AVG_ELEC_KWH, STD_ELEC_KWH, Q1, Q2, Q3, DF_DATA
    try:
        df = pd.read_csv("real_energy_data.csv")
        DF_DATA = df
        AVG_ELEC_KWH = float(df["useQty_kwh"].mean())
        STD_ELEC_KWH = float(df["useQty_kwh"].std())
        annual_tco2 = (df.groupby(['sigunguCd', 'bjdongCd', 'bun'])['useQty_kwh'].mean() * 12) * CO2_PER_KWH
        Q1, Q2, Q3 = round(float(annual_tco2.quantile(0.25)), 4), round(float(annual_tco2.quantile(0.50)), 4), round(float(annual_tco2.quantile(0.75)), 4)
    except Exception as e:
        print(f"데이터 로드 실패: {e}")

def get_grade_table():
    return [
        {"grade": "D", "range": f"{Q3}~", "min": Q3, "max": None},
        {"grade": "C", "range": f"{Q2}~{Q3}", "min": Q2, "max": Q3},
        {"grade": "B", "range": f"{Q1}~{Q2}", "min": Q1, "max": Q2},
        {"grade": "A", "range": f"0~{Q1}", "min": 0.0, "max": Q1}
    ]

def calc_energy_grade(annual_tco2):
    if annual_tco2 <= Q1: return "A"
    if annual_tco2 <= Q2: return "B"
    if annual_tco2 <= Q3: return "C"
    return "D"

def calc_emission(elec_kwh, gas_mj):
    elec_val, gas_val = float(elec_kwh), float(gas_mj or 0.0)
    elec_em = elec_val * CO2_PER_KWH
    gas_em = gas_val * CO2_PER_MJ
    monthly = elec_em + gas_em
    return round(elec_em, 4), round(gas_em, 4), round(monthly, 4), round(monthly * 12, 4)