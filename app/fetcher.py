import re
import time
from datetime import datetime

import requests

from app.config import DEFAULT_CONFIG

COMPLEX_URL = "https://m.land.naver.com/complex/ajax/complexListByCortarNo"
ARTICLE_URL = "https://m.land.naver.com/complex/getComplexArticleList"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Connection": "keep-alive",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def _sleep():
    time.sleep(max(DEFAULT_CONFIG.get("request_sleep_sec", 1.0), 0.8))


def safe_get_json(url: str, params: dict, referer: str, timeout_sec: int):
    try:
        _sleep()

        res = SESSION.get(
            url,
            params=params,
            headers={**HEADERS, "Referer": referer},
            timeout=timeout_sec,
            allow_redirects=False,
        )

        print("=" * 80)
        print("요청 URL:", res.url)
        print("status_code:", res.status_code)
        print("content-type:", res.headers.get("Content-Type", ""))
        print("response preview:", res.text[:300])

        if res.status_code in (301, 302, 303, 307, 308):
            print("리다이렉트 감지 - 네이버 차단/abuse 가능성")
            return None

        if res.status_code != 200:
            return None

        content_type = res.headers.get("Content-Type", "").lower()
        if "json" not in content_type:
            return None

        return res.json()

    except Exception as e:
        print("요청 실패:", str(e))
        return None


def safe_get_text(url: str, referer: str, timeout_sec: int):
    try:
        _sleep()

        res = SESSION.get(
            url,
            headers={
                **HEADERS,
                "Referer": referer,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            timeout=timeout_sec,
            allow_redirects=True,
        )

        print("=" * 80)
        print("상세 페이지 URL:", res.url)
        print("status_code:", res.status_code)
        print("content-type:", res.headers.get("Content-Type", ""))
        print("html preview:", res.text[:300])

        if res.status_code != 200:
            return None

        return res.text

    except Exception as e:
        print("상세 페이지 요청 실패:", str(e))
        return None


def get_html_snippet(text: str, keyword: str, radius: int = 200):
    idx = text.find(keyword)
    if idx == -1:
        return None

    start = max(0, idx - radius)
    end = min(len(text), idx + radius)
    snippet = text[start:end]
    return re.sub(r"\s+", " ", snippet)


def calc_building_age_years(approval_date: str | None):
    if not approval_date:
        return None

    for fmt in ("%Y.%m.%d", "%Y-%m-%d", "%Y%m%d"):
        try:
            approval_dt = datetime.strptime(approval_date, fmt).date()
            today = datetime.today().date()
            age = today.year - approval_dt.year
            if (today.month, today.day) < (approval_dt.month, approval_dt.day):
                age -= 1
            return age
        except Exception:
            continue

    return None


def normalize_visible_text(html: str) -> str:
    text = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_building_meta_from_html(html: str) -> dict:
    normalized = normalize_visible_text(html)

    household_count = None
    approval_date = None
    building_age_years = None

    approval_patterns = [
        r"사용승인일[^0-9]{0,30}([0-9]{4}\.[0-9]{2}\.[0-9]{2})",
        r"사용승인일[^0-9]{0,30}([0-9]{4}-[0-9]{2}-[0-9]{2})",
        r"사용승인일[^0-9]{0,30}([0-9]{8})",
    ]
    for pattern in approval_patterns:
        match = re.search(pattern, normalized)
        if match:
            approval_date = match.group(1)
            break

    household_patterns = [
        r"세대수[^0-9]{0,30}([0-9,]+)\s*세대",
        r"총[^0-9]{0,10}([0-9,]+)\s*세대",
    ]
    for pattern in household_patterns:
        match = re.search(pattern, normalized)
        if match:
            try:
                household_count = int(match.group(1).replace(",", ""))
                break
            except Exception:
                pass

    age_patterns = [
        r"\((\d+)\s*년차\)",
        r"(\d+)\s*년차",
    ]
    for pattern in age_patterns:
        match = re.search(pattern, normalized)
        if match:
            try:
                building_age_years = int(match.group(1))
                break
            except Exception:
                pass

    if building_age_years is None and approval_date:
        building_age_years = calc_building_age_years(approval_date)

    print(
        "META PARSED:",
        {
            "household_count": household_count,
            "approval_date": approval_date,
            "building_age_years": building_age_years,
        },
    )

    return {
        "household_count": household_count,
        "approval_date": approval_date,
        "building_age_years": building_age_years,
    }


def fetch_building_meta(article_no: str, hscp_no: str, timeout_sec: int) -> dict:
    url = f"https://fin.land.naver.com/articles/{article_no}?hscpNo={hscp_no}"

    html = safe_get_text(
        url=url,
        referer=f"https://m.land.naver.com/article/info/{article_no}?hscpNo={hscp_no}",
        timeout_sec=timeout_sec,
    )

    if not html:
        return {
            "household_count": None,
            "approval_date": None,
            "building_age_years": None,
        }

    print("HTML 사용승인일 주변:", get_html_snippet(html, "사용승인일"))
    print("HTML 세대수 주변:", get_html_snippet(html, "세대수"))

    parsed = parse_building_meta_from_html(html)
    if not isinstance(parsed, dict):
        return {
            "household_count": None,
            "approval_date": None,
            "building_age_years": None,
        }

    return parsed


def fetch_complexes(cortar_no: str, timeout_sec: int, allowed_rlet_tp_cds: list[str]):
    params = {"cortarNo": cortar_no}

    data = safe_get_json(
        COMPLEX_URL,
        params,
        referer="https://m.land.naver.com/",
        timeout_sec=timeout_sec,
    )

    if not data:
        return []

    result = data.get("result", [])
    if not isinstance(result, list):
        print("complex result가 list가 아님")
        return []

    complexes = []
    for item in result:
        hscp_no = str(item.get("hscpNo", "")).strip()
        hscp_nm = str(item.get("hscpNm", "")).strip()
        hscp_type_cd = str(item.get("hscpTypeCd", "")).strip()
        item_cortar_no = str(item.get("cortarNo", "")).strip()

        if not hscp_no or not hscp_nm:
            continue

        if hscp_type_cd not in allowed_rlet_tp_cds:
            continue

        if item_cortar_no != cortar_no:
            print(f"동코드 불일치 제외: 요청={cortar_no}, 응답={item_cortar_no}, 단지={hscp_nm}")
            continue

        complexes.append(
            {
                "hscpNo": hscp_no,
                "hscpNm": hscp_nm,
                "cortarNo": item_cortar_no,
                "hscpTypeCd": hscp_type_cd,
                "dealCnt": int(item.get("dealCnt", 0) or 0),
                "leaseCnt": int(item.get("leaseCnt", 0) or 0),
                "rentCnt": int(item.get("rentCnt", 0) or 0),
            }
        )

    return complexes


def fetch_article_page(
    hscp_no: str,
    rlet_tp_cd: str,
    trad_tp_cd: str,
    order: str,
    page: int,
    timeout_sec: int,
):
    params = {
        "hscpNo": hscp_no,
        "rletTpCd": rlet_tp_cd,
        "tradTpCd": trad_tp_cd,
        "order": order,
        "page": page,
    }

    data = safe_get_json(
        ARTICLE_URL,
        params,
        referer=f"https://m.land.naver.com/complex/info/{hscp_no}",
        timeout_sec=timeout_sec,
    )

    if not data:
        return []

    result = data.get("result", {})
    if not isinstance(result, dict):
        print("article result가 dict가 아님")
        return []

    article_list = result.get("list", [])
    if not isinstance(article_list, list):
        print("article result.list가 list가 아님")
        return []

    return article_list


def get_trade_count(complex_item: dict, trad_tp_cd: str) -> int:
    if trad_tp_cd == "A1":
        return complex_item.get("dealCnt", 0)
    if trad_tp_cd == "B1":
        return complex_item.get("leaseCnt", 0)
    if trad_tp_cd == "B2":
        return complex_item.get("rentCnt", 0)
    return 0


def fetch_listings(
    cortar_nos,
    trad_tp_cds: list[str],
    rlet_tp_cds: list[str],
    max_complexes_override=None,
):
    orders = DEFAULT_CONFIG.get("article_orders", ["date"])
    max_pages = DEFAULT_CONFIG.get("max_complex_pages", 1)
    max_complexes = max_complexes_override or DEFAULT_CONFIG.get("max_complexes_per_run", 2)
    timeout_sec = DEFAULT_CONFIG.get("request_timeout_sec", 20)

    all_articles = []
    building_meta_cache = {}
    redirect_block_count = 0

    for cortar_no in cortar_nos:
        print(f"지역 조회 시작: cortarNo={cortar_no}")

        complexes = fetch_complexes(
            cortar_no=cortar_no,
            timeout_sec=timeout_sec,
            allowed_rlet_tp_cds=rlet_tp_cds,
        )
        print("단지 개수:", len(complexes))

        if not complexes:
            continue

        complexes.sort(
            key=lambda x: x.get("dealCnt", 0) + x.get("leaseCnt", 0) + x.get("rentCnt", 0),
            reverse=True,
        )

        run_complexes = complexes[:max_complexes]
        print("실행 단지 개수:", len(run_complexes))

        for idx, complex_item in enumerate(run_complexes, start=1):
            hscp_no = complex_item["hscpNo"]
            hscp_nm = complex_item["hscpNm"]
            hscp_type_cd = complex_item["hscpTypeCd"]

            print(f"[{idx}/{len(run_complexes)}] 단지 수집 시작: {hscp_nm} ({hscp_no}) / {hscp_type_cd}")

            for trad_tp_cd in trad_tp_cds:
                trade_count = get_trade_count(complex_item, trad_tp_cd)
                if trade_count == 0:
                    print(f"skip: hscpNo={hscp_no}, tradTpCd={trad_tp_cd}, count=0")
                    continue

                for order in orders:
                    for page in range(1, max_pages + 1):
                        articles = fetch_article_page(
                            hscp_no=hscp_no,
                            rlet_tp_cd=hscp_type_cd,
                            trad_tp_cd=trad_tp_cd,
                            order=order,
                            page=page,
                            timeout_sec=timeout_sec,
                        )

                        if not articles:
                            redirect_block_count += 1
                            if redirect_block_count >= 5:
                                print("302/빈응답 누적. 수집 중단")
                                return all_articles
                            break

                        print(
                            f"hscpNo={hscp_no}, rletTpCd={hscp_type_cd}, tradTpCd={trad_tp_cd}, "
                            f"order={order}, page={page}, articles={len(articles)}"
                        )

                        if hscp_no not in building_meta_cache:
                            first_article_no = str(articles[0].get("atclNo", "")).strip()
                            if first_article_no:
                                building_meta_cache[hscp_no] = fetch_building_meta(
                                    article_no=first_article_no,
                                    hscp_no=hscp_no,
                                    timeout_sec=timeout_sec,
                                )
                            else:
                                building_meta_cache[hscp_no] = {
                                    "household_count": None,
                                    "approval_date": None,
                                    "building_age_years": None,
                                }

                        building_meta = building_meta_cache.get(hscp_no) or {
                            "household_count": None,
                            "approval_date": None,
                            "building_age_years": None,
                        }

                        for article in articles:
                            article["_complexNameFromComplex"] = hscp_nm
                            article["_hscpNo"] = hscp_no
                            article["_selectedCortarNo"] = cortar_no
                            article["_complexCortarNo"] = complex_item.get("cortarNo", "")
                            article["_complexTypeCd"] = hscp_type_cd
                            article["_householdCount"] = building_meta.get("household_count")
                            article["_approvalDate"] = building_meta.get("approval_date")
                            article["_buildingAgeYears"] = building_meta.get("building_age_years")

                        all_articles.extend(articles)

    return all_articles