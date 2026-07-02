from fastapi import FastAPI
from models import DiagnoseRequest, ESG_QUESTIONS
from utils import initialize_data
from logic import diagnose

app = FastAPI(title="GreenCheck XGBoost/ESG API")

# 서버 시작 시 데이터 로드
@app.on_event("startup")
async def startup_event():
    initialize_data()

@app.get("/")
def health_check():
    return {"status": "ok", "service": "GreenCheck XGBoost/ESG API"}

@app.post("/xgboost-diagnose")
def diagnose_endpoint(req: DiagnoseRequest):
    # 엔드포인트는 요청을 받고 -> 로직을 호출하고 -> 결과를 반환하는 역할만 수행
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