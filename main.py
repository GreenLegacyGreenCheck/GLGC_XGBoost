"""
GreenCheck - 탄소 배출 진단 종합 API 서버 (XGBoost/SHAP 담당 파트)

[역할]
탄소배출 진단 보고서 화면에 필요한 모든 숫자 데이터를 계산해서 반환.

[제외 항목 - LLM/RAG 담당]
- AI 종합 의견 텍스트
- AI 분석 근거 자연어 문장
- Before/After 시뮬레이션 (1도/2도/3도 감축 액션)

[중요 - 공신력 명시]
- 에너지 등급 구간(A:0~1.5, B:1.5~2.3, C:2.3~3, D:3~4 tCO2eq/년)은 팀 자체 설정값
- 전국/동종업 평균은 공식 통계 부재로 자체 수집 데이터(서울 건물 1,505건) 대체
- 냉방/가스 평균 비중 30%는 공식 통계 없는 자체 가정치
- 3개월 추세 예측은 현재 변화율 유지 단순 가정

[로컬 실행]
uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, Dict
import pandas as pd

app = FastAPI(title="GreenCheck XGBoost/ESG API")

# ──────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────
CO2_PER_KWH = 0.4541 / 1000
CO2_PER_MJ = 0.002176
MJ_PER_KWH = 3.6
ELEC_PRICE_PER_KWH = 150
GAS_PRICE_PER_MJ = 20
ASSUMED_AVG_COOLING_RATIO = 30.0
ASSUMED_AVG_GAS_RATIO = 30.0

df = pd.read_csv("real_energy_data.csv")
AVG_ELEC_KWH = df["useQty_kwh"].mean()
STD_ELEC_KWH = df["useQty_kwh"].std()

# 사분위수 기반 에너지 등급 구간 (자체 수집 데이터 기반, 공식 근거 없음)
# tCO2eq/년 기준으로 환산 (월간 kWh → 연간 tCO2eq)
Q1 = round(df["useQty_kwh"].quantile(0.25) * CO2_PER_KWH * 12, 3)
Q2 = round(df["useQty_kwh"].quantile(0.50) * CO2_PER_KWH * 12, 3)
Q3 = round(df["useQty_kwh"].quantile(0.75) * CO2_PER_KWH * 12, 3)

GRADE_THRESHOLDS = [
    (Q1, "A"),   # 하위 25% 미만 → 우수
    (Q2, "B"),   # 25~50% → 양호
    (Q3, "C"),   # 50~75% → 보통
]

# 등급 기준표 (프론트 기준표 표시용)
GRADE_TABLE = [
    {"grade": "D", "range": f"{Q3}~", "min": Q3, "max": None},
    {"grade": "C", "range": f"{Q2}~{Q3}", "min": Q2, "max": Q3},
    {"grade": "B", "range": f"{Q1}~{Q2}", "min": Q1, "max": Q2},
    {"grade": "A", "range": f"0~{Q1}", "min": 0.0, "max": Q1}
]

ESG_QUESTIONS = {
    "E": [
        {"code": "E-1-2", "question": "에너지 절감 노력(설비 점검, 절전 등)을 하고 있습니까?"},
        {"code": "E-6-1", "question": "폐기물 관리(분리수거, 일회용품 절감 등)를 하고 있습니까?"}
    ],
    "S": [
        {"code": "S-근로조건", "question": "직원 근로조건(4대보험, 정당한 급여 등)을 준수하고 있습니까?"},
        {"code": "S-지역사회", "question": "지역사회 기여(지역 농산물 사용, 지역 행사 참여 등)를 하고 있습니까?"}
    ],
    "G": [
        {"code": "G-4-1", "question": "사업 운영 관련 법규(세금 신고, 영업 인허가 등)를 준수하고 있습니까?"},
        {"code": "G-정보관리", "question": "고객 정보(개인정보, 결제정보)를 안전하게 관리하고 있습니까?"}
    ]
}


# ──────────────────────────────────────────────
# 공통 함수
# ──────────────────────────────────────────────
def calc_energy_grade(annual_tco2):
    for threshold, grade in GRADE_THRESHOLDS:
        if annual_tco2 <= threshold:
            return grade
    return "D"  # Q3 초과 → D


def calc_emission(elec_kwh, gas_mj):
    elec_emission = elec_kwh * CO2_PER_KWH
    gas_emission = (gas_mj or 0) * CO2_PER_MJ
    monthly_total = elec_emission + gas_emission
    annual_total = round(monthly_total * 12, 3)
    return round(elec_emission, 3), round(gas_emission, 3), round(monthly_total, 3), annual_total


# ──────────────────────────────────────────────
# 1. 핵심 KPI (연간 배출량 + 에너지 등급)
# ──────────────────────────────────────────────
def calc_kpi(annual_tco2):
    grade = calc_energy_grade(annual_tco2)
    return {
        "annual_emission_tco2": annual_tco2,
        "energy_grade": grade,
        "grade_table": GRADE_TABLE,  # 등급 기준표 (프론트 막대 표시용)
        "note": "등급 구간은 공식 기관 기준이 아닌 자체 설정값"
    }


# ──────────────────────────────────────────────
# 2. 평균 비교
# ──────────────────────────────────────────────
def compare_to_average(elec_kwh, annual_tco2, national_avg_tco2=None, industry_avg_tco2=None):
    fallback = round(AVG_ELEC_KWH * CO2_PER_KWH * 12, 3)
    national_avg = national_avg_tco2 if national_avg_tco2 is not None else fallback
    industry_avg = industry_avg_tco2 if industry_avg_tco2 is not None else fallback

    zscore = round((elec_kwh - AVG_ELEC_KWH) / STD_ELEC_KWH, 2)
    percentile_below = round((df["useQty_kwh"] < elec_kwh).mean() * 100, 1)
    rank_percentile = round(100 - percentile_below, 1)

    diff_vs_national = round((annual_tco2 - national_avg) / national_avg * 100, 1) if national_avg else None
    diff_vs_industry = round((annual_tco2 - industry_avg) / industry_avg * 100, 1) if industry_avg else None

    # 진단 메시지 (규칙 기반)
    if rank_percentile <= 30:
        message = f"동종업 상위 {rank_percentile}%에 해당해요. 현재 수준을 잘 유지해보세요."
    elif rank_percentile <= 60:
        message = f"동종업 상위 {rank_percentile}%에 해당해요. 조금 더 노력하면 상위권 진입이 가능해요."
    else:
        message = f"동종업 상위 {rank_percentile}%에 해당해요. 감축 액션이 필요해요."

    # 평균 대비 라벨
    if diff_vs_industry is not None:
        if diff_vs_industry < 0:
            avg_label = f"서울 근린생활 시설 평균 대비 {abs(diff_vs_industry)}% 낮음"
        else:
            avg_label = f"서울 근린생활 시설 평균 대비 {diff_vs_industry}% 높음"
    else:
        avg_label = None

    return {
        "national_avg_tco2": national_avg,
        "industry_avg_tco2": industry_avg,
        "my_emission_tco2": annual_tco2,
        "is_official_national_avg": national_avg_tco2 is not None,
        "is_official_industry_avg": industry_avg_tco2 is not None,
        "diff_vs_national_percent": diff_vs_national,
        "diff_vs_industry_percent": diff_vs_industry,
        "avg_comparison_label": avg_label,
        "zscore": zscore,
        "rank_percentile": rank_percentile,
        "diagnosis_message": message
    }


# ──────────────────────────────────────────────
# 3+4. 에너지원별 배출량 + 원인 분석
# ──────────────────────────────────────────────
def analyze_cause(elec_kwh, gas_mj, device_usage, industry_avg_kwh=None):
    elec_emission = elec_kwh * CO2_PER_KWH
    gas_emission = (gas_mj or 0) * CO2_PER_MJ
    total_emission = elec_emission + gas_emission

    elec_ratio = round(elec_emission / total_emission * 100, 1) if total_emission else 0
    gas_ratio = round(gas_emission / total_emission * 100, 1) if total_emission else 0

    device_usage = device_usage or {}
    cooling = device_usage.get("cooling", 0)
    lighting_etc = sum(v for k, v in device_usage.items() if k != "cooling")
    total_device = cooling + lighting_etc

    cooling_ratio = round(cooling / total_device * 100, 1) if total_device else 0
    lighting_etc_ratio = round(lighting_etc / total_device * 100, 1) if total_device else 0

    base_avg = industry_avg_kwh if industry_avg_kwh else AVG_ELEC_KWH
    elec_vs_avg = round((elec_kwh - base_avg) / base_avg * 100, 1) if base_avg else 0
    cooling_vs_avg = round(cooling_ratio - ASSUMED_AVG_COOLING_RATIO, 1)
    gas_vs_avg = round(gas_ratio - ASSUMED_AVG_GAS_RATIO, 1)

    # 순위별 기여 요인
    factors = [
        {"factor": "전기 사용량", "value_percent": elec_vs_avg},
        {"factor": "냉방기 사용", "value_percent": cooling_vs_avg},
        {"factor": "가스 사용량", "value_percent": gas_vs_avg}
    ]
    ranked = sorted(factors, key=lambda x: abs(x["value_percent"]), reverse=True)
    for i, f in enumerate(ranked, start=1):
        f["rank"] = i

    return {
        "total_emission_tco2": round(total_emission, 3),
        "by_energy_source": {
            "electricity": {
                "emission_tco2": round(elec_emission, 3),
                "ratio_percent": elec_ratio,
                "label": f"{round(elec_emission, 2)} tCO₂e ({elec_ratio}%)"
            },
            "gas": {
                "emission_tco2": round(gas_emission, 3),
                "ratio_percent": gas_ratio,
                "label": f"{round(gas_emission, 2)} tCO₂e ({gas_ratio}%)"
            }
        },
        "comparison_metrics": {
            "elec_vs_avg_percent": elec_vs_avg,
            "cooling_vs_avg_percent": cooling_vs_avg,
            "gas_vs_avg_percent": gas_vs_avg,
            "note": "냉방/가스 평균 비중 30%는 공식 통계 부재로 인한 자체 가정치"
        },
        "ranked_factors": ranked
    }


# ──────────────────────────────────────────────
# 5. 전월 대비 비교
# ──────────────────────────────────────────────
def compare_to_previous_month(elec_kwh, gas_mj, prev_elec_kwh=None, prev_gas_mj=None):
    if prev_elec_kwh is None:
        return None

    _, _, current_total, _ = calc_emission(elec_kwh, gas_mj)
    _, _, prev_total, _ = calc_emission(prev_elec_kwh, prev_gas_mj)

    emission_change = round((current_total - prev_total) / prev_total * 100, 1) if prev_total else None
    elec_change = round((elec_kwh - prev_elec_kwh) / prev_elec_kwh * 100, 1) if prev_elec_kwh else None
    gas_change = None
    if prev_gas_mj and gas_mj:
        gas_change = round((gas_mj - prev_gas_mj) / prev_gas_mj * 100, 1)

    return {
        "electricity": {
            "previous_kwh": prev_elec_kwh,
            "current_kwh": elec_kwh,
            "change_percent": elec_change,
            "direction": "증가" if (elec_change or 0) > 0 else "감소"
        },
        "carbon_emission": {
            "previous_tco2": prev_total,
            "current_tco2": current_total,
            "change_percent": emission_change,
            "direction": "증가" if (emission_change or 0) > 0 else "감소"
        },
        "gas_usage_change_percent": gas_change
    }


# ──────────────────────────────────────────────
# 6. 추세 예측 (현재유지 시 3개월 후 등급 변화 포함)
# ──────────────────────────────────────────────
def predict_trend(annual_tco2, current_grade, monthly_change_percent=None):
    if monthly_change_percent is None:
        monthly_change_percent = 0

    rate = monthly_change_percent / 100
    predicted_tco2 = round(annual_tco2 * ((1 + rate) ** 3), 3)
    predicted_grade = calc_energy_grade(predicted_tco2)

    return {
        "assumption": "현재 변화율이 3개월간 동일하게 유지된다고 가정한 단순 추정치",
        "keep_current": {
            "predicted_annual_tco2": predicted_tco2,
            "current_grade": current_grade,        # 현재 등급 (예: "B")
            "predicted_grade": predicted_grade,    # 3개월 후 예상 등급 (예: "B")
            "grade_change": f"{current_grade} → {predicted_grade}",  # 등급 변화 표시
            "grade_changed": current_grade != predicted_grade         # 등급 변화 여부
        },
        "grade_table": GRADE_TABLE
    }


# ──────────────────────────────────────────────
# 8. 절감 목표 및 진행률
# ──────────────────────────────────────────────
def calc_reduction_goal(annual_tco2):
    current_grade = calc_energy_grade(annual_tco2)
    grade_order = ["A", "B", "C", "D", "E"]
    current_idx = grade_order.index(current_grade)

    if current_idx == 0:
        target_tco2 = annual_tco2
        target_grade = "A"
    else:
        target_grade = grade_order[current_idx - 1]
        target_tco2 = GRADE_THRESHOLDS[current_idx - 1][0]

    remaining = round(annual_tco2 - target_tco2, 3)
    progress = round((1 - remaining / annual_tco2) * 100, 1) if annual_tco2 else 0
    progress = max(0, min(100, progress))

    return {
        "current_annual_tco2": annual_tco2,
        "current_grade": current_grade,
        "target_annual_tco2": target_tco2,
        "target_grade": target_grade,
        "remaining_reduction_tco2": max(0, remaining),
        "progress_percent": progress,
        "status": "목표 달성" if remaining <= 0 else "진행 중"
    }


# ──────────────────────────────────────────────
# 9. 절감 예상 비용
# ──────────────────────────────────────────────
def calc_cost_saving(elec_kwh, gas_mj, reduction_goal, elec_ratio_percent, gas_ratio_percent):
    remaining_tco2 = reduction_goal["remaining_reduction_tco2"]
    current_annual_cost = round(
        (elec_kwh * ELEC_PRICE_PER_KWH + (gas_mj or 0) * GAS_PRICE_PER_MJ) * 12
    )

    if remaining_tco2 <= 0:
        return {
            "current_annual_cost_krw": current_annual_cost,
            "expected_annual_cost_krw": current_annual_cost,
            "expected_saving_krw": 0,
            "annual_saving_label": "이미 목표 등급 달성",
            "note": "이미 목표 등급을 달성한 상태"
        }

    reduction_from_elec = remaining_tco2 * (elec_ratio_percent / 100)
    reduction_from_gas = remaining_tco2 * (gas_ratio_percent / 100)

    saving_elec = (reduction_from_elec / 12 / CO2_PER_KWH) * ELEC_PRICE_PER_KWH * 12 if elec_ratio_percent else 0
    saving_gas = (reduction_from_gas / 12 / CO2_PER_MJ) * GAS_PRICE_PER_MJ * 12 if gas_ratio_percent else 0

    expected_saving_krw = min(round(saving_elec + saving_gas), current_annual_cost)
    expected_annual_cost = current_annual_cost - expected_saving_krw

    # "연간 약 N만원 절감" 라벨
    saving_manwon = round(expected_saving_krw / 10000)
    annual_saving_label = f"연간 약 {saving_manwon}만원 절감"

    return {
        "current_annual_cost_krw": current_annual_cost,
        "expected_annual_cost_krw": expected_annual_cost,
        "expected_saving_krw": expected_saving_krw,
        "annual_saving_label": annual_saving_label,
        "note": "전기/가스 단가 기준 단순 환산 추정치 (실제 요금제에 따라 달라질 수 있음)"
    }


# ──────────────────────────────────────────────
# 10. ESG 점수
# ──────────────────────────────────────────────
def calc_survey_score(answers):
    if not answers:
        return None
    avg_score = sum(answers.values()) / len(answers)
    return round(avg_score / 5 * 100, 1)


def stage_score(value, mean, std):
    z = (value - mean) / std
    if z < -0.1:
        return 100
    elif z <= 0.1:
        return 50
    return 0


def calc_esg_score(elec_kwh, gas_mj, esg_answers):
    e_answers = {k: v for k, v in esg_answers.items() if k.startswith("E-")}
    s_answers = {k: v for k, v in esg_answers.items() if k.startswith("S-")}
    g_answers = {k: v for k, v in esg_answers.items() if k.startswith("G-")}

    emission_score = stage_score(
        elec_kwh * CO2_PER_KWH + (gas_mj or 0) * CO2_PER_MJ,
        AVG_ELEC_KWH * CO2_PER_KWH, STD_ELEC_KWH * CO2_PER_KWH
    )
    energy_score = stage_score(
        elec_kwh * MJ_PER_KWH + (gas_mj or 0),
        AVG_ELEC_KWH * MJ_PER_KWH, STD_ELEC_KWH * MJ_PER_KWH
    )
    e_survey = calc_survey_score(e_answers)
    e_scores = [s for s in [emission_score, energy_score, e_survey] if s is not None]
    e_final = round(sum(e_scores) / len(e_scores), 1) if e_scores else None

    s_score = calc_survey_score(s_answers)
    g_score = calc_survey_score(g_answers)

    # 종합 상태 라벨
    scores = [s for s in [e_final, s_score, g_score] if s is not None]
    avg_total = sum(scores) / len(scores) if scores else 0
    if avg_total >= 80:
        status_label = "우수"
    elif avg_total >= 60:
        status_label = "양호"
    elif avg_total >= 40:
        status_label = "보통"
    else:
        status_label = "개선 필요"

    return {
        "E": {
            "emission_score": emission_score,
            "energy_score": energy_score,
            "survey_score": e_survey,
            "final_score": e_final
        },
        "S": s_score,
        "G": g_score,
        "status_label": status_label
    }


# ──────────────────────────────────────────────
# 통합 진단 함수
# ──────────────────────────────────────────────
def diagnose(elec_kwh, gas_mj=None, device_usage=None,
             national_avg_tco2=None, industry_avg_tco2=None, industry_avg_kwh=None,
             esg_answers=None, prev_elec_kwh=None, prev_gas_mj=None):

    _, _, monthly_total, annual_total = calc_emission(elec_kwh, gas_mj)

    kpi = calc_kpi(annual_total)
    current_grade = kpi["energy_grade"]

    monthly_comparison = compare_to_previous_month(elec_kwh, gas_mj, prev_elec_kwh, prev_gas_mj)
    monthly_change_rate = monthly_comparison["carbon_emission"]["change_percent"] if monthly_comparison else None

    cause_result = analyze_cause(elec_kwh, gas_mj, device_usage, industry_avg_kwh)
    elec_ratio = cause_result["by_energy_source"]["electricity"]["ratio_percent"]
    gas_ratio = cause_result["by_energy_source"]["gas"]["ratio_percent"]

    reduction_goal = calc_reduction_goal(annual_total)
    cost_saving = calc_cost_saving(elec_kwh, gas_mj, reduction_goal, elec_ratio, gas_ratio)

    return {
        "kpi": kpi,
        "average_comparison": compare_to_average(elec_kwh, annual_total, national_avg_tco2, industry_avg_tco2),
        "cause_analysis": cause_result,
        "monthly_comparison": monthly_comparison,
        "trend_prediction": predict_trend(annual_total, current_grade, monthly_change_rate),
        "reduction_goal": reduction_goal,
        "cost_saving": cost_saving,
        "esg_score": calc_esg_score(elec_kwh, gas_mj, esg_answers or {})
    }


# ──────────────────────────────────────────────
# API 엔드포인트
# ──────────────────────────────────────────────

class DiagnoseRequest(BaseModel):
    elec_kwh: float
    gas_mj: Optional[float] = None
    device_usage: Optional[Dict[str, float]] = None
    national_avg_tco2: Optional[float] = None
    industry_avg_tco2: Optional[float] = None
    industry_avg_kwh: Optional[float] = None
    esg_answers: Optional[Dict[str, int]] = None
    prev_elec_kwh: Optional[float] = None
    prev_gas_mj: Optional[float] = None


@app.get("/")
def health_check():
    return {"status": "ok", "service": "GreenCheck XGBoost/ESG API"}


@app.post("/xgboost-diagnose")
def diagnose_endpoint(req: DiagnoseRequest):
    """탄소배출 진단 보고서 전체 항목 계산 (AI 문장/Before-After 시뮬레이션은 LLM/RAG 담당)"""
    return diagnose(
        elec_kwh=req.elec_kwh,
        gas_mj=req.gas_mj,
        device_usage=req.device_usage,
        national_avg_tco2=req.national_avg_tco2,
        industry_avg_tco2=req.industry_avg_tco2,
        industry_avg_kwh=req.industry_avg_kwh,
        esg_answers=req.esg_answers,
        prev_elec_kwh=req.prev_elec_kwh,
        prev_gas_mj=req.prev_gas_mj
    )


@app.get("/esg-questions")
def get_esg_questions():
    return ESG_QUESTIONS
