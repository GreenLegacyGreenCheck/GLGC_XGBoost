import utils
import models
from typing import Optional, Dict

# ──────────────────────────────────────────────
# 핵심 진단 로직 (logic.py)
# ──────────────────────────────────────────────

def calc_kpi(annual_tco2):
    grade = utils.calc_energy_grade(annual_tco2)
    return {
        "annual_emission_tco2": annual_tco2,
        "energy_grade": grade,
        "grade_table": utils.get_grade_table(),
        "note": "등급 구간은 서울 건물 자체 수집 데이터 사분위수 기준 적용"
    }

def compare_to_average(elec_kwh, annual_tco2, national_avg_tco2=None, industry_avg_tco2=None):
    fallback = round(utils.AVG_ELEC_KWH * models.CO2_PER_KWH * 12, 4)
    national_avg = national_avg_tco2 if national_avg_tco2 is not None else fallback
    industry_avg = industry_avg_tco2 if industry_avg_tco2 is not None else fallback

    zscore = round((elec_kwh - utils.AVG_ELEC_KWH) / (utils.STD_ELEC_KWH if utils.STD_ELEC_KWH else 1), 2)
    
    try:
        percentile_below = round((utils.DF_DATA["useQty_kwh"] < elec_kwh).mean() * 100, 1)
        rank_percentile = round(100 - percentile_below, 1)
    except:
        rank_percentile = 50.0

    diff_vs_industry = round((annual_tco2 - industry_avg) / industry_avg * 100, 1) if industry_avg else 0
    avg_label = f"서울 근린생활 시설 평균 대비 {abs(diff_vs_industry)}% {'낮음' if diff_vs_industry < 0 else '높음'}"

    # 진단 메시지
    message = f"동종업 상위 {rank_percentile}%에 해당해요. "
    message += "현재 수준을 잘 유지해보세요." if rank_percentile <= 30 else ("조금 더 노력하면 상위권 진입이 가능해요." if rank_percentile <= 60 else "감축 액션이 필요해요.")

    return {
        "national_avg_tco2": national_avg, "industry_avg_tco2": industry_avg,
        "my_emission_tco2": annual_tco2, "rank_percentile": rank_percentile,
        "avg_comparison_label": avg_label, "diagnosis_message": message
    }

def analyze_cause(elec_kwh, gas_mj, industry_avg_kwh=None):
    elec_em, gas_em, monthly_total, total = utils.calc_emission(elec_kwh, gas_mj)
    elec_ratio = round(elec_em / monthly_total * 100, 1) if monthly_total > 0 else 0
    gas_ratio = round(gas_em / monthly_total * 100, 1) if monthly_total > 0 else 0
    
    base_avg = industry_avg_kwh if industry_avg_kwh else utils.AVG_ELEC_KWH
    elec_vs_avg = round((elec_kwh - base_avg) / base_avg * 100, 1) if base_avg else 0
    gas_vs_avg = round(gas_ratio - models.ASSUMED_AVG_GAS_RATIO, 1)

    return {
        "total_emission_tco2": total,
        "by_energy_source": {
            "electricity": {"emission_tco2": elec_em, "ratio_percent": elec_ratio},
            "gas": {"emission_tco2": gas_em, "ratio_percent": gas_ratio}
        },
        "comparison_metrics": {"elec_vs_avg_percent": elec_vs_avg, "gas_vs_avg_percent": gas_vs_avg}
    }

def predict_trend(annual_tco2, monthly_change_percent):
    rate = (monthly_change_percent or 0) / 100
    predicted_tco2 = max(0.0, round(annual_tco2 * ((1 + rate) ** 3), 4))
    
    cur_g = utils.calc_energy_grade(annual_tco2)
    pre_g = utils.calc_energy_grade(predicted_tco2)
    
    return {
        "predicted_annual_tco2": predicted_tco2,
        "current_grade": cur_g, "predicted_grade": pre_g,
        "grade_changed": cur_g != pre_g
    }

def calc_reduction_goal(annual_tco2):
    curr_g = utils.calc_energy_grade(annual_tco2)
    grade_map = {"A": 0, "B": 1, "C": 2, "D": 3}
    idx = grade_map.get(curr_g, 3)
    
    table = utils.get_grade_table() # D, C, B, A 순서
    target_idx = max(0, idx - 1)
    target_tco2 = table[len(table)-1 - target_idx]["max"] if idx > 0 else annual_tco2
    
    remaining = max(0, annual_tco2 - target_tco2)
    return {"current_grade": curr_g, "target_grade": ["A","B","C","D"][target_idx], "remaining_reduction_tco2": remaining}

def calc_cost_saving(elec_kwh, gas_mj, goal_data, elec_ratio, gas_ratio):
    remaining = goal_data["remaining_reduction_tco2"]
    current_cost = round((elec_kwh * models.ELEC_PRICE_PER_KWH + float(gas_mj or 0) * models.GAS_PRICE_PER_MJ) * 12)
    
    if remaining <= 0: return {"current_annual_cost_krw": current_cost, "expected_saving_krw": 0, "annual_saving_label": "목표 달성"}
    
    saving = (remaining / 12 / models.CO2_PER_KWH * models.ELEC_PRICE_PER_KWH * 12) # 단순화된 계산식
    return {"current_annual_cost_krw": current_cost, "expected_saving_krw": round(saving), "annual_saving_label": f"연간 약 {round(saving/10000)}만원 절감"}

def calc_esg_score(elec_kwh, gas_mj, answers):
    # (기존 calc_esg_score 로직 그대로 이식)
    return {"status_label": "양호"} # 예시 반환값

def diagnose(elec_kwh, gas_mj=None, device_usage=None, national_avg_tco2=None, industry_avg_tco2=None, 
             industry_avg_kwh=None, esg_answers=None, prev_elec_kwh=None, prev_gas_mj=None):
    
    _, _, _, annual_total = utils.calc_emission(elec_kwh, gas_mj)
    
    # 전월 대비 계산
    if prev_elec_kwh:
        _, _, _, prev_total = utils.calc_emission(prev_elec_kwh, prev_gas_mj)
        change_rate = (annual_total - prev_total) / prev_total * 100 if prev_total > 0 else 0
    else:
        change_rate = 0

    cause = analyze_cause(elec_kwh, gas_mj, industry_avg_kwh)
    goal = calc_reduction_goal(annual_total)
    
    return {
        "kpi": calc_kpi(annual_total),
        "average_comparison": compare_to_average(elec_kwh, annual_total, national_avg_tco2, industry_avg_tco2),
        "cause_analysis": cause,
        "trend_prediction": predict_trend(annual_total, change_rate),
        "reduction_goal": goal,
        "cost_saving": calc_cost_saving(elec_kwh, gas_mj, goal, 
                                        cause["by_energy_source"]["electricity"]["ratio_percent"],
                                        cause["by_energy_source"]["gas"]["ratio_percent"])
    }