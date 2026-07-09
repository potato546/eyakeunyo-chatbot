# -*- coding: utf-8 -*-
"""
e약은요 + DUR(의약품안전사용서비스) 기반 약물 정보 챗봇 백엔드

기능 3가지
1. 성분명/제품명으로 약 정보 조회        -> e약은요(DrbEasyDrugInfoService)
2. 여러 약물 동시 입력 시 상호작용/부작용 -> DUR품목정보서비스(DURPrdlstInfoService03) 병용금기 등
3. 복용 횟수/일수 적합 여부              -> DUR 용량주의/투여기간주의 정보 + 규칙 기반 비교

주의:
- 이 코드는 공공데이터포털 문서 및 공개된 사용 사례를 바탕으로 작성되었습니다.
- DUR API의 세부 오퍼레이션 이름/응답 필드명 중 일부는 실제 Swagger 명세와
  다를 수 있으니, 처음 실행 후 /api/debug/raw 로 실제 응답을 꼭 확인하세요.
  (이 개발 환경 특성상 apis.data.go.kr에 직접 접속해 테스트할 수 없어서,
  실제 필드명은 사용자의 로컬 환경에서 1회 확인이 필요합니다.)
"""

import os
import re
import requests
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ------------------------------------------------------------------
# 설정
# ------------------------------------------------------------------
# data.go.kr은 보통 계정당 인증키 하나를 여러 API에 공용으로 씁니다.
# 만약 e약은요/DUR 인증키가 서로 다르게 발급됐다면 아래 두 값을 각각 채워주세요.
# 비워두면 자동으로 DATA_GO_KR_SERVICE_KEY(공통키)를 사용합니다.
SERVICE_KEY = os.environ.get("DATA_GO_KR_SERVICE_KEY", "")
EASY_DRUG_KEY = os.environ.get("DATA_GO_KR_EASY_KEY") or SERVICE_KEY
DUR_KEY = os.environ.get("DATA_GO_KR_DUR_KEY") or SERVICE_KEY
# 의약품 제품 허가정보 (전문+일반 의약품 모두 포함, e약은요에 없는 전문의약품 대응용)
PERMIT_KEY = os.environ.get("DATA_GO_KR_PERMIT_KEY") or SERVICE_KEY

EASY_DRUG_URL = "http://apis.data.go.kr/1471000/DrbEasyDrugInfoService/getDrbEasyDrugList"
DUR_BASE_URL = "http://apis.data.go.kr/1471000/DURPrdlstInfoService03"
# 서비스명 뒤 숫자(07 등)는 식약처가 주기적으로 버전업합니다.
# 만약 호출이 안 되면 data.go.kr에서 최신 서비스명을 확인해 이 값만 바꿔주세요.
DRUG_PERMIT_URL = "https://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService07/getDrugPrdtPrmsnInq07"

# DUR 오퍼레이션 목록 (일부는 실제 Swagger에서 이름 재확인 필요 - README 참고)
DUR_OPERATIONS = {
    "usjnt_taboo": "getUsjntTabooInfoList03",       # 병용금기 (확인됨)
    "age_taboo": "getSpcifyAgeTabooInfoList03",     # 특정연령대금기 (확인 필요)
    "pregnant_taboo": "getPwnmTabooInfoList03",     # 임부금기 (확인 필요)
    "capacity_atent": "getCpctyAtentInfoList03",    # 용량주의 (확인 필요)
    "period_atent": "getMdctnPdAtentInfoList03",    # 투여기간주의 (확인 필요)
    "elderly_atent": "getOdsnAtentInfoList03",      # 노인주의 (확인 필요)
    "efficacy_dup": "getEfcyDplctInfoList03",       # 효능군중복주의 (확인 필요)
}


# ------------------------------------------------------------------
# 공통 호출 함수
# ------------------------------------------------------------------
def _get(url, params, service_key, timeout=10):
    params = {**params, "serviceKey": service_key, "type": "json"}
    try:
        resp = requests.get(url, params=params, timeout=timeout)
    except requests.RequestException as e:
        return {"_http_error": True, "_status_code": None, "_raw_text": str(e)}
    if resp.status_code != 200:
        # 여기서 바로 예외를 던지지 않고, 실제 응답 본문을 그대로 담아 반환한다.
        # (data.go.kr이 403/500일 때 왜 막았는지 본문에 사유가 적혀있는 경우가 많음)
        return {
            "_http_error": True,
            "_status_code": resp.status_code,
            "_raw_text": resp.text[:2000],
        }
    try:
        data = resp.json()
    except ValueError:
        # 인증키 오류 등으로 XML 에러메시지가 오는 경우 대비
        return {"_raw_text": resp.text, "_parse_error": True}
    return data


def _extract_items(data):
    """OpenAPI 표준 응답 구조에서 item 리스트만 안전하게 뽑아낸다."""
    if not isinstance(data, dict):
        return []
    try:
        body = data["body"]
    except KeyError:
        try:
            body = data["response"]["body"]
        except Exception:
            return []
    items = body.get("items")
    if not items:
        return []
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    return items or []


def call_easy_drug(item_name=None, entp_name=None, num_of_rows=10):
    params = {"pageNo": 1, "numOfRows": num_of_rows}
    if item_name:
        params["itemName"] = item_name
    if entp_name:
        params["entpName"] = entp_name
    data = _get(EASY_DRUG_URL, params, EASY_DRUG_KEY)
    return _extract_items(data), data


def call_drug_permit(item_name=None, num_of_rows=5):
    params = {"pageNo": 1, "numOfRows": num_of_rows}
    if item_name:
        params["item_name"] = item_name  # 이 API는 item_name(스네이크케이스)인 경우가 많음 - 응답 없으면 itemName도 시도
    data = _get(DRUG_PERMIT_URL, params, PERMIT_KEY)
    items = _extract_items(data)
    if not items and item_name:
        # 파라미터 표기가 itemName일 수도 있어 한 번 더 시도
        params2 = {"pageNo": 1, "numOfRows": num_of_rows, "itemName": item_name}
        data = _get(DRUG_PERMIT_URL, params2, PERMIT_KEY)
        items = _extract_items(data)
    return items, data


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text):
    if not text:
        return text
    text = _TAG_RE.sub(" ", str(text))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _find_field(item, keywords):
    """필드명이 정확히 뭔지 확신할 수 없을 때, 키에 특정 키워드가 들어간 값을 찾아본다."""
    for k, v in item.items():
        if not v:
            continue
        key_lower = k.lower()
        if any(kw in key_lower for kw in keywords):
            return v
    return None



    operation = DUR_OPERATIONS[operation_key]
    url = f"{DUR_BASE_URL}/{operation}"
    params = {"pageNo": 1, "numOfRows": num_of_rows}
    if item_name:
        params["itemName"] = item_name
    data = _get(url, params, DUR_KEY)
    return _extract_items(data), data


# ------------------------------------------------------------------
# 1) 약 정보 조회
# ------------------------------------------------------------------
@app.route("/api/drug-info")
def drug_info():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "검색어(q)가 필요합니다."}), 400

    items, raw = call_easy_drug(item_name=query)
    if items:
        results = []
        for it in items:
            results.append({
                "source": "e약은요 (일반의약품)",
                "entpName": it.get("entpName"),
                "itemName": it.get("itemName"),
                "itemSeq": it.get("itemSeq"),
                "efficacy": it.get("efcyQesitm"),           # 효능
                "usage": it.get("useMethodQesitm"),          # 사용법
                "warning": it.get("atpnWarnQesitm"),         # 주의사항(경고)
                "caution": it.get("atpnQesitm"),             # 주의사항
                "interaction": it.get("intrcQesitm"),        # 상호작용
                "sideEffect": it.get("seQesitm"),            # 부작용
                "storage": it.get("depositMethodQesitm"),    # 보관법
            })
        return jsonify({"query": query, "results": results})

    # e약은요에 없으면 (전문의약품일 가능성) 의약품 제품 허가정보로 폴백
    permit_items, permit_raw = call_drug_permit(item_name=query)
    if not permit_items:
        return jsonify({"query": query, "results": [], "raw": raw, "permitRaw": permit_raw})

    results = []
    for it in permit_items:
        results.append({
            "source": "의약품 제품 허가정보 (전문/일반 포함)",
            "entpName": _find_field(it, ["entp", "업체"]),
            "itemName": _find_field(it, ["itemname", "item_name"]) or query,
            "itemSeq": _find_field(it, ["itemseq", "item_seq"]),
            "etcOtc": _find_field(it, ["etcotc", "etc_otc"]),   # 전문/일반 구분
            "efficacy": _strip_html(_find_field(it, ["eedoc", "ee_doc", "efcy"])),
            "usage": _strip_html(_find_field(it, ["uddoc", "ud_doc", "usemethod"])),
            "caution": _strip_html(_find_field(it, ["nbdoc", "nb_doc", "atpn"])),
            "raw": it,  # 필드명이 예상과 다를 경우를 대비해 원본도 같이 반환
        })
    return jsonify({"query": query, "results": results})


# ------------------------------------------------------------------
# 2) 여러 약물 병용 시 상호작용/부작용 체크 (DUR 병용금기 기반)
# ------------------------------------------------------------------
@app.route("/api/interaction-check", methods=["POST"])
def interaction_check():
    body = request.get_json(force=True) or {}
    drug_names = [d.strip() for d in body.get("drugs", []) if d.strip()]
    if len(drug_names) < 2:
        return jsonify({"error": "비교하려면 약물 이름을 2개 이상 입력하세요."}), 400

    warnings = []
    errors = []

    for name in drug_names:
        try:
            items, _raw = call_dur("usjnt_taboo", item_name=name)
        except requests.RequestException as e:
            errors.append(f"{name}: DUR 조회 실패 ({e})")
            continue

        for it in items:
            # 필드명이 정확히 뭐가 올지 100% 확신할 수 없으므로,
            # 이 레코드의 모든 값(dict의 모든 value)을 문자열로 합쳐서
            # 사용자가 입력한 '다른 약' 이름이 포함되는지 텍스트로 검사한다.
            joined_text = " ".join(str(v) for v in it.values() if v)
            for other in drug_names:
                if other == name:
                    continue
                if other in joined_text:
                    warnings.append({
                        "drugA": name,
                        "drugB": other,
                        "detail": it,   # 원본 레코드 그대로 (필드명 다양성 대응)
                    })

    # 중복 제거 (A-B, B-A 같은 쌍이 두 번 잡히는 것 방지)
    unique = []
    seen = set()
    for w in warnings:
        key = tuple(sorted([w["drugA"], w["drugB"]]))
        if key not in seen:
            seen.add(key)
            unique.append(w)

    return jsonify({
        "drugs": drug_names,
        "warnings": unique,
        "hasWarning": len(unique) > 0,
        "errors": errors,
    })


# ------------------------------------------------------------------
# 3) 복용 횟수 / 일수 적합 여부 체크 (DUR 용량주의 + 투여기간주의)
# ------------------------------------------------------------------
def _extract_number_range(text):
    """'최대 7일', '1일 3회 이내' 같은 문구에서 숫자를 뽑아본다 (참고용, 100% 정확 X)."""
    if not text:
        return []
    return [int(n) for n in re.findall(r"\d+", text)]


@app.route("/api/dosage-check", methods=["POST"])
def dosage_check():
    body = request.get_json(force=True) or {}
    drug_name = (body.get("drug") or "").strip()
    freq_per_day = body.get("freqPerDay")   # 하루 복용 횟수
    days = body.get("days")                 # 총 복용 일수

    if not drug_name:
        return jsonify({"error": "약물명이 필요합니다."}), 400

    period_items, _ = call_dur("period_atent", item_name=drug_name)
    capacity_items, _ = call_dur("capacity_atent", item_name=drug_name)

    def summarize(items):
        out = []
        for it in items:
            text_fields = [str(v) for v in it.values() if isinstance(v, str) and v.strip()]
            note = " / ".join(text_fields) if text_fields else ""
            out.append({
                "raw": it,
                "note": note,
                "numbers_found": _extract_number_range(note),
            })
        return out

    period_summary = summarize(period_items)
    capacity_summary = summarize(capacity_items)

    has_caution = bool(period_summary or capacity_summary)

    return jsonify({
        "drug": drug_name,
        "inputFreqPerDay": freq_per_day,
        "inputDays": days,
        "hasCaution": has_caution,
        "periodCaution": period_summary,     # 투여기간주의 관련 원본/참고 문구
        "capacityCaution": capacity_summary,  # 용량주의 관련 원본/참고 문구
        "note": (
            "DUR 데이터는 대부분 서술형 문구로 제공되어, 입력한 횟수/일수와 "
            "자동으로 숫자 비교하여 '적합/부적합'을 100% 단정하기 어렵습니다. "
            "위 문구를 참고해 최종 판단은 약사가 직접 확인해 주세요."
        ),
    })


# ------------------------------------------------------------------
# 디버그용: 특정 DUR 오퍼레이션의 원본 응답을 그대로 보고 싶을 때
# (필드명이 예상과 다를 때 이 엔드포인트로 실제 구조를 확인하세요)
# ------------------------------------------------------------------
@app.route("/api/debug/permit-raw")
def debug_permit_raw():
    item_name = request.args.get("itemName", "메드론정4밀리그램")
    _items, raw = call_drug_permit(item_name=item_name)
    return jsonify(raw)


@app.route("/api/debug/raw")
def debug_raw():
    operation_key = request.args.get("op", "usjnt_taboo")
    item_name = request.args.get("itemName", "타이레놀정500밀리그램")
    if operation_key not in DUR_OPERATIONS:
        return jsonify({"error": f"알 수 없는 operation_key: {operation_key}",
                         "available": list(DUR_OPERATIONS.keys())}), 400
    _items, raw = call_dur(operation_key, item_name=item_name)
    return jsonify(raw)


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    if not SERVICE_KEY:
        print("⚠️  경고: DATA_GO_KR_SERVICE_KEY 환경변수가 비어 있습니다. .env 파일을 확인하세요.")
    # 로컬 실행용. 실제 배포(Render 등)에서는 gunicorn이 app 객체를 직접 불러오므로
    # 이 블록은 실행되지 않습니다. (render.yaml / Procfile 참고)
    debug_mode = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug_mode, port=int(os.environ.get("PORT", 5000)), host="0.0.0.0")
