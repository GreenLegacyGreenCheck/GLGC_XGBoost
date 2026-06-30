import requests
import pandas as pd
import time
import xml.etree.ElementTree as ET

"""
GreenCheck - 서울 건물 실측 전기 사용량 수집 코드

[하는 일]
건축HUB 건물에너지 API로 서울 전체 법정동을 순회하며
각 동의 번지(1~199번)별 전기 사용량을 수집해 CSV로 저장.

[수집 범위]
- 지역: 서울 전체 법정동 (국토교통부 법정동코드 기준)
- 기간: TARGET_MONTHS에 지정된 월 (현재 2024년 1~12월로 설정됨)
- 번지: 1~199번 (200 이상은 미수집)

[주의]
- 1개월 분량(서울 전체, 번지 1~199) 수집에 약 12시간 소요됨
- 현재 코드대로 12개월 전체를 돌리면 약 144시간 소요 → 비현실적
- 실행 전 TARGET_MONTHS 범위를 줄여서 사용할 것
  (예: 분기별 1,4,7,10월만 수집하거나, 운영계정 한도 내에서 조정)
- API 일일 호출 한도로 인해 1회 실행에 끝나지 않을 수 있음
- 중단되어도 매 동(動)마다 CSV에 중간 저장되므로 데이터 손실 최소화
- 결과 파일: real_energy_data.csv (누적 저장, 재실행 시 덮어씀에 주의)
"""

BUILDING_API_KEY = "c040623fd5e96873ed9de880c3c86001d313da5be7f7691528afe0a17e4996aa"

# 수집할 연월 리스트 (2024년 1~12월)
TARGET_MONTHS = [f"2024{str(m).zfill(2)}" for m in range(1, 13)]

df_code = pd.read_csv("국토교통부_법정동코드_20250805.csv", encoding="cp949")

seoul = df_code[
    (df_code['법정동코드'].astype(str).str.startswith('11')) &
    (df_code['폐지여부'] == '존재') &
    (df_code['법정동코드'].astype(str).str[-5:] != '00000')
].copy()

seoul['sigunguCd'] = seoul['법정동코드'].astype(str).str[:5]
seoul['bjdongCd'] = seoul['법정동코드'].astype(str).str[5:]

print(f"서울 법정동 수: {len(seoul)}개")
print(f"수집 대상 월: {TARGET_MONTHS}")

results = []
for use_ym in TARGET_MONTHS:
    print(f"\n=== {use_ym} 수집 시작 ===")
    for _, row in seoul.iterrows():
        for bun in [str(i).zfill(4) for i in range(1, 200)]:
            url = "https://apis.data.go.kr/1613000/BldEngyHubService/getBeElctyUsgInfo"
            params = {
                "serviceKey": BUILDING_API_KEY,
                "sigunguCd": row['sigunguCd'],
                "bjdongCd": row['bjdongCd'],
                "platGbCd": "0",
                "bun": bun,
                "ji": "0000",
                "useYm": use_ym,
                "numOfRows": "100",
                "pageNo": "1"
            }
            try:
                response = requests.get(url, params=params, timeout=5)
                root = ET.fromstring(response.text)
                items = root.findall(".//item")
                for item in items:
                    use_qty = item.find("useQty")
                    if use_qty is not None:
                        results.append({
                            "sigunguCd": row['sigunguCd'],
                            "bjdongCd": row['bjdongCd'],
                            "dong_name": row['법정동명'],
                            "bun": bun,
                            "useYm": use_ym,
                            "useQty_kwh": float(use_qty.text)
                        })
            except:
                pass
            time.sleep(0.1)

        if results:
            print(f"{row['법정동명']} ({use_ym}): 누적 {len(results)}개")

        # 중간 저장 (혹시 중단돼도 손실 없게)
        df_result = pd.DataFrame(results)
        df_result.to_csv("real_energy_data.csv", index=False)

print(f"\n총 {len(results)}개 수집 완료! (수집 월: {len(TARGET_MONTHS)}개월)")