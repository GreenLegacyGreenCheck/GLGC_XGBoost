"""
GreenCheck - 탄소 배출 원인 분석 + ESG 자가진단 API 서버

[역할]
diagnose() 함수를 POST /diagnose 엔드포인트로 노출.
백엔드가 이 URL로 JSON을 보내면 원인 분석 + ESG 점수를 계산해서 반환.

[로컬 실행]
uvicorn main:app --reload --port 8000

[배포 후 호출 예시]
POST https://{서비스주소}/diagnose
Content-Type: application/json
"""

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, Dict
import json
import pandas as pd

app = FastAPI(title="GreenCheck XGBoost/ESG API")

# ──────────────────────────────────────────────
# 기존 greencheck_v4.py 로직 (배출계수, 기준값, 함수들)
# ──────────────────────────────────────────────

CO2_PER_KWH = 0.4541 / 1000
CO2_PER_MJ = 0.002176
MJ_PER_KWH = 3.6

df = pd.read_csv("real_energy_data.csv")
AVG_ELEC_KWH = df["useQty_kwh"].mean()
STD_ELEC_KWH = df["useQty_kwh"].std()

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


def analyze_cause(elec_kwh, gas_mj, device_usage=None, industry_avg=None):
    elec_emission = elec_kwh * CO2_PER_KWH
    gas_emission = (gas_mj or 0) * CO2_PER_MJ
    total_emission = elec_emission + gas_emission

    elec_ratio = round(elec_emission / total_emission * 100, 1) if total_emission else 0
    gas_ratio = round(gas_emission / total_emission * 100, 1) if total_emission else 0

    device_ratio = {}
    if device_usage:
        total_device = sum(device_usage.values())
        for device, usage in device_usage.items():
            device_ratio[device] = round(usage / total_device * 100, 1) if total_device else 0

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


def calc_e_score(elec_kwh, gas_mj, e_answers):
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


def diagnose(elec_kwh, gas_mj=None, device_usage=None, industry_avg=None, esg_answers=None):
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


# ──────────────────────────────────────────────
# API 엔드포인트
# ──────────────────────────────────────────────

class DiagnoseRequest(BaseModel):
    elec_kwh: float
    gas_mj: Optional[float] = None
    device_usage: Optional[Dict[str, float]] = None
    industry_avg: Optional[float] = None
    esg_answers: Optional[Dict[str, int]] = None


@app.get("/")
def health_check():
    """서버 살아있는지 확인용"""
    return {"status": "ok", "service": "GreenCheck XGBoost/ESG API"}


@app.post("/xgboost-diagnose")
def diagnose_endpoint(req: DiagnoseRequest):
    """원인 분석 + ESG 점수 계산"""
    result = diagnose(
        elec_kwh=req.elec_kwh,
        gas_mj=req.gas_mj,
        device_usage=req.device_usage,
        industry_avg=req.industry_avg,
        esg_answers=req.esg_answers
    )
    return result


@app.get("/esg-questions")
def get_esg_questions():
    """ESG 설문 문항 조회 (프론트엔드용)"""
    return ESG_QUESTIONS
