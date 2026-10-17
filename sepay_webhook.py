from __future__ import annotations
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import re
import urllib.request
import logging

from flask import Flask, request, jsonify

from config import settings as app_settings
from commands.dbconfig import db_connect
from i18n import get_text as i18n_get_text

app = Flask(__name__)

SEPAY_KEY = (app_settings.SEPAY_WEBHOOK_KEY or "").strip()
EXCHANGE_RATE_VND = 25000

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    filename="action.log",
    filemode="a",
)
logger = logging.getLogger(__name__)


def normalize_amount(value) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(round(value))
    text = str(value).strip().replace(",", "")
    if not text:
        return 0
    try:
        return int(float(text))
    except Exception:
        return 0


def extract_api_key_from_headers(req) -> str:
    data = req.get_json(silent=True) or {}

    provided = (
        req.headers.get("X-Webhook-Key")
        or req.headers.get("X-Api-Key")
        or req.headers.get("X-Sepay-Key")
        or req.headers.get("Authorization")
        or req.args.get("key")
        or data.get("webhook_key")
        or data.get("key")
        or ""
    )

    provided = (provided or "").strip()
    if provided.lower().startswith("bearer "):
        provided = provided[7:].strip()
    elif provided.lower().startswith("apikey "):
        provided = provided[len("apikey "):].strip()
    elif provided.lower().startswith("api-key "):
        provided = provided[len("api-key "):].strip()
    elif provided.startswith("Apikey "):
        provided = provided[len("Apikey "):].strip()
    elif provided.startswith("APIKEY "):
        provided = provided[len("APIKEY "):].strip()
    return provided


def is_auth_ok(req) -> bool:
    expected = (app_settings.SEPAY_WEBHOOK_KEY or "").strip()
    if not expected:
        return False

    provided = extract_api_key_from_headers(req)  # lấy từ X-Api-Key/Authorization/query key/body...
    return provided == expected


def parse_sepay_payload(raw: dict):
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw

    ttype = (data.get("transferType") or data.get("transactionType") or "").lower()
    if ttype in ("credit", "in", "receive"):
        direction = "in"
    elif ttype in ("debit", "out", "send"):
        direction = "out"
    else:
        direction = (data.get("direction") or "").lower()

    amount = normalize_amount(data.get("transferAmount") or data.get("amount") or 0)

    tx_id = data.get("id") or data.get("transactionId") or data.get("tid") or ""
    tx_id = str(tx_id).strip()

    content = ((data.get("content") or "") + " " + (data.get("description") or "")).strip()
    code = (data.get("code") or "").strip()

    return direction, amount, tx_id, content, code


def extract_order_code(code: str, content: str) -> str | None:
    for text in (code, content):
        if not text:
            continue
        text = text.strip()
        match = re.search(r"(SP[A-Za-z0-9]+)", text)
        if match:
            return match.group(1)
    return None


def send_telegram_message(chat_id: int, text: str) -> None:
    token = app_settings.BOT_TOKEN
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


@app.route("/", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "sepay_webhook"})


@app.route(app_settings.WEBHOOK_PATH + "/", methods=["POST"])
@app.route(app_settings.WEBHOOK_PATH, methods=["POST"])
def sepay_webhook():
    try:
        print("=== SEPAY WEBHOOK HIT ===")
        print("IP:", request.remote_addr)
        print("Headers:", dict(request.headers))
        print("Args:", request.args.to_dict())
        print("Form:", request.form.to_dict())
        try:
            print("JSON:", request.get_json(silent=True))
        except Exception as e:
            print("JSON parse error:", e)

        if not is_auth_ok(request):
            logger.warning("SePay webhook unauthorized")
            return jsonify({"ok": False, "error": "unauthorized"}), 401

        payload = request.get_json(silent=True) or {}
        direction, amount, tx_id, content, code = parse_sepay_payload(payload)
        if direction != "in":
            logger.info("SePay webhook ignored: direction=%s", direction)
            return jsonify({"ok": True, "ignored": "direction"}), 200

        order_code = extract_order_code(code, content)
        if not order_code:
            logger.info("SePay webhook ignored: order_code not found")
            return jsonify({"ok": True, "ignored": "order_code"}), 200

        conn = db_connect()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id_user, amount_vnd, amount_usdt, status, product_id, product_qty, product_name FROM recharge_orders WHERE order_code = ?",
                (order_code,),
            )
            row = cursor.fetchone()
            if not row:
                logger.info("SePay webhook ignored: order not found %s", order_code)
                return jsonify({"ok": True, "ignored": "not_found"}), 200

            id_user, amount_vnd, amount_usdt, status, product_id, product_qty, product_name = row
            if status not in ("PENDING", "MARKED"):
                logger.info("SePay webhook ignored: status=%s", status)
                return jsonify({"ok": True, "ignored": "status"}), 200

            if int(amount_vnd) != int(amount):
                logger.info(
                    "SePay webhook ignored: amount mismatch expected=%s got=%s",
                    amount_vnd,
                    amount,
                )
                return jsonify({"ok": True, "ignored": "amount_mismatch"}), 200

            now_vn = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "UPDATE recharge_orders SET status = ?, txid = ?, paid_at = ? WHERE order_code = ?",
                ("SUCCESS", tx_id, now_vn, order_code),
            )
            
            # Nếu là đơn mua trực tiếp (có product_id), không cộng vào balance
            # Nếu là đơn nạp tiền thông thường, cộng vào balance
            is_direct_purchase = product_id and product_qty
            
            if not is_direct_purchase:
                # Đơn nạp tiền thông thường - cộng vào balance
                cursor.execute("SELECT balance FROM users WHERE id_user = ?", (id_user,))
                balance_row = cursor.fetchone()
                current_balance = balance_row[0] if balance_row else 0
                after_balance = current_balance + amount_usdt
                cursor.execute(
                    "UPDATE users SET balance = balance + ? WHERE id_user = ?",
                    (amount_usdt, id_user),
                )
            else:
                # Đơn mua trực tiếp - không cộng vào balance
                cursor.execute("SELECT balance FROM users WHERE id_user = ?", (id_user,))
                balance_row = cursor.fetchone()
                current_balance = balance_row[0] if balance_row else 0
                after_balance = current_balance
            # Nếu có product_id, đây là đơn mua trực tiếp - tự động tạo order và trừ kho
            # Nếu không, đây là đơn nạp tiền thông thường - thêm vào recharge_history
            if not is_direct_purchase:
                cursor.execute(
                    "INSERT INTO recharge_history (id_user, amount, method, status, txid) VALUES (?, ?, ?, ?, ?)",
                    (id_user, amount_usdt, "sepay", "SUCCESS", tx_id),
                )
            
            # Xử lý đơn mua trực tiếp
            if is_direct_purchase:
                try:
                    # Lấy thông tin sản phẩm (bao gồm mode)
                    cursor.execute("SELECT price, quality, mode, descrip FROM listproducts WHERE id_product = ?", (product_id,))
                    product_row = cursor.fetchone()
                    if product_row:
                        product_price, product_stock, product_mode, product_descrip = product_row
                        product_mode = product_mode if product_mode is not None else 0
                        
                        # Kiểm tra tồn kho
                        if product_stock is None or product_stock >= product_qty:
                            # Tạo order ID
                            import random
                            id_order = random.randint(1001, 9999)
                            while True:
                                cursor.execute("SELECT * FROM orders WHERE id_order = ?", (id_order,))
                                if not cursor.fetchone():
                                    break
                                else:
                                    id_order = random.randint(1001, 9999)
                            
                            if product_mode == 0:
                                # Mode 0: Tạo order PENDING, yêu cầu người dùng nhập thông tin
                                cursor.execute(
                                    "INSERT INTO orders (id_order, id_buyer, name, price, quality, status, created_at, product_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                    (id_order, id_user, product_name or product_id, product_price, product_qty, "PENDING", now_vn, product_id)
                                )
                                cursor.execute("UPDATE users SET products_bought = products_bought + 1 WHERE id_user = ?", (id_user,))
                                conn.commit()
                                
                                # Yêu cầu người dùng nhập thông tin
                                from i18n import get_user_language, get_text
                                lang = get_user_language(id_user)
                                if lang == 'vi':
                                    prompt_text = (
                                        f"📝 **Vui lòng nhập thông tin đơn hàng**\n\n"
                                        f"🛍️ Sản phẩm: **{product_name or product_id}**\n"
                                        f"🔢 Số lượng: **{product_qty}**\n"
                                        f"💰 Tổng tiền: **{product_price * product_qty:.2f} USDT**\n"
                                        f"🆔 Mã đơn: `{id_order}`\n\n"
                                    )
                                    if product_descrip and product_descrip.strip() and product_descrip != '@daksdlkasd':
                                        prompt_text += f"**📄 Yêu cầu thông tin:**\n{product_descrip}\n\n"
                                    prompt_text += "💡 Gửi thông tin theo yêu cầu trên. Bot sẽ gửi đơn hàng đến admin để xử lý."
                                else:
                                    prompt_text = (
                                        f"📝 **Please enter order information**\n\n"
                                        f"🛍️ Product: **{product_name or product_id}**\n"
                                        f"🔢 Quantity: **{product_qty}**\n"
                                        f"💰 Total: **{product_price * product_qty:.2f} USDT**\n"
                                        f"🆔 Order ID: `{id_order}`\n\n"
                                    )
                                    if product_descrip and product_descrip.strip() and product_descrip != '@daksdlkasd':
                                        prompt_text += f"**📄 Information required:**\n{product_descrip}\n\n"
                                    prompt_text += "💡 Send the information as requested. Bot will send the order to admin for processing."
                                
                                send_telegram_message(id_user, prompt_text)
                                logger.info(f"Order {id_order} created for direct purchase {order_code} (mode=0, waiting for info)")
                                
                            else:
                                # Mode 1: Tự động giao hàng
                                items_to_deliver = []
                                if product_stock is not None and product_stock > 0:
                                    # Lấy product_qty items từ stock_items (chỉ lấy items chưa bán)
                                    cursor.execute(
                                        "SELECT id, item_content FROM stock_items WHERE product_id = ? AND status = 'PENDING' ORDER BY id LIMIT ?",
                                        (product_id, product_qty)
                                    )
                                    items_to_deliver = cursor.fetchall()
                                    
                                    if len(items_to_deliver) < product_qty:
                                        logger.warning(f"Not enough items in stock_items for {product_id}. Requested: {product_qty}, Available: {len(items_to_deliver)}")
                                    
                                    # Đánh dấu các items đã bán (không xóa, chỉ đổi status)
                                    if items_to_deliver:
                                        item_ids = [item[0] for item in items_to_deliver]
                                        placeholders = ','.join('?' * len(item_ids))
                                        now_vn_str = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d %H:%M:%S")
                                        cursor.execute(
                                            f"UPDATE stock_items SET status = 'SOLD', sold_at = ?, sold_to_user_id = ?, sold_order_id = ? WHERE id IN ({placeholders})",
                                            (now_vn_str, id_user, id_order, *item_ids)
                                        )
                                    
                                    # Trừ kho trong listproducts
                                    cursor.execute("UPDATE listproducts SET quality = quality - ? WHERE id_product = ?", (product_qty, product_id))
                                
                                cursor.execute(
                                    "INSERT INTO orders (id_order, id_buyer, name, price, quality, status, created_at, product_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                    (id_order, id_user, product_name or product_id, product_price, product_qty, "DONE", now_vn, product_id)
                                )
                                cursor.execute("UPDATE users SET products_bought = products_bought + 1 WHERE id_user = ?", (id_user,))
                                conn.commit()
                                
                                # Gửi items cho người dùng
                                from i18n import get_text
                                purchase_success = i18n_get_text(
                                    id_user,
                                    "products.purchase_success"
                                )
                                
                                if items_to_deliver:
                                    send_telegram_message(
                                        id_user,
                                        f"📦 **{purchase_success}**\n🛍️ {product_name or product_id}\n🔢 Số lượng: {product_qty}\n💰 Tổng tiền: {product_price * product_qty:.2f} USDT\n🆔 Order ID: {id_order}\n\n**Chi tiết đơn hàng:**"
                                    )
                                    for idx, (item_id, item_content) in enumerate(items_to_deliver, 1):
                                        send_telegram_message(
                                            id_user,
                                            f"**Item {idx}/{len(items_to_deliver)}:**\n```\n{item_content}\n```"
                                        )
                                else:
                                    purchase_detail = (
                                        f"✅ **{purchase_success}**\n"
                                        f"🛍️ Sản phẩm: {product_name or product_id}\n"
                                        f"🔢 Số lượng: {product_qty}\n"
                                        f"💰 Tổng tiền: {product_price * product_qty:.2f} USDT\n"
                                        f"🆔 Order ID: {id_order}\n\n"
                                        f"⚠️ Vui lòng liên hệ admin để nhận hàng."
                                    )
                                    send_telegram_message(id_user, purchase_detail)
                                
                                # Gửi thông báo cho admin
                                from config import settings
                                admin_order_msg = (
                                    f"🛒 Đơn hàng mới (Mua trực tiếp)\n"
                                    f"👤 User: {id_user}\n"
                                    f"🆔 Order ID: {id_order}\n"
                                    f"🛍️ Sản phẩm: {product_name or product_id}\n"
                                    f"🔢 Số lượng: {product_qty}\n"
                                    f"💰 Tổng: {product_price * product_qty:.2f} USDT"
                                )
                                if items_to_deliver:
                                    admin_order_msg += f"\n📦 Đã giao {len(items_to_deliver)} item tự động"
                                send_telegram_message(app_settings.ADMIN_ID, admin_order_msg)
                                
                                logger.info(f"Auto-created order {id_order} for direct purchase {order_code}, delivered {len(items_to_deliver)} items")
                        else:
                            logger.warning(f"Product {product_id} out of stock for direct purchase {order_code}")
                            send_telegram_message(id_user, f"❌ Sản phẩm {product_name or product_id} đã hết hàng. Vui lòng liên hệ admin để được hoàn tiền.")
                except Exception as e:
                    logger.exception(f"Error creating order for direct purchase {order_code}: {e}")
            
            conn.commit()

            # Gửi thông báo nạp tiền thành công (chỉ nếu không phải mua trực tiếp)
            if not product_id:
                user_message = i18n_get_text(
                    id_user,
                    "sepay.success",
                    order_code=order_code,
                    amount_vnd=amount_vnd,
                    amount_usdt=amount_usdt,
                )
                send_telegram_message(id_user, user_message)

            admin_recharge_success = i18n_get_text(
                id_user,
                "admin.recharge_success",
                buyer_id=id_user,
                order_code=order_code,
                amount=amount_vnd,
                current_balance=current_balance,
                after_balance=after_balance,
            )
            send_telegram_message(app_settings.ADMIN_ID, admin_recharge_success)

            return jsonify({"ok": True}), 200

        finally:
            cursor.close()
            conn.close()

    except Exception as e:
        logger.exception("SePay webhook crashed: %s", e)
        print("TRACEBACK:\n", traceback.format_exc())
        return jsonify({"ok": False, "error": "server_error"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=app_settings.PORT)
