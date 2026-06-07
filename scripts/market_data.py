#!/usr/bin/env python3
"""
Compass Trader · 行情数据获取模块
基于新浪财经 API 获取 A 股实时/历史行情数据。

用法：
  python3 scripts/market_data.py quote 600519          # 实时行情
  python3 scripts/market_data.py history 600519 2026-01-01 2026-06-07  # 历史K线
  python3 scripts/market_data.py index 000300           # 指数行情
  python3 scripts/market_data.py search 茅台             # 搜索股票代码
  python3 scripts/market_data.py batch 600519,000858    # 批量行情
"""

import sys
import json
import os
import re
from datetime import datetime, timedelta

# 绕过 macOS 系统代理
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"

import requests

# ── 工具函数 ──────────────────────────────────────────────

def _session():
    """创建绕过系统代理的 requests session"""
    s = requests.Session()
    s.trust_env = False
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko)"
    })
    return s


def _sina_ticker(ticker: str) -> str:
    """将纯数字代码转为新浪格式 (sh600519 或 sz000858)"""
    if ticker.startswith(("6", "5", "9")):
        return f"sh{ticker}"
    else:
        return f"sz{ticker}"


def _sina_market(ticker: str) -> str:
    """判断交易所"""
    if ticker.startswith(("6", "5", "9")):
        return "SH"
    else:
        return "SZ"


# ── 实时行情 (新浪财经) ──────────────────────────────────

def get_realtime_quote(ticker: str) -> dict:
    """
    获取单只股票实时行情。
    ticker: 纯数字代码，如 "600519"
    """
    try:
        s = _session()
        url = f"https://hq.sinajs.cn/list={_sina_ticker(ticker)}"
        r = s.get(url, timeout=10, headers={"Referer": "https://finance.sina.com.cn"})
        r.encoding = "gb2312"

        if r.status_code != 200 or not r.text.strip():
            return {"error": f"新浪 API 返回空数据，请检查代码 {ticker}"}

        # 解析 var hq_str_sh600519="名称,今开,昨收,现价,最高,最低,...";
        match = re.search(r'"([^"]+)"', r.text)
        if not match:
            return {"error": f"解析行情数据失败: {r.text[:100]}"}

        fields = match.group(1).split(",")
        if len(fields) < 32:
            return {"error": f"行情数据字段不足 ({len(fields)}), 原始: {r.text[:200]}"}

        return {
            "ticker": ticker,
            "name": fields[0],
            "open": _float(fields[1]),
            "pre_close": _float(fields[2]),
            "price": _float(fields[3]),
            "high": _float(fields[4]),
            "low": _float(fields[5]),
            "volume": _float(fields[8]),
            "turnover": _float(fields[9]),
            "change_pct": round((_float(fields[3]) - _float(fields[2])) / _float(fields[2]) * 100, 2) if _float(fields[2]) else None,
            "change_amount": round(_float(fields[3]) - _float(fields[2]), 2) if _float(fields[3]) and _float(fields[2]) else None,
            "date": fields[30],
            "time": fields[31],
            # 新浪不直接提供 PE/PB，标记为 N/A
            "pe": None,
            "pb": None,
        }
    except requests.RequestException as e:
        return {"error": f"网络请求失败: {str(e)}"}
    except Exception as e:
        return {"error": f"获取行情失败: {str(e)}"}


# ── 历史K线 (新浪财经) ────────────────────────────────────

def get_history(ticker: str, start_date: str = None, end_date: str = None,
                period: str = "daily") -> list:
    """
    获取历史K线数据。
    ticker: 纯数字代码
    start_date/end_date: YYYY-MM-DD (缺省取近60个交易日)
    period: daily
    """
    try:
        s = _session()

        # 新浪日K API: scale=240 表示日线
        scale_map = {"daily": 240, "weekly": 1200, "monthly": 7200}
        scale = scale_map.get(period, 240)

        # 获取足够多的数据点（最多 2000 条）
        url = (f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
               f"CN_MarketData.getKLineData?symbol={_sina_ticker(ticker)}"
               f"&scale={scale}&ma=no&datalen=2000")
        r = s.get(url, timeout=15, headers={"Referer": "https://finance.sina.com.cn"})

        if r.status_code != 200:
            return {"error": f"新浪历史API返回状态 {r.status_code}"}

        data = r.json()
        if not data or not isinstance(data, list):
            return {"error": f"未获取到 {ticker} 历史数据"}

        records = []
        for row in data:
            date_str = row.get("day", "")
            # 按日期范围过滤
            if start_date and date_str < start_date:
                continue
            if end_date and date_str > end_date:
                continue

            records.append({
                "date": date_str,
                "open": _float(row.get("open")),
                "high": _float(row.get("high")),
                "low": _float(row.get("low")),
                "close": _float(row.get("close")),
                "volume": _float(row.get("volume")),
            })

        return records
    except requests.RequestException as e:
        return {"error": f"网络请求失败: {str(e)}"}
    except json.JSONDecodeError:
        return {"error": f"解析历史数据JSON失败"}
    except Exception as e:
        return {"error": f"获取历史数据失败: {str(e)}"}


# ── 指数行情 (新浪财经) ──────────────────────────────────

INDEX_MAP = {
    "000001": ("上证指数", "sh000001"),
    "000300": ("沪深300", "sh000300"),
    "000016": ("上证50", "sh000016"),
    "399001": ("深证成指", "sz399001"),
    "399006": ("创业板指", "sz399006"),
    "000688": ("科创50", "sh000688"),
    "399005": ("中小100", "sz399005"),
}


def get_index_data(index_code: str = "000300") -> dict:
    """获取指数实时行情"""
    if index_code not in INDEX_MAP:
        return {"error": f"不支持的指数代码: {index_code}，支持: {list(INDEX_MAP.keys())}"}

    name, sina_code = INDEX_MAP[index_code]
    try:
        s = _session()
        url = f"https://hq.sinajs.cn/list={sina_code}"
        r = s.get(url, timeout=10, headers={"Referer": "https://finance.sina.com.cn"})
        r.encoding = "gb2312"

        match = re.search(r'"([^"]+)"', r.text)
        if not match:
            return {"error": f"解析指数数据失败"}

        fields = match.group(1).split(",")
        return {
            "index_code": index_code,
            "name": name,
            "price": _float(fields[3]) if len(fields) > 3 else _float(fields[1]),
            "change_pct": round((_float(fields[3]) - _float(fields[2])) / _float(fields[2]) * 100, 2) if len(fields) > 3 and _float(fields[2]) else None,
            "change_amount": round(_float(fields[3]) - _float(fields[2]), 2) if len(fields) > 3 and _float(fields[3]) and _float(fields[2]) else None,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as e:
        return {"error": f"获取指数数据失败: {str(e)}"}


def get_index_history(index_code: str, start_date: str = None, end_date: str = None) -> list:
    """获取指数历史数据"""
    if index_code not in INDEX_MAP:
        return {"error": f"不支持的指数代码: {index_code}"}

    _, sina_code = INDEX_MAP[index_code]
    try:
        s = _session()
        url = (f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
               f"CN_MarketData.getKLineData?symbol={sina_code}"
               f"&scale=240&ma=no&datalen=2000")
        r = s.get(url, timeout=15, headers={"Referer": "https://finance.sina.com.cn"})

        data = r.json()
        if not data or not isinstance(data, list):
            return {"error": f"未获取到指数 {index_code} 历史数据"}

        records = []
        for row in data:
            date_str = row.get("day", "")
            if start_date and date_str < start_date:
                continue
            if end_date and date_str > end_date:
                continue
            records.append({
                "date": date_str,
                "open": _float(row.get("open")),
                "high": _float(row.get("high")),
                "low": _float(row.get("low")),
                "close": _float(row.get("close")),
                "volume": _float(row.get("volume")),
            })
        return records
    except Exception as e:
        return {"error": f"获取指数历史数据失败: {str(e)}"}


# ── 搜索 (新浪财经 suggest API) ───────────────────────────

def search_ticker(keyword: str) -> list:
    """
    根据关键词搜索股票代码。
    使用新浪 suggest API 实时搜索。
    """
    try:
        s = _session()
        # 新浪 suggest: type=11(沪深A股),12(港股),13(美股),14(基金),15(债券)
        url = f"https://suggest3.sinajs.cn/suggest/type=11,12,13,14,15&key={keyword}"
        r = s.get(url, timeout=10, headers={"Referer": "https://finance.sina.com.cn"})
        r.encoding = "gb2312"

        if r.status_code != 200 or not r.text.strip():
            return {"error": f"搜索 '{keyword}' 无结果"}

        # 解析: var suggestvalue="名称1,类型,代码,market_code,名称2,...;名称3,...;"
        match = re.search(r'"([^"]*)"', r.text)
        if not match:
            return {"error": f"未找到匹配 '{keyword}' 的股票"}

        raw = match.group(1)
        results = []
        # 多条结果用 ";" 分隔，每条内部用 "," 分隔
        for item in raw.split(";"):
            if not item.strip():
                continue
            fields = item.split(",")
            if len(fields) < 4:
                continue
            name = fields[0]
            stype = fields[1]
            ticker = fields[3].replace("sh", "").replace("sz", "")

            # 只保留 A 股 (type=11) 和有意义的代码
            if stype == "11" and ticker.isdigit() and len(ticker) == 6:
                market = "SH" if ticker.startswith(("6", "5", "9")) else "SZ"
                results.append({
                    "ticker": ticker,
                    "name": name,
                    "market": market,
                })

        if not results:
            # 如果 type=11 没结果，也返回其他类型的（基金、港股等）
            for item in raw.split(";"):
                if not item.strip():
                    continue
                fields = item.split(",")
                if len(fields) < 4:
                    continue
                name = fields[0]
                stype = fields[1]
                ticker = fields[3].replace("sh", "").replace("sz", "").replace("of", "")
                if ticker.isdigit():
                    market = fields[3][:2].upper()
                    results.append({
                        "ticker": ticker,
                        "name": name,
                        "market": market,
                    })

        if not results:
            return {"error": f"未找到匹配 '{keyword}' 的股票"}
        return results[:15]
    except Exception as e:
        return {"error": f"搜索失败: {str(e)}"}


# ── 批量行情 ──────────────────────────────────────────────

def batch_quotes(tickers: list) -> list:
    """批量获取多只股票实时行情"""
    try:
        s = _session()
        sina_codes = ",".join(_sina_ticker(t) for t in tickers)
        url = f"https://hq.sinajs.cn/list={sina_codes}"
        r = s.get(url, timeout=15, headers={"Referer": "https://finance.sina.com.cn"})
        r.encoding = "gb2312"

        results = []
        for t in tickers:
            quote = get_realtime_quote(t)
            # 精简批量返回的字段
            if "error" not in quote:
                quote.pop("turnover", None)
                quote.pop("date", None)
                quote.pop("time", None)
            results.append(quote)
        return results
    except Exception as e:
        return {"error": f"批量获取失败: {str(e)}"}


# ── 辅助 ──────────────────────────────────────────────────

def _float(val) -> float:
    """安全转 float，失败返回 None"""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# ── CLI 入口 ──────────────────────────────────────────────

def _cli():
    if len(sys.argv) < 2:
        print("Compass Trader · 行情数据模块 (新浪财经)")
        print("用法:")
        print("  python3 scripts/market_data.py quote <ticker>")
        print("  python3 scripts/market_data.py history <ticker> [start] [end]")
        print("  python3 scripts/market_data.py index [code]")
        print("  python3 scripts/market_data.py index-history <code> [start] [end]")
        print("  python3 scripts/market_data.py search <keyword>")
        print("  python3 scripts/market_data.py batch <ticker1,ticker2,...>")
        return

    cmd = sys.argv[1]
    result = None

    if cmd == "quote" and len(sys.argv) >= 3:
        result = get_realtime_quote(sys.argv[2])
    elif cmd == "history" and len(sys.argv) >= 3:
        start = sys.argv[3] if len(sys.argv) >= 4 else None
        end = sys.argv[4] if len(sys.argv) >= 5 else None
        result = get_history(sys.argv[2], start, end)
    elif cmd == "index":
        idx = sys.argv[2] if len(sys.argv) >= 3 else "000300"
        result = get_index_data(idx)
    elif cmd == "index-history" and len(sys.argv) >= 3:
        start = sys.argv[3] if len(sys.argv) >= 4 else None
        end = sys.argv[4] if len(sys.argv) >= 5 else None
        result = get_index_history(sys.argv[2], start, end)
    elif cmd == "search" and len(sys.argv) >= 3:
        result = search_ticker(sys.argv[2])
    elif cmd == "batch" and len(sys.argv) >= 3:
        tickers = [t.strip() for t in sys.argv[2].split(",")]
        result = batch_quotes(tickers)
    else:
        result = {"error": f"未知命令或参数不足: {cmd}"}

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _cli()
