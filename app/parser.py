import re


def safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default

        if isinstance(value, str):
            value = value.replace(",", "").strip()

        return int(float(value))
    except Exception:
        return default


def has_bargain_keyword(text: str) -> bool:
    if not text:
        return False

    normalized = str(text).replace(" ", "").strip()

    keywords = [
        "급매",
        "급처",
        "특가",
        "저렴",
        "시세보다",
        "가격조정",
        "가격인하",
        "인하",
        "빠른매매",
        "최저가",
    ]

    return any(keyword in normalized for keyword in keywords)


def parse_korean_money_to_manwon(text: str) -> int:
    """
    예:
    23억
    9억 5,000
    1억5000
    8,500
    5000
    """
    if not text:
        return 0

    s = str(text).strip().replace(",", "").replace(" ", "")
    if not s:
        return 0

    if "억" in s:
        left, right = s.split("억", 1)

        eok = 0
        manwon = 0

        try:
            eok = int(left) if left else 0
        except Exception:
            eok = 0

        right_digits = re.sub(r"[^0-9]", "", right or "")
        if right_digits:
            try:
                manwon = int(right_digits)
            except Exception:
                manwon = 0

        return eok * 10000 + manwon

    digits = re.sub(r"[^0-9]", "", s)
    if digits:
        try:
            return int(digits)
        except Exception:
            return 0

    return 0


def manwon_to_text(value: int | float | None) -> str:
    if value is None:
        return "-"

    try:
        value = int(value)
    except Exception:
        return "-"

    if value <= 0:
        return "0"

    eok = value // 10000
    manwon = value % 10000

    if eok > 0 and manwon > 0:
        return f"{eok}억 {manwon:,}"
    if eok > 0:
        return f"{eok}억"
    return f"{manwon:,}"


def format_gap_text(gap_value: int | None) -> str:
    if gap_value is None:
        return "-"

    sign = "+" if gap_value > 0 else ""
    return f"{sign}{manwon_to_text(abs(gap_value))}" if gap_value < 0 else f"{sign}{manwon_to_text(gap_value)}"


def resolve_price_value(prc, prc_info: str) -> int:
    value = safe_int(prc, 0)
    if value > 0:
        return value
    return parse_korean_money_to_manwon(prc_info)


def build_price_fields(article: dict):
    deal_type = str(article.get("tradTpNm", "")).strip()

    prc = article.get("prc")
    rent_prc = safe_int(article.get("rentPrc"))
    prc_info = str(article.get("prcInfo", "")).strip()

    resolved_price = resolve_price_value(prc, prc_info)

    if deal_type == "월세":
        if resolved_price > 0 or rent_prc > 0:
            display_text = prc_info if prc_info else f"{manwon_to_text(resolved_price)} / {rent_prc:,}"
            return {
                "deposit": display_text,
                "price_value": resolved_price,
                "deposit_value": resolved_price,
                "rent_value": rent_prc,
            }

        return {
            "deposit": prc_info if prc_info else "0",
            "price_value": 0,
            "deposit_value": 0,
            "rent_value": 0,
        }

    if resolved_price > 0:
        return {
            "deposit": prc_info if prc_info else manwon_to_text(resolved_price),
            "price_value": resolved_price,
            "deposit_value": resolved_price,
            "rent_value": 0,
        }

    return {
        "deposit": prc_info if prc_info else "0",
        "price_value": 0,
        "deposit_value": 0,
        "rent_value": 0,
    }


def make_area_bucket(area_m2: float) -> str:
    if not area_m2 or area_m2 <= 0:
        return "기타"
    return f"{round(area_m2)}㎡형"


def parse_articles(raw_articles: list[dict]) -> list[dict]:
    parsed = []

    for article in raw_articles:
        article_no = str(article.get("atclNo", "")).strip()
        if not article_no:
            continue

        hscp_no = str(article.get("_hscpNo", "")).strip()
        url = (
            f"https://m.land.naver.com/article/info/{article_no}?hscpNo={hscp_no}"
            if hscp_no
            else f"https://m.land.naver.com/article/info/{article_no}"
        )

        price_fields = build_price_fields(article)

        spc1 = safe_float(article.get("spc1"), 0.0)   # 공급면적 추정
        spc2 = safe_float(article.get("spc2"), 0.0)   # 전용면적 추정

        area_m2 = spc1 if spc1 > 0 else spc2
        area_pyung = round(area_m2 / 3.3058, 1) if area_m2 > 0 else 0.0
        area_bucket = make_area_bucket(area_m2)

        article_desc = str(article.get("atclFetrDesc", "")).strip()

        household_count = article.get("_householdCount")
        if household_count in ("", 0):
            household_count = None

        parsed.append(
            {
                "article_no": article_no,
                "complex_name": str(
                    article.get("atclNm") or article.get("_complexNameFromComplex") or ""
                ).strip(),
                "deal_type": str(article.get("tradTpNm", "")).strip(),
                "rlet_type": str(article.get("rletTpNm", "")).strip(),
                "area_m2": round(area_m2, 2) if area_m2 > 0 else 0.0,
                "area_pyung": area_pyung,
                "area_bucket": area_bucket,
                "floor": str(article.get("flrInfo", "")).strip(),
                "deposit": price_fields["deposit"],
                "price_text": manwon_to_text(price_fields["price_value"]),
                "price_value": price_fields["price_value"],
                "deposit_value": price_fields["deposit_value"],
                "rent_value": price_fields["rent_value"],
                "url": url,
                "article_name": article_desc,
                "household_count": household_count,
                "approval_date": article.get("_approvalDate"),
                "building_age_years": article.get("_buildingAgeYears"),
                "is_bargain_keyword": has_bargain_keyword(article_desc),
            }
        )

    return parsed