# 상수 및 pydantic 모델
from pydantic import BaseModel
from typing import Optional, Dict

CO2_PER_KWH = 0.4541 / 1000
CO2_PER_MJ = 0.002176
MJ_PER_KWH = 3.6
ELEC_PRICE_PER_KWH = 150
GAS_PRICE_PER_MJ = 20
ASSUMED_AVG_COOLING_RATIO = 30.0
ASSUMED_AVG_GAS_RATIO = 30.0

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