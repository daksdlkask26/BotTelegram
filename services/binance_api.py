import hashlib
import hmac
import time
import urllib.parse
import requests

from config import settings

BASE_URL = "https://api.binance.com"


class BinanceApiError(RuntimeError):
    pass


def _get_api_creds():
    api_key = (settings.BINANCE_API_KEY or "").strip()
    api_secret = (settings.BINANCE_API_SECRET or "").strip()
    if not api_key or not api_secret:
        raise BinanceApiError("Missing BINANCE_API_KEY / BINANCE_API_SECRET")
    return api_key, api_secret


def _sign_params(params: dict, api_secret: str) -> str:
    query_string = urllib.parse.urlencode(params, doseq=True)
    signature = hmac.new(
        api_secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{query_string}&signature={signature}"


def _request_signed(path: str, params: dict):
    api_key, api_secret = _get_api_creds()
    params["timestamp"] = int(time.time() * 1000)
    signed_qs = _sign_params(params, api_secret)
    url = f"{BASE_URL}{path}?{signed_qs}"
    headers = {"X-MBX-APIKEY": api_key}
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_pay_history(start_time_ms=None, end_time_ms=None, limit=100):
    params = {"limit": int(limit)}
    if start_time_ms is not None:
        params["startTime"] = int(start_time_ms)
    if end_time_ms is not None:
        params["endTime"] = int(end_time_ms)
    data = _request_signed("/sapi/v1/pay/transactions", params)
    if isinstance(data, dict) and not data.get("success", True):
        raise BinanceApiError(f"Binance error: {data}")
    return data.get("data", []) if isinstance(data, dict) else data


def find_pay_transaction_by_id(order_id: str, start_time_ms=None, end_time_ms=None):
    history = get_pay_history(start_time_ms=start_time_ms, end_time_ms=end_time_ms)
    for tx in history:
        tx_ids = [
            tx.get("transactionId"),
            tx.get("orderId"),
            tx.get("bizId"),
        ]
        if order_id in [str(v) for v in tx_ids if v is not None]:
            return tx
    return None


def check_deposit_by_txid(txid: str, coin: str | None = None):
    params = {"txId": txid}
    if coin:
        params["coin"] = coin
    data = _request_signed("/sapi/v1/capital/deposit/hisrec", params)
    if isinstance(data, dict) and "depositList" in data:
        return data.get("depositList", [])
    return data if isinstance(data, list) else []


def extract_amount_currency(tx: dict):
    amount = (
        tx.get("totalAmount")
        or tx.get("amount")
        or tx.get("transactionAmount")
        or tx.get("transAmount")
        or tx.get("orderAmount")
        or tx.get("paymentAmount")
        or tx.get("payAmount")
        or 0
    )
    currency = (
        tx.get("currency")
        or tx.get("transactCurrency")
        or tx.get("fiatCurrency")
        or tx.get("coin")
        or "USDT"
    )
    try:
        amount_val = float(amount)
    except Exception:
        amount_val = 0.0
    return amount_val, str(currency).upper()


def extract_tx_time_ms(tx: dict):
    candidates = [
        tx.get("transactTime"),
        tx.get("payTime"),
        tx.get("createTime"),
        tx.get("time"),
        tx.get("insertTime"),
    ]
    for t in candidates:
        if t is None:
            continue
        try:
            return int(t)
        except Exception:
            continue
    return int(time.time() * 1000)
