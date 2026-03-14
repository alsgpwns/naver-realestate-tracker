from statistics import median

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

from app.config import (
    DEFAULT_CONFIG,
    REGION_TREE,
    RLET_TYPE_OPTIONS,
    TRADE_TYPE_OPTIONS,
)
from app.fetcher import fetch_listings
from app.parser import format_gap_text, manwon_to_text, parse_articles

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")


def parse_optional_int(value, default=None):
    if value is None:
        return default
    text = str(value).strip()
    if text == "":
        return default
    try:
        return int(float(text))
    except Exception:
        return default


def parse_optional_float(value, default=None):
    if value is None:
        return default
    text = str(value).strip()
    if text == "":
        return default
    try:
        return float(text)
    except Exception:
        return default


def dedupe_by_article_no(items):
    unique_map = {}
    for item in items:
        article_no = item.get("article_no")
        if article_no:
            unique_map[article_no] = item
    return list(unique_map.values())


def get_percentile_threshold(values, ratio):
    if not values:
        return 0
    sorted_values = sorted(values)
    index = max(0, int(len(sorted_values) * ratio) - 1)
    index = min(index, len(sorted_values) - 1)
    return sorted_values[index]


def build_bargain_list(items):
    groups = {}

    for item in items:
        deal_type = str(item.get("deal_type", "")).strip()
        if deal_type not in ("매매", "전세"):
            continue

        price_value = item.get("price_value", 0) or 0
        if price_value <= 0:
            continue

        complex_name = str(item.get("complex_name", "")).strip()
        area_bucket = str(item.get("area_bucket", "")).strip() or "기타"
        key = (complex_name, deal_type, area_bucket)

        groups.setdefault(key, []).append(item)

    bargain_candidates = []

    for _, group_items in groups.items():
        prices = sorted([
            item.get("price_value", 0) or 0
            for item in group_items
            if (item.get("price_value", 0) or 0) > 0
        ])

        if not prices:
            continue

        group_count = len(prices)
        min_price = min(prices)
        median_price = int(median(prices))
        low_20_price = get_percentile_threshold(prices, 0.2)

        sorted_group = sorted(group_items, key=lambda x: x.get("price_value", 0) or 0)

        for rank_index, item in enumerate(sorted_group, start=1):
            price_value = item.get("price_value", 0) or 0
            if price_value <= 0:
                continue

            is_keyword = bool(item.get("is_bargain_keyword"))
            percentile_rank = rank_index / group_count if group_count > 0 else 1.0

            median_discount_rate = 0.0
            if median_price > 0:
                median_discount_rate = (median_price - price_value) / median_price

            is_low_20 = price_value <= low_20_price
            is_near_min = price_value <= int(min_price * 1.01)

            score = 0
            if is_keyword:
                score += 15
            if price_value == min_price:
                score += 40
            elif is_near_min:
                score += 25

            if median_discount_rate > 0:
                score += int(median_discount_rate * 1000)

            if percentile_rank <= 0.2:
                score += 25
            elif percentile_rank <= 0.4:
                score += 10

            if group_count < 3:
                score -= 15

            is_candidate = False

            if group_count >= 5:
                if is_low_20 and median_discount_rate >= 0.03:
                    is_candidate = True
            elif group_count >= 3:
                if price_value == min_price or median_discount_rate >= 0.04:
                    is_candidate = True
            else:
                if is_keyword or price_value == min_price:
                    is_candidate = True

            if is_keyword:
                is_candidate = True

            if not is_candidate:
                continue

            bargain_item = dict(item)
            bargain_item["group_count"] = group_count
            bargain_item["bargain_min_price"] = min_price
            bargain_item["bargain_min_price_text"] = manwon_to_text(min_price)
            bargain_item["bargain_median_price"] = median_price
            bargain_item["bargain_median_price_text"] = manwon_to_text(median_price)
            bargain_item["bargain_gap"] = price_value - min_price
            bargain_item["bargain_gap_text"] = format_gap_text(price_value - min_price)
            bargain_item["bargain_gap_eok"] = round((price_value - min_price) / 10000, 2)
            bargain_item["median_gap_rate"] = round(median_discount_rate * 100, 2)
            bargain_item["percentile_rank"] = round(percentile_rank * 100, 1)
            bargain_item["bargain_score"] = score
            bargain_candidates.append(bargain_item)

    result = dedupe_by_article_no(bargain_candidates)
    result.sort(key=lambda x: (-(x.get("bargain_score", 0) or 0), x.get("price_value", 0) or 0))
    return result


def apply_filters(
    listings,
    min_pyung_value,
    max_pyung_value,
    max_price_manwon,
    max_deposit_manwon,
    min_household_count_value,
    max_building_age_value,
):
    filtered = []

    for item in listings:
        pyung = item.get("area_pyung", 0) or 0
        if pyung < min_pyung_value:
            continue
        if pyung > max_pyung_value:
            continue

        household_count = item.get("household_count")
        if min_household_count_value > 0:
            if household_count is not None and household_count > 0:
                if household_count < min_household_count_value:
                    continue

        if max_building_age_value is not None:
            building_age_years = item.get("building_age_years")
            if building_age_years is not None and building_age_years > max_building_age_value:
                continue

        deal_type_value = str(item.get("deal_type", "")).strip()

        if deal_type_value == "월세":
            deposit_value = item.get("deposit_value", 0) or 0
            if max_deposit_manwon is not None and deposit_value > max_deposit_manwon:
                continue
        elif deal_type_value in ("매매", "전세"):
            price_value = item.get("price_value", 0) or 0
            if max_price_manwon is not None and price_value > max_price_manwon:
                continue

        filtered.append(item)

    return filtered


def sort_items(items, sort_by):
    sorted_items = list(items)

    if sort_by == "price_asc":
        sorted_items.sort(key=lambda x: x.get("price_value", 0) or 0)
    elif sort_by == "price_desc":
        sorted_items.sort(key=lambda x: -(x.get("price_value", 0) or 0))
    elif sort_by == "pyung_desc":
        sorted_items.sort(key=lambda x: -(x.get("area_pyung", 0) or 0))
    elif sort_by == "household_desc":
        sorted_items.sort(key=lambda x: -((x.get("household_count") or 0)))
    elif sort_by == "age_asc":
        sorted_items.sort(
            key=lambda x: x.get("building_age_years")
            if x.get("building_age_years") is not None else 9999
        )
    elif sort_by == "bargain_score_desc":
        sorted_items.sort(key=lambda x: -(x.get("bargain_score", 0) or 0))
    else:
        sorted_items.sort(key=lambda x: x.get("price_value", 0) or 0)

    return sorted_items


@app.get("/")
def home(
    request: Request,
    trade_type: str = DEFAULT_CONFIG["trade_type"],
    rlet_type: str = DEFAULT_CONFIG["rlet_type"],
    gu_name: str = DEFAULT_CONFIG["gu_name"],
    dong_name: str = DEFAULT_CONFIG["dong_name"],
    min_pyung: str = "0",
    max_pyung: str = "200",
    max_eok: str = "",
    max_deposit_eok: str = "",
    min_household_count: str = "",
    max_building_age: str = "",
    sort_by: str = "bargain_score_desc",
):
    min_pyung_value = parse_optional_float(min_pyung, 0.0) or 0.0
    max_pyung_value = parse_optional_float(max_pyung, 200.0) or 200.0

    max_eok_value = parse_optional_float(max_eok, None)
    max_deposit_eok_value = parse_optional_float(max_deposit_eok, None)
    min_household_count_value = parse_optional_int(min_household_count, 0) or 0
    max_building_age_value = parse_optional_int(max_building_age, None)

    if max_building_age_value is not None and max_building_age_value <= 0:
        max_building_age_value = None

    max_price_manwon = int(max_eok_value * 10000) if max_eok_value is not None else None
    max_deposit_manwon = int(max_deposit_eok_value * 10000) if max_deposit_eok_value is not None else None

    trad_tp_cds = TRADE_TYPE_OPTIONS.get(trade_type, TRADE_TYPE_OPTIONS["전체"])
    rlet_tp_cds = RLET_TYPE_OPTIONS.get(rlet_type, RLET_TYPE_OPTIONS["전체"])

    gu_map = REGION_TREE.get(gu_name, {})
    selected_value = gu_map.get(dong_name)

    if isinstance(selected_value, list):
        cortar_nos = selected_value
    elif isinstance(selected_value, str):
        cortar_nos = [selected_value]
    else:
        fallback = REGION_TREE[DEFAULT_CONFIG["gu_name"]][DEFAULT_CONFIG["dong_name"]]
        cortar_nos = fallback if isinstance(fallback, list) else [fallback]

    raw = fetch_listings(
        cortar_nos=cortar_nos,
        trad_tp_cds=trad_tp_cds,
        rlet_tp_cds=rlet_tp_cds,
        max_complexes_override=2 if dong_name == "전체" else 4,
    )

    listings = parse_articles(raw)

    filtered_list = apply_filters(
        listings=listings,
        min_pyung_value=min_pyung_value,
        max_pyung_value=max_pyung_value,
        max_price_manwon=max_price_manwon,
        max_deposit_manwon=max_deposit_manwon,
        min_household_count_value=min_household_count_value,
        max_building_age_value=max_building_age_value,
    )

    filtered_list = dedupe_by_article_no(filtered_list)
    bargain_list = build_bargain_list(filtered_list)

    bargain_map = {item.get("article_no"): item for item in bargain_list}

    enriched_general_list = []
    for item in filtered_list:
        merged = dict(item)
        if item.get("article_no") in bargain_map:
            merged.update(bargain_map[item.get("article_no")])
        else:
            merged["bargain_score"] = 0
        enriched_general_list.append(merged)

    bargain_list = sort_items(bargain_list, sort_by)
    general_list = sort_items(enriched_general_list, sort_by)

    dong_options = list(REGION_TREE.get(gu_name, {}).keys())

    sort_options = [
        ("bargain_score_desc", "급매점수 높은 순"),
        ("price_asc", "가격 낮은 순"),
        ("price_desc", "가격 높은 순"),
        ("pyung_desc", "평수 큰 순"),
        ("household_desc", "세대수 많은 순"),
        ("age_asc", "연식 낮은 순"),
    ]

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "general_list": general_list,
            "bargain_list": bargain_list,
            "count": len(general_list),
            "selected_trade_type": trade_type,
            "selected_rlet_type": rlet_type,
            "selected_gu_name": gu_name,
            "selected_dong_name": dong_name,
            "selected_min_pyung": min_pyung,
            "selected_max_pyung": max_pyung,
            "selected_max_eok": max_eok,
            "selected_max_deposit_eok": max_deposit_eok,
            "selected_min_household_count": min_household_count,
            "selected_max_building_age": max_building_age,
            "selected_sort_by": sort_by,
            "sort_options": sort_options,
            "trade_type_options": list(TRADE_TYPE_OPTIONS.keys()),
            "rlet_type_options": list(RLET_TYPE_OPTIONS.keys()),
            "gu_options": list(REGION_TREE.keys()),
            "dong_options": dong_options,
        },
    )