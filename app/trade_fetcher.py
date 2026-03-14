import json
from pathlib import Path

from app.parser import gap_to_text, manwon_to_text, safe_int

TRADE_CACHE_FILE = Path("data/trades/recent_trade_cache.json")


def load_trade_cache() -> dict:
    if not TRADE_CACHE_FILE.exists():
        return {}

    try:
        with open(TRADE_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}



def merge_recent_trade_data(items: list[dict]) -> list[dict]:
    cache = load_trade_cache()
    merged = []

    for item in items:
        new_item = dict(item)
        cache_key = f"{item.get('complex_name', '')}|{item.get('area_bucket', '')}"
        trade = cache.get(cache_key) or {}

        recent_trade_price = safe_int(trade.get("recent_trade_price"), 0)
        recent_trade_avg_price = safe_int(trade.get("recent_trade_avg_price"), 0)

        new_item["recent_trade_price"] = recent_trade_price
        new_item["recent_trade_price_text"] = manwon_to_text(recent_trade_price) if recent_trade_price > 0 else "-"
        new_item["recent_trade_date"] = str(trade.get("recent_trade_date", "")).strip() or "-"

        new_item["recent_trade_avg_price"] = recent_trade_avg_price
        new_item["recent_trade_avg_price_text"] = manwon_to_text(recent_trade_avg_price) if recent_trade_avg_price > 0 else "-"
        new_item["recent_trade_avg_period"] = str(trade.get("recent_trade_avg_period", "최근 3개월")).strip() or "최근 3개월"

        price_value = safe_int(item.get("price_value"), 0)
        if price_value > 0 and recent_trade_price > 0:
            gap = price_value - recent_trade_price
            new_item["recent_trade_gap"] = gap
            new_item["recent_trade_gap_text"] = gap_to_text(gap)
        else:
            new_item["recent_trade_gap"] = None
            new_item["recent_trade_gap_text"] = "-"

        if price_value > 0 and recent_trade_avg_price > 0:
            avg_gap = price_value - recent_trade_avg_price
            new_item["recent_trade_avg_gap"] = avg_gap
            new_item["recent_trade_avg_gap_text"] = gap_to_text(avg_gap)
        else:
            new_item["recent_trade_avg_gap"] = None
            new_item["recent_trade_avg_gap_text"] = "-"

        merged.append(new_item)

    return merged
