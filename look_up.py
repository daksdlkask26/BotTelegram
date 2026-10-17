import os
import time
import hmac
import hashlib
import urllib.parse
import requests
import json
from dotenv import load_dotenv

# =========================
# LOAD .env
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


# =========================
# CẤU HÌNH BINANCE API
# =========================
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
TRC20_ADDRESS = os.getenv("TRC20_ADDRESS", "").strip()
BEP20_ADDRESS = os.getenv("BEP20_ADDRESS", "").strip()


if not BINANCE_API_KEY or not BINANCE_API_SECRET:
    raise RuntimeError("Thiếu BINANCE_API_KEY / BINANCE_API_SECRET trong env.")

BINANCE_API_SECRET = BINANCE_API_SECRET.encode("utf-8")
BASE_URL = "https://api.binance.com"  # Main Binance

# ====== HÀM KÝ SIGNATURE ======
def sign_params(params: dict) -> str:
    """Create Binance-style signed query string."""
    query_string = urllib.parse.urlencode(params, doseq=True)
    signature = hmac.new(
        BINANCE_API_SECRET, query_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"{query_string}&signature={signature}"


def _server_time_ms():
    try:
        resp = requests.get(f"{BASE_URL}/api/v3/time", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return int(data.get("serverTime", int(time.time() * 1000)))
    except Exception:
        return int(time.time() * 1000)


# ====== GỌI /sapi/v1/pay/transactions ======
def get_pay_history(start_time_ms=None, end_time_ms=None, limit=100):
    """
    Gọi Get Pay Trade History.
    - Nếu không truyền start/end thì Binance trả 90 ngày gần nhất.
    - Hỗ trợ truy vấn trong vòng 18 tháng.
    """
    params = {
        "timestamp": _server_time_ms(),
        "limit": limit,  # tối đa 100
        "recvWindow": 60000,
    }
    if start_time_ms is not None:
        params["startTime"] = int(start_time_ms)
    if end_time_ms is not None:
        params["endTime"] = int(end_time_ms)

    signed_qs = sign_params(params)
    url = f"{BASE_URL}/sapi/v1/pay/transactions?{signed_qs}"

    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}

    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    # Thường sẽ có dạng { "code": "000000", "message": "success", "data": [ ... ], "success": true }
    if not data.get("success"):
        raise RuntimeError(f"Binance trả về lỗi: {data}")

    return data.get("data", [])


def find_pay_transaction_by_id(order_id: str, start_time_ms=None, end_time_ms=None):
    """
    Lọc trong lịch sử Pay để tìm giao dịch khớp với orderId / transactionId.
    - order_id: chuỗi bạn thấy trên app, ví dụ '402117599683977216'
    """
    history = get_pay_history(start_time_ms=start_time_ms, end_time_ms=end_time_ms)

    for tx in history:
        # Tùy account/region, field có thể là transactionId, orderId, bizId...
        tx_ids = [
            tx.get("transactionId"),
            tx.get("orderId"),
            tx.get("bizId"),
        ]
        if order_id in [str(v) for v in tx_ids if v is not None]:
            return tx

    return None


def check_deposit_by_txid(txid: str):
    """
    Check blockchain transaction by txid.
    Supports:
    1. Binance Deposit History (for deposits to Binance wallet)
    2. TRC20 direct blockchain verification (TronScan API)
    3. BEP20 direct blockchain verification (BscScan API)
    
    Returns dict with:
    - amount: float (in USDT)
    - currency: str (USDT)
    - timestamp: int (unix ms)
    - confirmed: bool
    Or None if not found/invalid
    """
    
    if not txid or len(txid) < 10:
        print(f"⚠️ Invalid txid format: {txid}")
        return None
    
    print(f"🔍 Checking txid: {txid[:20]}...")
    
    # Try Binance Deposit History first
    try:
        result = _check_binance_deposit(txid)
        if result:
            print(f"✅ Found in Binance deposit history")
            return result
    except Exception as e:
        print(f"⚠️ Binance deposit check failed: {e}")
    
    # If not found in Binance, check blockchain directly
    # TRC20: 64 hex chars starting with 0x or just hex
    # BEP20: 64 hex chars starting with 0x
    if len(txid) >= 60:
        # Try TRC20 first
        try:
            result = _check_trc20_transaction(txid)
            if result:
                return result
        except Exception as e:
            print(f"⚠️ TRC20 check failed: {e}")
        
        # Then try BEP20
        try:
            result = _check_bep20_transaction(txid)
            if result:
                return result
        except Exception as e:
            print(f"⚠️ BEP20 check failed: {e}")
    else:
        print(f"⚠️ TxID too short for blockchain verification: {len(txid)} chars")
    
    print(f"❌ TxID not found in any source")
    return None


def _check_binance_deposit(txid: str):
    """Check Binance deposit history for txid"""
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        return None
    
    try:
        end_time = int(time.time() * 1000)
        start_time = end_time - (90 * 24 * 3600 * 1000)
        
        params = {
            "timestamp": _server_time_ms(),
            "recvWindow": 60000,
            "startTime": start_time,
            "endTime": end_time,
        }
        
        signed = sign_params(params)
        url = f"{BASE_URL}/sapi/v1/capital/deposit/hisrec"
        headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
        
        resp = requests.get(url, params=signed, headers=headers, timeout=15)
        
        if resp.status_code != 200:
            return None
        
        deposits = resp.json()
        
        for deposit in deposits:
            if deposit.get("txId") == txid and deposit.get("status") == 1:
                return {
                    "amount": float(deposit.get("amount", 0)),
                    "currency": deposit.get("coin", "USDT"),
                    "timestamp": int(deposit.get("insertTime", time.time() * 1000)),
                    "confirmed": True
                }
        
        return None
        
    except Exception as e:
        print(f"❌ Binance deposit check error: {e}")
        return None
def _check_trc20_transaction(txid: str):
    """
    Verify TRC20 USDT transaction using TronScan public API (no key required).
    Contract: TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t (USDT TRC20)
    """
    if not TRC20_ADDRESS:
        print("⚠️ TRC20_ADDRESS not configured")
        return None
    
    try:
        # Clean txid (remove 0x if present)
        clean_txid = txid.replace("0x", "").replace("0X", "")
        
        # TronScan public API (no API key needed)
        url = f"https://apilist.tronscan.org/api/transaction-info?hash={clean_txid}"
        resp = requests.get(url, timeout=15)
        
        if resp.status_code != 200:
            print(f"⚠️ TronScan API error: {resp.status_code}")
            return None
        
        data = resp.json()
        
        # Check if transaction exists and confirmed
        if not data or data.get("confirmed") != True:
            print("⚠️ TRC20 transaction not found or not confirmed")
            return None
        
        # USDT TRC20 contract address
        USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
        
        # Parse token transfers
        token_transfers = data.get("trc20TransferInfo", [])
        
        for transfer in token_transfers:
            to_address = transfer.get("to_address", "")
            contract = transfer.get("contract_address", "")
            
            # Check if this is USDT transfer to our address
            if contract == USDT_CONTRACT and to_address == TRC20_ADDRESS:
                # Amount is in smallest unit (6 decimals for USDT)
                amount_raw = int(transfer.get("amount_str", "0"))
                amount = amount_raw / 1_000_000  # Convert to USDT
                
                timestamp = data.get("timestamp", int(time.time() * 1000))
                
                print(f"✅ TRC20 verified: {amount} USDT to {TRC20_ADDRESS[:10]}...")
                
                return {
                    "amount": amount,
                    "currency": "USDT",
                    "timestamp": timestamp,
                    "confirmed": True
                }
        
        print("⚠️ No USDT transfer found to configured TRC20 address")
        return None
        
    except Exception as e:
        print(f"❌ TRC20 verification error: {e}")
        return None


def _check_bep20_transaction(txid: str):
    """
    Verify BEP20 USDT transaction using BscScan public API (no key required).
    Contract: 0x55d398326f99059fF775485246999027B3197955 (USDT BEP20)
    Works without API key but with lower rate limit (5 req/sec vs 15 req/sec with key).
    """
    if not BEP20_ADDRESS:
        print("⚠️ BEP20_ADDRESS not configured")
        return None
    
    bscscan_key = os.getenv("BSCSCAN_API_KEY", "").strip()
    
    try:
        # Clean txid
        clean_txid = txid if txid.startswith("0x") else f"0x{txid}"
        
        # BscScan public API endpoint (works without API key)
        url = "https://api.bscscan.com/api"
        params = {
            "module": "proxy",
            "action": "eth_getTransactionReceipt",
            "txhash": clean_txid,
        }
        
        # API key is optional (only for higher rate limit)
        if bscscan_key:
            params["apikey"] = bscscan_key
        
        resp = requests.get(url, params=params, timeout=15)
        
        if resp.status_code != 200:
            print(f"⚠️ BscScan API error: {resp.status_code}")
            return None
        
        data = resp.json()
        
        if data.get("result") is None:
            print("⚠️ BEP20 transaction not found or pending")
            return None
        
        receipt = data.get("result", {})
        
        # Check if transaction was successful
        if receipt.get("status") != "0x1":  # 0x1 = success
            print("⚠️ BEP20 transaction failed")
            return None
        
        # Parse logs to find USDT transfer
        USDT_CONTRACT = "0x55d398326f99059fF775485246999027B3197955".lower()
        
        logs = receipt.get("logs", [])
        for log in logs:
            # Check if this is from USDT contract
            if log.get("address", "").lower() != USDT_CONTRACT:
                continue
            
            # ERC20 Transfer event signature
            topics = log.get("topics", [])
            if len(topics) < 3:
                continue
            
            # Decode recipient address (topic[2])
            to_address = "0x" + topics[2][-40:]  # Last 40 hex chars
            
            if to_address.lower() == BEP20_ADDRESS.lower():
                # Decode amount from data field
                data_hex = log.get("data", "0x0")
                amount_raw = int(data_hex, 16)
                amount = amount_raw / 1_000_000_000_000_000_000  # 18 decimals for BEP20 USDT
                
                # Get block timestamp
                block_hex = receipt.get("blockNumber", "0x0")
                block_num = int(block_hex, 16)
                
                # Get block details for timestamp (also works without API key)
                block_params = {
                    "module": "proxy",
                    "action": "eth_getBlockByNumber",
                    "tag": hex(block_num),
                    "boolean": "false"
                }
                if bscscan_key:
                    block_params["apikey"] = bscscan_key
                
                block_resp = requests.get(url, params=block_params, timeout=10)
                timestamp = int(time.time() * 1000)
                
                if block_resp.status_code == 200:
                    block_data = block_resp.json()
                    if block_data.get("result"):
                        ts_hex = block_data["result"].get("timestamp", "0x0")
                        timestamp = int(ts_hex, 16) * 1000
                
                print(f"✅ BEP20 verified: {amount} USDT to {BEP20_ADDRESS[:10]}...")
                
                return {
                    "amount": amount,
                    "currency": "USDT",
                    "timestamp": timestamp,
                    "confirmed": True
                }
        
        print("⚠️ No USDT transfer found to configured BEP20 address")
        return None
        
    except Exception as e:
        print(f"❌ BEP20 verification error: {e}")
        return None
