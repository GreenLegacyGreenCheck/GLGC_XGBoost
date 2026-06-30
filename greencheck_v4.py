"""
GreenCheck - 탄소 배출 원인 분석 + ESG 자가진단 모듈

[하는 일]
1. 전기/가스 중 뭐가 배출에 더 영향을 줬는지, 기기별로는 뭐가 많이 썼는지 계산
2. ESG 점수(환경/사회/지배구조) 100점 만점으로 계산

[참고]
- 점수 계산은 머신러닝(XGBoost)이 아니라 단순 비교/평균 계산임
- ESG 환경(E) 점수는 K-ESG 가이드라인(산업통상자원부) 기준 적용
- 동종업 평균 데이터가 공식적으로 없어서, 우리가 수집한 서울 건물
  1,505개 평균(real_energy_data.csv)으로 임시 대체 중
- 기기별(냉방/조명) 사용량은 OCR로 고지서에서 읽어온다고 가정
"""

import json
import pandas as pd

# 배출계수 (공식 수치, 바꾸지 말 것)
CO2_PER_KWH = 0.4541 / 1000   # 전기 1kWh → 탄소 배출량
CO2_PER_MJ = 0.002176          # 가스 1MJ → 탄소 배출량
MJ_PER_KWH = 3.6                # 전기 1kWh = 3.6MJ (에너지 단위 통일용)

# 서울 건물 실측 평균 (비교 기준값)
df = pd.read_csv("real_energy_data.csv")
AVG_ELEC_KWH = df["useQty_kwh"].mean()
STD_ELEC_KWH = df["useQty_kwh"].std()

# ESG 설문 문항 (5점 척도: 1=전혀아니다 ~ 5=매우그렇다)
ESG_QUESTIONS = {
    "E": [
        {"code": "E-1-2", "question": "에너지 절감 노력을 하고 있습니까?"},
        {"code": "E-6-1", "question": "폐기물 관리를 하고 있습니까?"}
    ],
    "S": [
        {"code": "S-근로조건", "question": "직원 근로조건을 잘 지키고 있습니까?"},
        {"code": "S-지역사회", "question": "지역사회에 기여하고 있습니까?"}
    ],
    "G": [
        {"code": "G-4-1", "question": "사업 관련 법규를 잘 지키고 있습니까?"},
        {"code": "G-정보관리", "question": "고객 정보를 안전하게 관리하고 있습니까?"}
    ]
}


def analyze_cause(elec_kwh, gas_mj, device_usage=None, industry_avg=None):
    """전기/가스 중 뭐가 배출 많이 했는지, 기기별로 뭐 많이 썼는지 계산"""

    # 전기/가스 각각 탄소 배출량 계산
    elec_emission = elec_kwh * CO2_PER_KWH
    gas_emission = (gas_mj or 0) * CO2_PER_MJ
    total_emission = elec_emission + gas_emission

    # 전기 vs 가스 비율 (%)
    elec_ratio = round(elec_emission / total_emission * 100, 1) if total_emission else 0
    gas_ratio = round(gas_emission / total_emission * 100, 1) if total_emission else 0

    # 기기별(냉방/조명 등) 비율 계산
    device_ratio = {}
    if device_usage:
        total_device = sum(device_usage.values())
        for device, usage in device_usage.items():
            device_ratio[device] = round(usage / total_device * 100, 1)

    # 동종업 평균과 비교 (없으면 우리 수집 데이터 평균 사용)
    base_avg = industry_avg if industry_avg else AVG_ELEC_KWH
    diff_percent = round((elec_kwh - base_avg) / base_avg * 100, 1)

    return {
        "total_emission_tco2": round(total_emission, 3),
        "elec_ratio_percent": elec_ratio,
        "gas_ratio_percent": gas_ratio,
        "device_ratio_percent": device_ratio,
        "industry_avg_kwh": round(base_avg, 1),
        "is_official_avg": industry_avg is not None,
        "diff_from_avg_percent": diff_percent
    }


def calc_survey_score(answers):
    """1~5점 응답 평균내서 100점 만점으로 환산"""
    if not answers:
        return None
    avg_score = sum(answers.values()) / len(answers)
    return round(avg_score / 5 * 100, 1)


def stage_score(value, mean, std):
    """평균보다 적으면 100점, 비슷하면 50점, 많으면 0점"""
    z = (value - mean) / std
    if z < -0.1:
        return 100
    elif z <= 0.1:
        return 50
    return 0


def calc_e_score(elec_kwh, gas_mj, e_answers):
    """환경(E) 점수 = 온실가스 자동점수 + 에너지 자동점수 + 설문점수 평균"""

    emission_score = stage_score(
        elec_kwh * CO2_PER_KWH + (gas_mj or 0) * CO2_PER_MJ,
        AVG_ELEC_KWH * CO2_PER_KWH,
        STD_ELEC_KWH * CO2_PER_KWH
    )
    energy_score = stage_score(
        elec_kwh * MJ_PER_KWH + (gas_mj or 0),
        AVG_ELEC_KWH * MJ_PER_KWH,
        STD_ELEC_KWH * MJ_PER_KWH
    )
    survey_score = calc_survey_score(e_answers)

    scores = [s for s in [emission_score, energy_score, survey_score] if s is not None]
    final_score = round(sum(scores) / len(scores), 1) if scores else None

    return {
        "emission_score": emission_score,
        "energy_score": energy_score,
        "survey_score": survey_score,
        "final_score": final_score
    }


def diagnose(elec_kwh, gas_mj, device_usage=None, industry_avg=None, esg_answers=None):
    """원인 분석 + ESG 점수 한번에 계산해서 반환"""

    esg_answers = esg_answers or {}
    e_answers = {k: v for k, v in esg_answers.items() if k.startswith("E-")}
    s_answers = {k: v for k, v in esg_answers.items() if k.startswith("S-")}
    g_answers = {k: v for k, v in esg_answers.items() if k.startswith("G-")}

    return {
        "cause_analysis": analyze_cause(elec_kwh, gas_mj, device_usage, industry_avg),
        "esg_score": {
            "E": calc_e_score(elec_kwh, gas_mj, e_answers),
            "S": calc_survey_score(s_answers),
            "G": calc_survey_score(g_answers)
        }
    }


# 테스트
if __name__ == "__main__":
    result = diagnose(
        elec_kwh=356.2,
        gas_mj=42.7 * 43.1,
        device_usage={"cooling": 150.0, "lighting": 80.0, "etc": 126.2},
        industry_avg=None,
        esg_answers={
            "E-1-2": 4, "E-6-1": 3,
            "S-근로조건": 5, "S-지역사회": 4,
            "G-4-1": 5, "G-정보관리": 4
        }
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))