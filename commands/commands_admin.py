from sqlalchemy import text
from telegram import Update
from config import settings
from telegram.ext import ContextTypes
from sqlite3 import connect
import os
import logging
from telegram.error import RetryAfter, Forbidden, BadRequest
import asyncio
from telegram.constants import ParseMode
from commands.dbconfig import db_connect
from i18n import get_text, get_user_language
import random, html
from telegram.helpers import escape_markdown

async def check_stock_add_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is in stock_add flow. If yes, notify and return True."""
    if context.user_data.get("stock_add_pending"):
        product_id = context.user_data.get("stock_add_product_id", "N/A")
        count = context.user_data.get("stock_add_count", 0)
        if update.message:
            await update.message.reply_text(
                f"⚠️ Bạn đang trong quá trình nhập kho cho sản phẩm {product_id}.\n"
                f"📊 Đã nhập: {count} item\n"
                f"💡 Gửi tiếp nội dung kho hoặc dùng /done để kết thúc."
            )
        return True
    return False

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO,
                    filename = "action.log",
                    filemode='a' # ghi noi tiep khong ghi de
                    )
logger = logging.getLogger(__name__)

async def analyst_pr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Phân tích chi tiết 1 sản phẩm theo IDpr: bán ra, doanh thu, top buyer, mapping item SOLD/PENDING."""
    if not update.message:
        return

    caller_id = update.message.from_user.id
    text = (update.message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text(
            "❌ Thiếu ID sản phẩm.\nVD: <code>/analystPr NET1M</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    product_id = parts[1].strip().upper()

    # Permission: main admin hoặc subadmin
    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM subadmins WHERE id_user = ?", (caller_id,))
        is_sub = cursor.fetchone() is not None
        if caller_id != settings.ADMIN_ID and not is_sub:
            await update.message.reply_text("❌ Bạn không có quyền dùng lệnh này.")
            return

        # Product info
        cursor.execute(
            "SELECT id_product, name, price, quality, mode, descrip FROM listproducts WHERE id_product = ?",
            (product_id,),
        )
        prod = cursor.fetchone()
        if not prod:
            await update.message.reply_text(f"❌ Không tìm thấy sản phẩm: <code>{html.escape(product_id)}</code>", parse_mode=ParseMode.HTML)
            return
        pid, name, price, quality, mode, descrip = prod

        # Sales summary (DONE)
        cursor.execute(
            """
            SELECT
                COALESCE(SUM(quality), 0) AS sold_qty,
                COALESCE(SUM(price * quality), 0) AS revenue,
                COUNT(*) AS orders_count
            FROM orders
            WHERE product_id = ?
              AND UPPER(status) = 'DONE'
            """,
            (product_id,),
        )
        sold_qty, revenue, orders_count = cursor.fetchone() or (0, 0, 0)

        # Top buyers
        cursor.execute(
            """
            SELECT
                o.id_buyer,
                COALESCE(u.user_name, '') AS user_name,
                COALESCE(SUM(o.quality), 0) AS qty,
                COALESCE(SUM(o.price * o.quality), 0) AS spend
            FROM orders o
            LEFT JOIN users u ON u.id_user = o.id_buyer
            WHERE o.product_id = ?
              AND UPPER(o.status) = 'DONE'
            GROUP BY o.id_buyer
            ORDER BY spend DESC, qty DESC
            LIMIT 5
            """,
            (product_id,),
        )
        top_buyers = cursor.fetchall() or []

        # Stock counts
        cursor.execute(
            "SELECT COALESCE(SUM(CASE WHEN status='PENDING' THEN 1 ELSE 0 END),0), COALESCE(SUM(CASE WHEN status='SOLD' THEN 1 ELSE 0 END),0) FROM stock_items WHERE product_id = ?",
            (product_id,),
        )
        pending_cnt, sold_cnt_items = cursor.fetchone() or (0, 0)

        # SOLD items list (newest first) with buyer mapping (if available)
        cursor.execute(
            """
            SELECT s.id, s.sold_at, s.sold_to_user_id, COALESCE(u.user_name,''), s.sold_order_id, s.item_content
            FROM stock_items s
            LEFT JOIN users u ON u.id_user = s.sold_to_user_id
            WHERE s.product_id = ? AND s.status = 'SOLD'
            ORDER BY s.id DESC
            LIMIT 30
            """,
            (product_id,),
        )
        sold_items = cursor.fetchall() or []

        # PENDING items list (oldest first)
        cursor.execute(
            """
            SELECT s.id, s.created_at, s.item_content
            FROM stock_items s
            WHERE s.product_id = ? AND s.status = 'PENDING'
            ORDER BY s.id ASC
            LIMIT 30
            """,
            (product_id,),
        )
        pending_items = cursor.fetchall() or []

        def preview(s: str, n: int = 60) -> str:
            s = (s or "").replace("\n", " ").strip()
            if len(s) <= n:
                return s
            return s[: n - 1] + "…"

        lines = []
        lines.append("📊 <b>ANALYST PRODUCT</b>")
        lines.append(f"🆔 ID: <code>{html.escape(str(pid))}</code>")
        lines.append(f"🛍️ Tên: <b>{html.escape(str(name))}</b>")
        lines.append(f"💰 Giá: <code>{price:.2f}</code>")
        lines.append(f"⚙️ Mode: <code>{int(mode or 0)}</code> (0=manual, 1=auto)")
        lines.append(f"📦 Stock (listproducts.quality): <code>{int(quality or 0)}</code>")
        lines.append("")

        lines.append("💵 <b>Doanh số</b>")
        lines.append(f"• Đơn DONE: <code>{int(orders_count)}</code>")
        lines.append(f"• Số lượng bán ra: <code>{int(sold_qty)}</code>")
        lines.append(f"• Doanh thu: <code>{float(revenue):.2f}</code> USDT")
        lines.append("")

        lines.append("👑 <b>Top người mua</b> (Top 5)")
        if not top_buyers:
            lines.append("• (Chưa có dữ liệu)")
        else:
            for idx, (buyer_id, buyer_name, qty_b, spend_b) in enumerate(top_buyers, 1):
                display_name = buyer_name or "N/A"
                lines.append(
                    f"{idx}) <code>{int(buyer_id)}</code> — {html.escape(str(display_name))} | qty=<code>{int(qty_b)}</code> | spend=<code>{float(spend_b):.2f}</code>"
                )
        lines.append("")

        lines.append("📦 <b>Kho theo stock_items</b>")
        lines.append(f"• PENDING: <code>{int(pending_cnt)}</code>")
        lines.append(f"• SOLD: <code>{int(sold_cnt_items)}</code>")
        lines.append("")

        lines.append("✅ <b>Danh sách item SOLD</b> (mới nhất, tối đa 30)")
        if not sold_items:
            lines.append("• (Chưa có item SOLD hoặc item SOLD từ trước chưa có tracking buyer)")
        else:
            for (sid, sold_at, sold_to, sold_to_name, sold_order_id, content) in sold_items:
                buyer_part = "UNKNOWN"
                if sold_to:
                    buyer_part = f"{int(sold_to)} ({html.escape(sold_to_name or 'N/A')})"
                order_part = f"{int(sold_order_id)}" if sold_order_id else "N/A"
                lines.append(
                    f"• <code>{sid}</code> | order=<code>{order_part}</code> | buyer=<code>{html.escape(buyer_part)}</code> | at=<code>{html.escape(str(sold_at or ''))}</code>\n"
                    f"  <i>{html.escape(preview(content))}</i>"
                )
        lines.append("")

        lines.append("🟡 <b>Danh sách item PENDING</b> (cũ nhất, tối đa 30)")
        if not pending_items:
            lines.append("• (Không còn item PENDING)")
        else:
            for (sid, created_at, content) in pending_items:
                lines.append(
                    f"• <code>{sid}</code> | at=<code>{html.escape(str(created_at or ''))}</code>\n"
                    f"  <i>{html.escape(preview(content))}</i>"
                )

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    finally:
        cursor.close()
        conn.close()



#block_user {id}
async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    # lay du lieu tu data base
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT id_user FROM subadmins")
    rows = cursor.fetchall()


    caller_id = update.message.from_user.id
    text = (update.message.text)
    safe_text = escape_markdown(text or "", version=1)  # Markdown (legacy)
    safe_id = escape_markdown(str(caller_id), version=1)

    msg = f"🟢 ID:`{safe_id}`\nUsed: {safe_text}"
    await context.bot.send_message(text=msg, chat_id=settings.ADMIN_ID, parse_mode="Markdown")

    data = text.split()

    if len(data) != 2:
        logger.info(f"{caller_id} /blockuser INvalid data")
        await update.message.reply_text(f"❌ Invalid syntax")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        return

    text = data[1]

    subAdmins = [r[0] for r in rows]
    if caller_id not in subAdmins and caller_id != settings.ADMIN_ID:
        logger.info(f"{caller_id} use block_user but NOT ADMIN")
        await update.message.reply_text(f"❌You aren't sub admin")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        cursor.close()
        conn.close()
        return
    
    try: 
        id_client = int(text)
    except:
        logger.info(f"{caller_id} entered INVALID data")
        await update.message.reply_text("❌ Your command is INVALID")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        cursor.close()
        conn.close()
        return

    if id_client == settings.ADMIN_ID:
        logger.info(f"You can't block ADMIN")
        await update.message.reply_text(f"❌ Block MAIN ADMIN isn't allow")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        cursor.close()
        conn.close()
        return

    cursor.execute("SELECT * FROM users WHERE id_user = ? and is_blocked = 0",(id_client,))
    row = cursor.fetchone()

    if not row:
        logger.info(f"{id_client} isn't found")
        await update.message.reply_text(f"❌ {id_client} isn't found")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        cursor.close()
        conn.close()
        return
    
    cursor.execute("UPDATE users SET is_blocked = 1 WHERE id_user = ?", (id_client,))
    cursor.close()
    conn.commit()
    conn.close()
    logger.info(f"Blocked user {id_client} successfully")
    await update.message.reply_text(f"✅ Blocked user {id_client} successfully")
    await context.bot.send_message(text=f"✅ ID:`{caller_id}` SUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
    return
    
#unblock_user
async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # kiem tra co nhan tin nhan hay khong
    if not update.message:
        return
    
    caller_id = update.message.from_user.id

    text = update.message.text
    safe_text = escape_markdown(text or "", version=1)  # Markdown (legacy)
    safe_id = escape_markdown(str(caller_id), version=1)

    msg = f"🟢 ID:`{safe_id}`\nUsed: {safe_text}"
    await context.bot.send_message(text=f"{msg}", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
    data = text.split()

    if len(data) != 2:
        logger.info(f"{caller_id} /blockuser INvalid data")
        await update.message.reply_text(f"❌ Invalid syntax")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        return

    text = data[1]

    # kiem tra caller cos phai la subadmins hay khong

    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM subadmins WHERE id_user = ?", (caller_id,))
    data = cursor.fetchall()

    if (caller_id == settings.ADMIN_ID) or data:
        pass
    else:
        logger.info(f"{caller_id} isn't admin")
        await update.message.reply_text(f"❌ You aren't Admin")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        cursor.close()
        conn.close()
        return

    cursor.execute("SELECT id_user FROM users WHERE is_blocked = 1")
    id_users = cursor.fetchall()

    if caller_id in id_users:
        logger.info(f"You are blocked")
        await update.message.reply_text(f"❌ You are blocked")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")

    if not id_users:
        logger.info("No user is blocked")
        await update.message.reply_text(f"❌ ID: {text} not found")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        return

    cursor.execute("UPDATE users SET is_blocked = 0 WHERE id_user = ?", (text,))
    conn.commit()
    cursor.close()
    conn.close()

    logger.info(f"Unblock {text} successfully")
    await update.message.reply_text(f"✅ Unblock {text} successfully")
    await context.bot.send_message(text=f"✅ ID:`{caller_id}` SUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")

    return   

# Hàm liệt kê tất cả người dùng
async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # Kiểm tra xem có tin nhắn không
    if not update.message:
        return
    
    caller_id = update.message.from_user.id # Lay ID nguoi gui tin nhan
    text = update.message.text
    await context.bot.send_message(text=f"🟢 ID:`{caller_id}`\nUsed: {text} ", chat_id=settings.ADMIN_ID, parse_mode="Markdown")


    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT id_user FROM subadmins WHERE id_user = ?", (caller_id,))
    data = cursor.fetchone()

    if (caller_id != settings.ADMIN_ID) and not data:
        logger.info(f"Attempt to list Users without ADMIN ID")
        await update.message.reply_text("❌[Error] You aren't ADMIN or SubAdmin")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        cursor.close()
        conn.close()
        return
    
    cursor.execute("SELECT id_user, user_name FROM users")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    # Kiểm tra xem có người dùng không
    if not rows:
        logger.info(f"Listed Users: No Users in shop, Requested by ADMIN ID={caller_id}")
        await update.message.reply_text("❌ **No Users in shop.**", parse_mode="Markdown")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        return

    # Tạo tin nhắn trả về danh sách người dùng
    text_reply = "📋 **List of Users:**\n"
    i = 1
    for row in rows:
        user_name = row[1]
        user_id = row[0]    
        text_reply += f"ID{i}: `{user_id}` : {user_name}\n"
        i = i+1

    logger.info(f"Listed Users: Requested by ADMIN ID={caller_id}")
    await update.message.reply_text(text_reply, parse_mode="MarkdownV2")
    await context.bot.send_message(text=f"✅ ID:`{caller_id}` SUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
    return

# hàm gửi tin nhắn đến toàn bộ người dùng
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    caller_id = update.message.from_user.id
    text = update.message.text
    await context.bot.send_message(text=f"🟢 ID:`{caller_id}`\nUsed: {text} ", chat_id=settings.ADMIN_ID, parse_mode="Markdown")


    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT id_user FROM subadmins WHERE id_user = ?", (caller_id,))
    data = cursor.fetchone()

    from_sub = False
    if data:
        from_sub = True

    if caller_id != settings.ADMIN_ID and not data:
        logger.info(f"{caller_id} used /broadcast, but is not ADMIN or Subadmins")
        await update.message.reply_text("❌ You aren't ADMIN or SubAdmin")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        return  # QUAN TRỌNG: dừng tại đây


    reply_to = update.message.reply_to_message
    if reply_to:
        mode = "copy"
    else:
        # Lấy nội dung sau lệnh /broadcast
        text = (update.message.text or "").strip()
        parts = text.split(" ", 1)
        if len(parts) < 2 or not parts[1].strip():
            await update.message.reply_text("❌ Syntax error.")
            await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
            return
        message_text = parts[1].strip()
        mode = "text"

    # Lấy danh sách user hợp lệ
    cursor.execute("SELECT id_user FROM users WHERE is_blocked = 0")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        await update.message.reply_text("❌ No users to broadcast.")
        return

    # Bóc tách ID (rows: list[tuple])
    user_ids = [r[0] for r in rows]

    sent = failed = 0 # khởi tạo số lượng tin nhắn gửi thành công và tin nhắn gửi lỗi
    status = await update.message.reply_text(f"🚀 Bắt đầu gửi đến {len(user_ids)} users...")

    # index bắt đầu từ 1 - id (cặp idx - id)
    for idx, chat_id_raw in enumerate(user_ids, start=1):
        # chuẩn hoá về int, tránh khoảng trắng/ký tự lạ
        try:
            chat_id = int(str(chat_id_raw).strip())
            
        except Exception:
            failed += 1
            logger.warning(f"Invalid chat_id in DB: {chat_id_raw!r}")
            continue
        
        # bỏ qua nếu ID trùng với admin
        if (chat_id == settings.ADMIN_ID and not from_sub) or (chat_id == caller_id and from_sub):
                continue

        try:
            if mode == "copy":
                await context.bot.copy_message(chat_id=chat_id, from_chat_id=reply_to.chat_id, message_id=reply_to.message_id)
            elif mode == "text": 
                await context.bot.send_message(chat_id=chat_id, text=message_text, parse_mode=ParseMode.HTML)
            sent += 1
            logger.info(f"Sent to {chat_id}")
        # Kiểm tra lỗi bị quá thời gian, phải thử gửi lại sau
        except RetryAfter as e:
            wait = getattr(e, "retry_after", 1)
            logger.warning(f"RetryAfter {wait}s for {chat_id}")
            await asyncio.sleep(float(wait) + 1.0)
            # thử lại 1 lần
            try:
                await context.bot.send_message(chat_id=chat_id, text=message_text, parse_mode=ParseMode.HTML)
                sent += 1
            except Exception as e2:
                failed += 1
                logger.exception(f"Retry failed for {chat_id}: {e2}")
        except Forbidden:
            failed += 1
            logger.info(f"Forbidden (user blocked or no chat) {chat_id}")
            # đánh dấu is_blocked để lần sau bỏ qua
            try:
                conn = db_connect()
                conn.execute("UPDATE users SET is_blocked = 1 WHERE id_user = ?", (chat_id,))
                conn.commit()
                conn.close()
            except Exception:
                logger.exception("Failed to mark is_blocked")
        except BadRequest as e:
            failed += 1
            logger.warning(f"BadRequest for {chat_id}: {e}")
        except Exception as e:
            failed += 1
            logger.exception(f"Unexpected error sending to {chat_id}: {e}")

        if idx % 50 == 0 or idx == len(user_ids):
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=status.message_id,
                    text=f"📣 Tiến độ: {idx}/{len(user_ids)}\n✅ Sent: {sent}\n❌ Failed: {failed}"
                )
            except Exception:   
                pass


    await update.message.reply_text(f"✅ Hoàn tất.\nTổng: {len(user_ids)}\nSent: {sent}\nFailed: {failed}")
    await context.bot.send_message(text=f"✅ ID:`{caller_id}` SUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")

# Help sub admin
async def help_subadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # kiem tra co nhan tin nhan hay khong
    if not update.message:
        return
    
    caller_id = update.message.from_user.id
    msg = update.message.text
    safe_msg = html.escape(str(msg))
    text = f"🟢 ID: <code>{caller_id}</code>\nUsed: {safe_msg}"
    await context.bot.send_message(text=text, chat_id=settings.ADMIN_ID, parse_mode=ParseMode.HTML)

    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT id_user FROM subadmins WHERE id_user = ?", (caller_id,))
    row = cursor.fetchone()
    
    if (settings.ADMIN_ID != caller_id) and (not row):
        logger.info(f"{caller_id} user help_subadmin UN successfully")
        await update.message.reply_text(f"❌ You aren't Sub ADMIN")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        return
    
    lang = get_user_language(caller_id)
    if lang == "vi":
        text = (
            "📋 <b>HƯỚNG DẪN SUBADMIN</b>\n\n"
            "🧾 <b>Sản phẩm</b>\n"
            "• <code>/addproduct Name | Price | IDpr | Mode</code>\n"
            "  - Mode: 0 (thủ công) / 1 (tự động)\n"
            "  - Sau khi thêm, bot sẽ hỏi mô tả (gửi /skip để bỏ qua)\n"
            "  VD: <code>/addproduct Netflix 1M | 99 | NET1M | 1</code>\n"
            "• <code>/removeproduct IDpr</code>\n"
            "• <code>/updatestock IDpr quality</code>\n"
            "• <code>/ad_products</code> — Xem nhanh sản phẩm: ID | Tên | Price | Stock | Sold\n\n"
            "📦 <b>Kho (stock items)</b>\n"
            "• <code>/pushItem IDpr</code> — Nhập kho (gõ nhiều dòng, kết thúc bằng <code>/done</code>)\n"
            "  - Mỗi tin nhắn = 1 item\n"
            "  - Có thể nhập nhiều item bằng cách ngăn bởi <code>=====</code>\n"
            "• <code>/pullItem IDpr</code> — Kéo hàng về (flow)\n"
            "• <code>/pullItems IDpr 1,2,3</code> — Kéo theo thứ tự (chỉ PENDING)\n"
            "• <code>/myStocks</code> — Tổng quan kho\n"
            "• <code>/myStock IDpr</code> — Chi tiết kho theo IDpr\n\n"
            "📋 <b>Đơn hàng</b>\n"
            "• <code>/listorders</code> — Xem toàn bộ đơn\n"
            "• <code>/listorders user_id</code> — Lọc theo user\n"
            "• Đơn mode=0: xử lý bằng nút <b>✅ Xác nhận / ❌ Hủy / 🔇 Mute</b> trong tin nhắn order\n\n"
            "👥 <b>Người dùng</b>\n"
            "• <code>/users</code>\n"
            "• <code>/detailuser user_id</code>\n"
            "• <code>/block_user user_id</code> / <code>/unblock_user user_id</code>\n"
            "• <code>/banlist</code>\n\n"
            "💬 <b>Nhắn tin</b>\n"
            "• <code>/broadcast text</code> (hoặc reply tin nhắn rồi <code>/broadcast</code>)\n"
            "• <code>/message |user_id|text</code> (hoặc reply rồi <code>/message user_id</code>)\n\n"
            "ℹ️ <b>Khác</b>\n"
            "• <code>/help_subadmin</code> — Xem hướng dẫn này\n"
        )
    else:
        text = (
            "📋 <b>SUBADMIN HELP</b>\n\n"
            "🧾 <b>Products</b>\n"
            "• <code>/addproduct Name | Price | IDpr | Mode</code>\n"
            "  - Mode: 0 (manual) / 1 (auto)\n"
            "  - Bot will ask for description after adding (send /skip to skip)\n"
            "  Ex: <code>/addproduct Netflix 1M | 99 | NET1M | 1</code>\n"
            "• <code>/removeproduct IDpr</code>\n"
            "• <code>/updatestock IDpr quality</code>\n"
            "• <code>/ad_products</code> — Quick list: ID | Name | Price | Stock | Sold\n\n"
            "📦 <b>Stock (stock items)</b>\n"
            "• <code>/pushItem IDpr</code> — Add stock (end with <code>/done</code>)\n"
            "  - 1 message = 1 item\n"
            "  - You can batch items separated by <code>=====</code>\n"
            "• <code>/pullItem IDpr</code> — Pull back (flow)\n"
            "• <code>/pullItems IDpr 1,2,3</code> — Pull by index (PENDING only)\n"
            "• <code>/myStocks</code> — Stock overview\n"
            "• <code>/myStock IDpr</code> — Stock details by IDpr\n\n"
            "📋 <b>Orders</b>\n"
            "• <code>/listorders</code>\n"
            "• <code>/listorders user_id</code>\n"
            "• Mode=0 orders: use buttons <b>✅ Confirm / ❌ Cancel / 🔇 Mute</b> in order message\n\n"
            "👥 <b>Users</b>\n"
            "• <code>/users</code>\n"
            "• <code>/detailuser user_id</code>\n"
            "• <code>/block_user user_id</code> / <code>/unblock_user user_id</code>\n"
            "• <code>/banlist</code>\n\n"
            "💬 <b>Messaging</b>\n"
            "• <code>/broadcast text</code> (or reply + <code>/broadcast</code>)\n"
            "• <code>/message |user_id|text</code> (or reply + <code>/message user_id</code>)\n\n"
            "ℹ️ <b>Other</b>\n"
            "• <code>/help_subadmin</code> — Show this help\n"
        )
    logger.info(f"Sent help admin to SUB ADMIN")
    await update.message.reply_text(text=text, parse_mode=ParseMode.HTML)
    await context.bot.send_message(text=f"✅ ID:`{caller_id}` SUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
    return


# detail userid
async def detailuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    caller_id = update.message.from_user.id
    text = update.message.text
    await context.bot.send_message(text=f"🟢 ID:`{caller_id}`\nUsed: {text} ", chat_id=settings.ADMIN_ID, parse_mode="Markdown")

    conn = db_connect()
    cursor = conn.cursor()

    # lay data subadmins
    cursor.execute("SELECT id_user FROM subadmins WHERE id_user = ?", (caller_id,))
    row = cursor.fetchone()
    
    # kiem thu co phai admin hay subadmin hay khong
    if not row and caller_id != settings.ADMIN_ID:
        logger.info(f"{caller_id} detailuser call fail")
        await update.message.reply_text(f"❌ You aren't admin or subadmin")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        cursor.close()
        conn.close()
        return
    
    text = update.message.text
    parts = text.split(" ", 1)
    if len(parts) != 2:
        logger.info(f"{caller_id} Syntax error")
        await update.message.reply_text(f"❌ Syntax error.")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        return
    id = parts[1]
    
    try:
        user_id = int(id)
        if user_id == settings.ADMIN_ID:
            logger.info("Check info mAdmin isn't allow")
            await update.message.reply_text("❌ Check mAdmin isn't allow")
            await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
            return
    except:
        logger.info("/detailuser ID is not valid")
        await update.message.reply_text("❌ ID isn't valid")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        cursor.close()
        conn.close()
        return
 
    cursor.execute("SELECT * FROM users WHERE id_user = ?", (user_id,))
    row = cursor.fetchone()

    if not row:
        logger.info(f"{user_id} not found")
        await update.message.reply_text("❌ User isn't Exist")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        cursor.close()
        conn.close()
        return
    
    user = {
        "id_user":     row[0],
        "user_name":   row[1],
        "balance":     row[2],
        "currency":    row[3],
        "is_subadmin": bool(row[4]),
        "is_blocked":  bool(row[5]),
        "products_bought": row[6],
        "created_at":  row[7],
    }

            # Format tin nhắn trả lời 
    msg = (
        "👤 Your account information:\n"
        f"• ID: {user['id_user']}\n"
        f"• Username: {user['user_name']}\n"
        f"• Balance: {user['balance']} {user['currency']}\n"
        f"• Currency: {user['currency']}\n"
        f"• Sub-admin: {'✅' if user['is_subadmin'] else '❌'}\n"
        f"• Is Blocked: {'✅' if user['is_blocked'] else '❌'}\n"
        f"• Products Bought: {user['products_bought']}\n"
        f"• Created at: {user['created_at']}"
    )

    logger.info(f"Display user {user_id} Successfully")
    await update.message.reply_text(text = msg, parse_mode=ParseMode.HTML)
    await context.bot.send_message(text=f"✅ ID:`{caller_id}` SUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
    return


# addproduct
async def addproduct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    # Check nếu đang trong quá trình nhập kho
    if await check_stock_add_flow(update, context):
        return
    
    caller_id = update.message.from_user.id
    text = update.message.text
    await context.bot.send_message(text=f"🟢 ID:`{caller_id}`\nUsed: {text} ", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM subadmins WHERE id_user = ?", (caller_id,))
    row = cursor.fetchone()

    if caller_id != settings.ADMIN_ID and not row:
        logger.info(f"/addproduct not mAdmin or sAdmin")
        await update.message.reply_text(f"❌ You aren't mAdmin or sAdmin")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        cursor.close()
        conn.close()
        return
    
    text = update.message.text.split(" ",1)[1]
    data = [item.strip() for item in text.split("|")]

    try:
        name = str(data[0])
    except:
        logger.info(f"{caller_id} /addproduct name fail")
        await update.message.reply_text("❌ Data name fail")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        cursor.close()
        conn.close()
        return

    try:
        price = float(data[1])
    except:
        logger.info(f"{caller_id} /addproduct price fail")
        await update.message.reply_text("❌ Data price fail")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        cursor.close()
        conn.close()
        return
    
    try:
        # Lấy ID sản phẩm và format thành chữ in hoa (hỗ trợ cả chữ và số)
        ID_product_raw = str(data[2]).strip()
        ID_product = ID_product_raw.upper()  # Tự động format chữ in hoa
    except:
        logger.info(f"{caller_id} /addproduct id_product fail")
        await update.message.reply_text("❌ Data ID product fail")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        cursor.close()
        conn.close()
        return
    
    # Mode là tùy chọn (mặc định 0)
    mode = 0
    if len(data) >= 4:
        try:
            mode = int(data[3])
            if mode not in [0, 1]:
                mode = 0
        except:
            mode = 0

    # Kiểm tra xem sản phẩm với ID này đã tồn tại chưa
    cursor.execute("SELECT id_product FROM listproducts WHERE id_product = ?", (ID_product,))
    existing_product = cursor.fetchone()
    
    if existing_product:
        # Nếu sản phẩm đã tồn tại, UPDATE thông tin mới
        cursor.execute("UPDATE listproducts SET name = ?, price = ?, mode = ? WHERE id_product = ?", (name, price, mode, ID_product))
        conn.commit()
        logger.info(f"Product {ID_product} updated successfully (mode={mode})")
        await update.message.reply_text(f"✅ Product updated successfully! (ID: {ID_product}, Mode: {mode})")
        action_type = "updated"
    else:
        # Nếu sản phẩm chưa tồn tại, INSERT mới
        cursor.execute("INSERT INTO listproducts(id_product, name, price, mode) VALUES (?, ?, ?, ?)", (ID_product, name, price, mode))
        conn.commit()
        logger.info(f"Product {ID_product} added successfully (mode={mode})")
        await update.message.reply_text(f"✅ Product added successfully! (ID: {ID_product}, Mode: {mode})")
        action_type = "added"
    
    cursor.close()
    conn.close()
    
    # Yêu cầu nhập mô tả sản phẩm (chỉ khi thêm mới, hoặc có thể cho cả update)
    context.user_data["awaiting_product_description"] = True
    context.user_data["product_description_id"] = ID_product
    context.user_data["active_flow"] = "product_description"
    
    await update.message.reply_text(get_text(caller_id, 'products.description_prompt'))
    await context.bot.send_message(text=f"✅ ID:`{caller_id}` SUCCESSFULLY ({action_type} product {ID_product})", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
    return

# deleteproduct
async def removeproduct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    # Check nếu đang trong quá trình nhập kho
    if await check_stock_add_flow(update, context):
        return
    
    caller_id = update.message.from_user.id
    text = update.message.text
    await context.bot.send_message(text=f"🟢 ID:`{caller_id}`\nUsed: {text} ", chat_id=settings.ADMIN_ID, parse_mode="Markdown")

    conn = db_connect()
    cursor = conn.cursor()

    # kiem tra nguoi dung lenh co phai la admin hay khong
    cursor.execute("SELECT * FROM subadmins WHERE id_user = ?", (caller_id,))
    row = cursor.fetchone()
    
    # check dieu kien co phai la mAdmin hay sAdmin hay khong
    if (not row) and (caller_id != settings.ADMIN_ID):
        logger.info(f"{caller_id} /removeproduct error user")
        await update.message.reply_text("❌ You aren't mAdmin or sAdmin")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        cursor.close()
        conn.close()
        return

    text = update.message.text.split()

    # check data dau vao co hop le hay khong
    if len(text) != 2:
        logger.infor(f"/removeproduct Invalid syntax")
        await update.message.reply_text("❌ Invalid syntax") 
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        cursor.close()
        conn.close()   
        return
    
    # Format ID sản phẩm thành chữ in hoa (hỗ trợ cả chữ và số)
    try:
        id_product = str(text[1]).strip().upper()
    except:
        logger.info("/removeproduct invalid id")
        await update.message.reply_text("❌ ID invalid")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        cursor.close()
        conn.close()
        return

    # tim id product trongg db
    cursor.execute("SELECT id_product FROM listproducts WHERE id_product = ?", (id_product,))
    row = cursor.fetchone()

    # Kiem tra id product co ton tai hay khong
    if not row:
        logger.info("/removeproduct ID not found")
        await update.message.reply_text("❌ ID not found")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        cursor.close()
        conn.close()
        return
    
    # thuc hien xoas
    cursor.execute("DELETE FROM listproducts WHERE id_product = ?", (id_product,))
    conn.commit()
    cursor.close()
    conn.close()

    logger.info(f"{caller_id} Deleted product {id_product}")
    await update.message.reply_text(f"✅ Delete product ID: {id_product} successfully")
    await context.bot.send_message(text=f"✅ ID:`{caller_id}` SUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
    return

# bandlist
async def banlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    conn = db_connect()
    cursor = conn.cursor()

    caller_id = update.message.from_user.id
    text = update.message.text
    await context.bot.send_message(text=f"🟢 ID:`{caller_id}`\nUsed: {text} ", chat_id=settings.ADMIN_ID, parse_mode="Markdown")

    try:
        cursor.execute("SELECT * FROM subadmins WHERE id_user = ? ", (caller_id,))
        row = cursor.fetchone()

        if not row and caller_id != settings.ADMIN_ID:
            logger.info(f"{caller_id} /bandlist isn't admin")
            await update.message.reply_text("❌ Access isn't allow")
            await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
            return
        
        cursor.execute("SELECT * FROM users WHERE is_blocked = 1")
        rows = cursor.fetchall()

        if not rows:
            logger.info("No user is banned")
            await update.message.reply_text("❌ No user is banned")
            await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
            return 
                
        text = "**List ID banned:\n"
        i = 1
        for row in rows:
            user_id = row[0]    
            text += f"**ID**{i}: `{user_id}`\n"
            i = i+1

        logger.info(f"{caller_id} used banlist")
        await update.message.reply_text(text = text, parse_mode="Markdown")
        await context.bot.send_message(text=f"✅ ID:`{caller_id}` SUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")

    finally:
        cursor.close()
        conn.close()
        return


# listorders
async def listorders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    caller_id = update.message.from_user.id
    text = update.message.text
    await context.bot.send_message(text=f"🟢 ID:`{caller_id}`\nUsed: {text} ", chat_id=settings.ADMIN_ID, parse_mode="Markdown")

    conn = db_connect()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM subadmins WHERE id_user = ?", (caller_id,))
        if not cursor.fetchone() and caller_id != settings.ADMIN_ID:
            logger.info(f"{caller_id} /listorders no msAdmin")
            await update.message.reply_text("❌ You aren't mAdmin or sAdmin")
            await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
            return
        
        text_user = update.message.text
        parts = text_user.split(" ")
        if len(parts) > 2:
            logger.info(f"{caller_id} Invalid syntax")
            await update.message.reply_text("❌ Invalid syntax")
            await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
            return
        
        if len(parts == 1):
            cursor.execute("SELECT id_order, id_buyer, name, price, quality, created_at FROM orders")
            rows = cursor.fetchall()

            if not rows:
                logger.info("No orders in DB")
                await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
                await update.message.reply_text("❌ No orders in DB")
                return
            
            for idx, row in enumerate(rows, 1):
                id_order   = html.escape(str(row[0]))
                id_buyer   = html.escape(str(row[1]))
                name       = html.escape(str(row[2]))
                price      = html.escape(str(row[3]))
                quality    = html.escape(str(row[4]))
                created_at = html.escape(str(row[5]))

                text = (
                    f"<b>== ORDER {idx} ==</b>\n"
                    f"ID order: <code>{id_order}</code>\n"
                    f"ID buyer: <code>{id_buyer}</code>\n"
                    f"Product: {name}\n"
                    f"Price: {price}\n"
                    f"Quality: {quality}\n"
                    f"Created_at: {created_at}"
                )
                await context.bot.send_message(text=f"✅ ID:`{caller_id}` SUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
                await update.message.reply_text(text=text, parse_mode="HTML")

        condition = parts[1]
        cursor.execute("SELECT id_order, id_buyer, name, price, quality, created_at FROM orders WHERE id_buyer = ?", (condition,))
        rows = cursor.fetchall()

        if not rows:
            logger.info("No orders in DB")
            await update.message.reply_text("❌ No orders in DB")
            await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
            return
        
        for idx, row in enumerate(rows, 1):
            id_order   = html.escape(str(row[0]))
            id_buyer   = html.escape(str(row[1]))
            name       = html.escape(str(row[2]))
            price      = html.escape(str(row[3]))
            quality    = html.escape(str(row[4]))
            created_at = html.escape(str(row[5]))

            text = (
                f"<b>== ORDER {idx} ==</b>\n"
                f"ID order: <code>{id_order}</code>\n"
                f"ID buyer: <code>{id_buyer}</code>\n"
                f"Product: {name}\n"
                f"Price: {price}\n"
                f"Quality: {quality}\n"
                f"Created_at: {created_at}"
            )
            await update.message.reply_text(text=text, parse_mode="HTML")
            await context.bot.send_message(text=f"✅ ID:`{caller_id}` SUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error in listorders: {e}")
        await update.message.reply_text(f"❌ Error: {e}")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")

    finally:
        cursor.close()
        conn.close()
        return


# /message id_user
async def message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return 
    
    # Check nếu đang trong quá trình nhập kho
    if await check_stock_add_flow(update, context):
        return
    
    caller_id = update.effective_user.id
    text = update.message.text
    await context.bot.send_message(text=f"🟢 ID:`{caller_id}`\nUsed: {text} ", chat_id=settings.ADMIN_ID, parse_mode="Markdown")

    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM subadmins WHERE id_user = ?", (caller_id,))
        if not cursor.fetchone() and caller_id != settings.ADMIN_ID:
            logger.info(f"{caller_id} /message no msAdmin")
            await update.message.reply_text("❌ You aren't msAdmin")
            await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
            return
        
        reply_mode = update.message.reply_to_message
        if reply_mode:
            mode = "reply"
            texts = update.message.text.split(' ')
            if len(texts) != 2:
                logger.info("Non valid data")
                await update.message.reply_text("❌ Invalid syntax")
                await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
                return
            
            try: 
                id_user = int(texts[1])
            except Exception as e:
                logger.info("Error ID")
                await update.message.reply_text("❌ Invalid ID")
                await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
                return

        else:
            mode = "text"
            text = (update.message.text).split('|')
            if len(text) != 3:
                logger.info(f"{caller_id} used invalid syntax")
                await update.message.reply_text(f"❌ Invalid syntax")
                await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
                return
            
            id = text[1]
            msg = text[2]
            try:
                id_user = int(id)
            
            except Exception as e:
                logger.info(f"{caller_id} entered invalid ID")
                await update.message.reply_text(f"❌ Invalid ID user")
                await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
                return
            
        cursor.execute("SELECT * FROM users WHERE id_user=?", (id_user,))
        if not cursor.fetchone():
            logger.info(f"{id_user} not found")
            await update.message.reply_text(f"❌ {id_user} not found")
            await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
            return

        if mode == "reply":
            await context.bot.send_message(text=("🟩 [Message from ADMIN]\n"), chat_id=id_user)
            await context.bot.copy_message(chat_id=id_user, from_chat_id=reply_mode.chat_id, message_id=reply_mode.message_id)
            await update.message.reply_text(f"✅ Sent message to {id_user} Successfully")
            await context.bot.send_message(text=f"✅ ID:`{caller_id}` SUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
            return
        
        elif mode == "text":
            await context.bot.send_message(chat_id=id_user, text =("🟩 [Message from ADMIN]\n") + msg, parse_mode=ParseMode.HTML)
            await update.message.reply_text(f"✅ Sent message to {id_user} Successfully")
            await context.bot.send_message(text=f"✅ ID:`{caller_id}` SUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
            return

        else:
            return 

    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"❌ ERROR: {e}")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        return
    
    finally:
        cursor.close()
        conn.close()

# stock ID +1/-1
async def updatestock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    # Check nếu đang trong quá trình nhập kho
    if await check_stock_add_flow(update, context):
        return
    
    caller_id = update.effective_user.id
    text = update.message.text
    await context.bot.send_message(text=f"🟢 ID:`{caller_id}`\nUsed: {text} ", chat_id=settings.ADMIN_ID, parse_mode="Markdown")

    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM subadmins WHERE id_user = ?", (caller_id,))
        if not cursor.fetchone() and caller_id != settings.ADMIN_ID:
            logger.info(f"{caller_id} /message no msAdmin")
            await update.message.reply_text("❌ You aren't msAdmin")
            await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
            return
        
        text = update.message.text.split(" ")
        if len(text) != 3:
            logger.info("ERROR syntax")
            await update.message.reply_text("❌ Error syntax")
            await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
            return
        

        try:
            # Format ID sản phẩm thành chữ in hoa (hỗ trợ cả chữ và số)
            id_product = str(text[1]).strip().upper()
            amount = (text[2])

        except:
            logger.info(f"Error data ID, quality")
            await update.message.reply_text(f"❌ Error data")
            await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
            return

        cursor.execute("UPDATE listproducts SET quality = quality + ? WHERE id_product = ?", (amount, id_product,))
        logger.info(f"{caller_id} Updated stock ID: {id_product} : {amount}")
        await update.message.reply_text(f"✅ Updated Successfully ID: {id_product} : {amount}")
        await context.bot.send_message(text=f"✅ ID:`{caller_id}` SUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        return 
        
    except Exception as e:
        logger.info(f"{caller_id} /updatestock ERROR {e}")
        await update.message.reply_text(f"❌ Error")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        return 
    
    finally:
        cursor.close()
        conn.commit()
        conn.close()


async def push_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _start_stock_add_flow(update, context, mode=1)


async def pull_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _start_stock_add_flow(update, context, mode=-1)


# Lệnh /pullItems để kéo hàng theo thứ tự cụ thể
async def pull_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kéo hàng về theo thứ tự: /pullItems <product_id> <stt1,stt2,stt3> hoặc /pullItems <product_id> <stt1> <stt2> <stt3>"""
    if not update.message:
        return
    
    caller_id = update.message.from_user.id
    text = update.message.text
    await context.bot.send_message(text=f"🟢 ID:`{caller_id}`\nUsed: {text} ", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
    
    conn = db_connect()
    cursor = conn.cursor()
    try:
        # Kiểm tra quyền admin/subadmin
        cursor.execute("SELECT id_user FROM subadmins WHERE id_user = ?", (caller_id,))
        if not cursor.fetchone() and caller_id != settings.ADMIN_ID:
            await update.message.reply_text("❌ You aren't ADMIN or SubAdmin")
            return
        
        # Parse command: /pullItems <product_id> <stt1,stt2,stt3> hoặc /pullItems <product_id> <stt1> <stt2> <stt3>
        parts = text.split()
        if len(parts) < 3:
            await update.message.reply_text("❌ Syntax: /pullItems <product_id> <stt1,stt2,stt3> hoặc /pullItems <product_id> <stt1> <stt2> <stt3>")
            return
        
        try:
            product_id = str(parts[1]).strip().upper()
        except (ValueError, IndexError):
            await update.message.reply_text("❌ Product ID invalid")
            return
        
        # Kiểm tra sản phẩm có tồn tại không
        cursor.execute("SELECT name, quality FROM listproducts WHERE id_product = ?", (product_id,))
        product_row = cursor.fetchone()
        if not product_row:
            await update.message.reply_text("❌ Product ID not found")
            return
        
        product_name = product_row[0] if product_row[0] else product_id
        current_stock = product_row[1] if product_row[1] is not None else 0
        
        # Parse các số thứ tự
        # Có thể là: "1,2,3" hoặc "1 2 3"
        stt_str = ' '.join(parts[2:])  # Lấy tất cả phần còn lại
        # Xử lý cả dấu phẩy và khoảng trắng
        if ',' in stt_str:
            stt_list = [s.strip() for s in stt_str.split(',')]
        else:
            stt_list = parts[2:]
        
        # Chuyển đổi sang số và loại bỏ trùng lặp, sắp xếp
        try:
            stt_numbers = []
            for stt in stt_list:
                if stt.strip():
                    num = int(stt.strip())
                    if num > 0 and num not in stt_numbers:
                        stt_numbers.append(num)
            stt_numbers.sort()  # Sắp xếp để dễ xử lý
        except ValueError:
            await update.message.reply_text("❌ Số thứ tự không hợp lệ. Phải là số nguyên dương.")
            return
        
        if not stt_numbers:
            await update.message.reply_text("❌ Không có số thứ tự hợp lệ.")
            return
        
        # Lấy tất cả items của sản phẩm theo thứ tự (chỉ lấy items chưa bán - PENDING)
        cursor.execute(
            "SELECT id, item_content FROM stock_items WHERE product_id = ? AND status = 'PENDING' ORDER BY id",
            (product_id,)
        )
        all_items = cursor.fetchall()
        
        if not all_items:
            await update.message.reply_text(f"❌ Sản phẩm {product_name} (ID: {product_id}) không có item nào còn lại trong kho (chỉ có items đã bán).")
            return
        
        # Kiểm tra số thứ tự có hợp lệ không (phải <= số lượng items)
        max_stt = len(all_items)
        invalid_stt = [stt for stt in stt_numbers if stt > max_stt]
        if invalid_stt:
            await update.message.reply_text(
                f"❌ Số thứ tự không hợp lệ: {invalid_stt}. Sản phẩm chỉ có {max_stt} item còn lại.\n"
                f"Vui lòng sử dụng số từ 1 đến {max_stt}."
            )
            return
        
        # Lấy các items cần kéo về (stt bắt đầu từ 1, nên phải -1 cho index)
        items_to_remove = []
        for stt in stt_numbers:
            idx = stt - 1  # Chuyển từ số thứ tự (1-based) sang index (0-based)
            if 0 <= idx < len(all_items):
                items_to_remove.append(all_items[idx])
        
        if not items_to_remove:
            await update.message.reply_text("❌ Không có item nào để kéo về.")
            return
        
        # Xóa các items khỏi stock_items (đã kéo về, không còn trong kho nữa)
        item_ids = [item[0] for item in items_to_remove]
        placeholders = ','.join('?' * len(item_ids))
        cursor.execute(f"DELETE FROM stock_items WHERE id IN ({placeholders})", item_ids)
        
        # Giảm stock trong listproducts
        removed_count = len(items_to_remove)
        new_stock = max(0, current_stock - removed_count)
        cursor.execute("UPDATE listproducts SET quality = ? WHERE id_product = ?", (new_stock, product_id))
        
        conn.commit()
        
        # Tạo thông báo chi tiết
        items_detail = "\n".join([
            f"  {idx+1}. Item #{stt_numbers[idx]}: {item[1][:50]}{'...' if len(item[1]) > 50 else ''}"
            for idx, item in enumerate(items_to_remove)
        ])
        
        success_msg = (
            f"✅ Đã kéo {removed_count} item về cho {product_name} (ID: {product_id})\n"
            f"📊 Stock cũ: {current_stock}\n"
            f"📊 Stock mới: {new_stock}\n"
            f"🔢 Số thứ tự đã kéo: {', '.join(map(str, stt_numbers))}\n\n"
            f"**Chi tiết items đã kéo:**\n{items_detail}"
        )
        
        await update.message.reply_text(success_msg, parse_mode="Markdown")
        logger.info(f"{caller_id} pulled {removed_count} items from {product_id} at positions {stt_numbers}")
        
    except Exception as e:
        logger.exception(f"Error in pull_items: {e}")
        await update.message.reply_text(f"❌ Lỗi khi kéo hàng: {e}")
    finally:
        cursor.close()
        conn.close()


async def _start_stock_add_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: int):
    if not update.message:
        return

    caller_id = update.message.from_user.id
    text = update.message.text
    await context.bot.send_message(text=f"🟢 ID:`{caller_id}`\nUsed: {text} ", chat_id=settings.ADMIN_ID, parse_mode="Markdown")

    if context.user_data.get("active_flow"):
        await update.message.reply_text("⚠️ You have a pending flow. Finish it first. May be you in status buying product, or add product to stock. Please leave it first.")
        await context.bot.send_message(text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        return

    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id_user FROM subadmins WHERE id_user = ?", (caller_id,))
        if not cursor.fetchone() and caller_id != settings.ADMIN_ID:
            await update.message.reply_text("❌ You aren't ADMIN or SubAdmin")
            return

        parts = (update.message.text or "").split()
        if len(parts) != 2:
            await update.message.reply_text("❌ Syntax: /pushItem <product_id> or /pullItem <product_id>")
            return

        try:
            # Format ID sản phẩm thành chữ in hoa (hỗ trợ cả chữ và số)
            product_id = str(parts[1]).strip().upper()
        except (ValueError, IndexError):
            await update.message.reply_text("❌ Product ID invalid")
            return

        cursor.execute("SELECT name, quality FROM listproducts WHERE id_product = ?", (product_id,))
        row = cursor.fetchone()
        if not row:
            await update.message.reply_text("❌ Product ID not found")
            return
        
        # Lấy tên sản phẩm và stock type
        product_name = row[0] if row[0] else product_id
        stock_type = row[1] if row[1] is not None else 0
        
        context.user_data["active_flow"] = "stock_add"
        context.user_data["stock_add_pending"] = True
        context.user_data["stock_add_product_id"] = product_id
        context.user_data["stock_add_mode"] = mode
        context.user_data["stock_add_count"] = 0
        context.user_data["stock_add_items"] = []  # Lưu danh sách items để kiểm tra trùng

        action = "thêm" if mode > 0 else "kéo"
        action_en = "add" if mode > 0 else "pull"
        await update.message.reply_text(
            f"📦 Nhập kho cho {product_name}\n"
            f"🆔 Product ID: {product_id}\n"
            f"📊 Stock type: {stock_type}\n\n"
            f"Gửi nội dung kho (mỗi tin nhắn 1 item, giữ nguyên định dạng).\n"
            f"Nếu gửi tin nhắn dài, dùng \"=====\" để phân cách giữa các item.\n"
            f"Kết thúc bằng /done"
        )
    finally:
        cursor.close()
        conn.close()


# Handler riêng cho lệnh /done trong stock add flow
async def handle_done_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    if not context.user_data.get("stock_add_pending"):
        # Nếu không có flow pending, bỏ qua
        return
    
    product_id = context.user_data.get("stock_add_product_id")
    mode = int(context.user_data.get("stock_add_mode", 1))
    count = int(context.user_data.get("stock_add_count", 0))
    items_list = context.user_data.get("stock_add_items", [])

    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT quality, name FROM listproducts WHERE id_product = ?", (product_id,))
        row = cursor.fetchone()
        if not row:
            await update.message.reply_text("❌ Product ID not found")
            # Clear flow
            for key in ("active_flow", "stock_add_pending", "stock_add_product_id", "stock_add_mode", "stock_add_count", "stock_add_items"):
                context.user_data.pop(key, None)
            return
        current = int(row[0] or 0)
        product_name = row[1] if row[1] else product_id
        
        if count <= 0:
            await update.message.reply_text("⚠️ Không có item nào để cập nhật.")
            # Clear flow
            for key in ("active_flow", "stock_add_pending", "stock_add_product_id", "stock_add_mode", "stock_add_count", "stock_add_items"):
                context.user_data.pop(key, None)
            return
        
        # Nếu là thêm (mode > 0) và có items, lưu vào database và kiểm tra trùng
        added_count = 0
        duplicate_count = 0
        processed_items = set()  # Để kiểm tra trùng trong cùng một lần nhập
        
        if mode > 0 and items_list:
            for item_content in items_list:
                if not item_content or not item_content.strip():
                    continue
                item_content = item_content.strip()
                
                # Kiểm tra trùng trong cùng một lần nhập
                if item_content in processed_items:
                    duplicate_count += 1
                    continue
                processed_items.add(item_content)
                
                # Kiểm tra trùng lặp trong database (chỉ kiểm tra items chưa bán)
                cursor.execute(
                    "SELECT id FROM stock_items WHERE product_id = ? AND item_content = ? AND status = 'PENDING'",
                    (product_id, item_content)
                )
                if cursor.fetchone():
                    duplicate_count += 1
                    continue
                
                # Thêm vào database
                try:
                    cursor.execute(
                        "INSERT INTO stock_items (product_id, item_content) VALUES (?, ?)",
                        (product_id, item_content)
                    )
                    added_count += 1
                except Exception as e:
                    # Nếu trùng (UNIQUE constraint), bỏ qua
                    logger.warning(f"Duplicate item detected: {e}")
                    duplicate_count += 1
                    continue
        
        # Cập nhật số lượng tồn kho
        new_qty = current + (mode * count)
        if new_qty < 0:
            new_qty = 0
        cursor.execute("UPDATE listproducts SET quality = ? WHERE id_product = ?", (new_qty, product_id))
        conn.commit()
        
        action = "thêm" if mode > 0 else "kéo"
        success_msg = (
            f"✅ Đã {action} {count} item cho {product_name} (ID: {product_id})\n"
            f"📊 Stock cũ: {current}\n"
            f"📊 Stock mới: {new_qty}"
        )
        
        if mode > 0 and duplicate_count > 0:
            success_msg += f"\n⚠️ Đã bỏ qua {duplicate_count} item trùng lặp"
        
        await update.message.reply_text(success_msg)
        logger.info(f"Stock updated: {product_id}, added: {added_count}, duplicates: {duplicate_count}")
        
    except Exception as e:
        logger.exception(f"Error in handle_done_stock: {e}")
        await update.message.reply_text(f"❌ Lỗi khi cập nhật kho: {e}")
    finally:
        cursor.close()
        conn.close()

    # Clear flow
    for key in ("active_flow", "stock_add_pending", "stock_add_product_id", "stock_add_mode", "stock_add_count", "stock_add_items"):
        context.user_data.pop(key, None)


async def handle_stock_add_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle stock input messages - supports both single message per item and multi-item with ====="
    """
    if not update.message:
        return

    if not context.user_data.get("stock_add_pending"):
        return

    text = (update.message.text or "").strip()

    # Xử lý input: kiểm tra nếu có "=====" thì chia thành nhiều items
    product_id = context.user_data.get("stock_add_product_id")
    items_list = context.user_data.get("stock_add_items", [])
    
    add_count = 0
    new_items = []
    duplicate_count = 0
    
    if text.isdigit():
        # Nếu là số thì tính là số lượng (không lưu items)
        add_count = int(text)
    else:
        # Kiểm tra xem có "=====" không
        if "=====" in text:
            # Chia theo "=====", mỗi phần là 1 item
            items = [item.strip() for item in text.split("=====") if item.strip()]
            new_items = items
        else:
            # Mặc định: mỗi tin nhắn = 1 item
            new_items = [text]
        
        # Kiểm tra trùng lặp trong danh sách đang nhập và database
        conn = db_connect()
        cursor = conn.cursor()
        try:
            mode = int(context.user_data.get("stock_add_mode", 1))
            for item_content in new_items:
                if not item_content or not item_content.strip():
                    continue
                item_content = item_content.strip()
                
                # Kiểm tra trùng trong danh sách đang nhập
                if item_content in items_list:
                    duplicate_count += 1
                    continue
                
                # Kiểm tra trùng trong database (chỉ khi mode > 0 - thêm, chỉ kiểm tra items chưa bán)
                if mode > 0:
                    cursor.execute(
                        "SELECT id FROM stock_items WHERE product_id = ? AND item_content = ? AND status = 'PENDING'",
                        (product_id, item_content)
                    )
                    if cursor.fetchone():
                        duplicate_count += 1
                        continue
                
                # Thêm vào danh sách
                items_list.append(item_content)
                add_count += 1
        finally:
            cursor.close()
            conn.close()
        
        # Cập nhật danh sách items
        context.user_data["stock_add_items"] = items_list

    if add_count <= 0 and duplicate_count > 0:
        await update.message.reply_text(f"⚠️ Tất cả {duplicate_count} item đã tồn tại (trùng lặp).")
        return
    
    if add_count <= 0:
        await update.message.reply_text("⚠️ Input không hợp lệ. Gửi nội dung item hoặc số lượng.")
        return

    context.user_data["stock_add_count"] = int(context.user_data.get("stock_add_count", 0)) + add_count
    total_pending = context.user_data['stock_add_count']
    
    response_msg = f"✅ Đã thêm {add_count} item. Tổng đang chờ: {total_pending}"
    if duplicate_count > 0:
        response_msg += f"\n⚠️ Đã bỏ qua {duplicate_count} item trùng lặp"
    
    await update.message.reply_text(response_msg)

# myStocks - Xem tất cả sản phẩm trong kho
async def my_stocks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xem tất cả sản phẩm trong kho với số lượng còn lại"""
    if not update.message:
        return
    
    caller_id = update.message.from_user.id
    text = update.message.text
    await context.bot.send_message(text=f"🟢 ID:`{caller_id}`\nUsed: {text} ", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
    
    conn = db_connect()
    cursor = conn.cursor()
    try:
        # Kiểm tra quyền admin/subadmin
        cursor.execute("SELECT id_user FROM subadmins WHERE id_user = ?", (caller_id,))
        if not cursor.fetchone() and caller_id != settings.ADMIN_ID:
            await update.message.reply_text("❌ You aren't ADMIN or SubAdmin")
            return
        
        # Lấy tất cả sản phẩm và đếm số lượng items còn lại (PENDING)
        cursor.execute("""
            SELECT 
                p.id_product,
                p.name,
                p.price,
                p.quality,
                COUNT(CASE WHEN s.status = 'PENDING' THEN 1 END) as pending_count,
                COUNT(CASE WHEN s.status = 'SOLD' THEN 1 END) as sold_count
            FROM listproducts p
            LEFT JOIN stock_items s ON p.id_product = s.product_id
            GROUP BY p.id_product, p.name, p.price, p.quality
            ORDER BY p.id_product
        """)
        products = cursor.fetchall()
        
        if not products:
            await update.message.reply_text("❌ Không có sản phẩm nào trong shop.")
            return
        
        # Format output
        lines = ["📦 **KHO HÀNG TỔNG QUAN**\n"]
        lines.append("```")
        lines.append("ID          | Tên                    | Price      | Stock | Còn lại | Đã bán")
        lines.append("-" * 75)
        
        for product_id, name, price, quality, pending_count, sold_count in products:
            name_display = (name[:20] + "...") if len(name) > 20 else name
            lines.append(
                f"{product_id.ljust(12)}| {name_display.ljust(24)}| "
                f"{str(price).ljust(11)}| {str(quality or 0).ljust(6)}| "
                f"{str(pending_count or 0).ljust(8)}| {str(sold_count or 0)}"
            )
        
        lines.append("```")
        lines.append(f"\n💡 Sử dụng `/myStock <ID>` để xem chi tiết từng sản phẩm")
        
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        await context.bot.send_message(text=f"✅ ID:`{caller_id}` SUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        
    except Exception as e:
        logger.exception(f"Error in my_stocks: {e}")
        await update.message.reply_text(f"❌ Lỗi: {e}")
    finally:
        cursor.close()
        conn.close()


# myStock - Xem chi tiết kho của một sản phẩm
async def my_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xem chi tiết kho của một sản phẩm cụ thể"""
    if not update.message:
        return
    
    caller_id = update.message.from_user.id
    text = update.message.text
    await context.bot.send_message(text=f"🟢 ID:`{caller_id}`\nUsed: {text} ", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
    
    conn = db_connect()
    cursor = conn.cursor()
    try:
        # Kiểm tra quyền admin/subadmin
        cursor.execute("SELECT id_user FROM subadmins WHERE id_user = ?", (caller_id,))
        if not cursor.fetchone() and caller_id != settings.ADMIN_ID:
            await update.message.reply_text("❌ You aren't ADMIN or SubAdmin")
            return
        
        # Parse command: /myStock <product_id>
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text("❌ Syntax: /myStock <product_id>")
            return
        
        try:
            product_id = str(parts[1]).strip().upper()
        except (ValueError, IndexError):
            await update.message.reply_text("❌ Product ID invalid")
            return
        
        # Kiểm tra sản phẩm có tồn tại không
        cursor.execute("SELECT name, price, quality FROM listproducts WHERE id_product = ?", (product_id,))
        product_row = cursor.fetchone()
        if not product_row:
            await update.message.reply_text(f"❌ Không tìm thấy sản phẩm với ID: {product_id}")
            return
        
        product_name, product_price, product_stock = product_row
        
        # Lấy tất cả items của sản phẩm (cả PENDING và SOLD)
        cursor.execute("""
            SELECT id, item_content, status, created_at, sold_at 
            FROM stock_items 
            WHERE product_id = ? 
            ORDER BY 
                CASE WHEN status = 'PENDING' THEN 0 ELSE 1 END,
                id
        """, (product_id,))
        items = cursor.fetchall()
        
        # Đếm số lượng
        pending_items = [item for item in items if item[2] == 'PENDING']
        sold_items = [item for item in items if item[2] == 'SOLD']
        
        # Format output
        lines = [f"📦 **KHO HÀNG: {product_name}**\n"]
        lines.append(f"🆔 ID: `{product_id}`")
        lines.append(f"💰 Giá: {product_price} USDT")
        lines.append(f"📊 Stock (listproducts): {product_stock or 0}")
        lines.append(f"✅ Còn lại (PENDING): {len(pending_items)}")
        lines.append(f"❌ Đã bán (SOLD): {len(sold_items)}")
        lines.append(f"📦 Tổng items: {len(items)}\n")
        
        if pending_items:
            lines.append("**📋 DANH SÁCH ITEMS CÒN LẠI (PENDING):**\n")
            lines.append("```")
            for idx, (item_id, item_content, status, created_at, sold_at) in enumerate(pending_items, 1):
                # Hiển thị 50 ký tự đầu của item_content
                content_preview = item_content[:50] + "..." if len(item_content) > 50 else item_content
                lines.append(f"{idx:3d}. ID: {item_id:5d} | {content_preview}")
            lines.append("```\n")
        
        if sold_items:
            lines.append(f"**📋 DANH SÁCH ITEMS ĐÃ BÁN (SOLD) - {len(sold_items)} items:**\n")
            lines.append("```")
            for idx, (item_id, item_content, status, created_at, sold_at) in enumerate(sold_items[:20], 1):  # Chỉ hiển thị 20 items đầu
                content_preview = item_content[:40] + "..." if len(item_content) > 40 else item_content
                sold_date = sold_at[:16] if sold_at else "N/A"
                lines.append(f"{idx:3d}. ID: {item_id:5d} | {sold_date} | {content_preview}")
            if len(sold_items) > 20:
                lines.append(f"... và {len(sold_items) - 20} items khác")
            lines.append("```")
        
        if not items:
            lines.append("⚠️ Sản phẩm này chưa có item nào trong kho.")
        
        lines.append(f"\n💡 Sử dụng `/pullItems {product_id} <stt1,stt2,stt3>` để kéo hàng về")
        
        message = "\n".join(lines)
        # Telegram có giới hạn 4096 ký tự, nếu quá dài thì chia nhỏ
        if len(message) > 4000:
            # Gửi phần đầu
            await update.message.reply_text("\n".join(lines[:50]), parse_mode="Markdown")
            # Gửi phần còn lại nếu có
            if len(lines) > 50:
                await update.message.reply_text("\n".join(lines[50:]), parse_mode="Markdown")
        else:
            await update.message.reply_text(message, parse_mode="Markdown")
        
        await context.bot.send_message(text=f"✅ ID:`{caller_id}` SUCCESSFULLY", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        
    except Exception as e:
        logger.exception(f"Error in my_stock: {e}")
        await update.message.reply_text(f"❌ Lỗi: {e}")
    finally:
        cursor.close()
        conn.close()

# Handler xác nhận đơn hàng (mode 0)
async def handle_order_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin/Subadmin xác nhận đơn hàng đã xử lý xong"""
    q = update.callback_query
    if not q:
        return
    await q.answer()
    
    caller_id = q.from_user.id
    data = q.data or ""
    if not data.startswith("order_confirm:"):
        return
    
    try:
        order_id = int(data.split(":")[1])
    except (ValueError, IndexError):
        await q.answer("❌ Invalid order ID", show_alert=True)
        return
    
    conn = db_connect()
    cursor = conn.cursor()
    try:
        # Kiểm tra quyền
        cursor.execute("SELECT id_user FROM subadmins WHERE id_user = ?", (caller_id,))
        is_subadmin = cursor.fetchone()
        if caller_id != settings.ADMIN_ID and not is_subadmin:
            await q.answer("❌ You aren't ADMIN or SubAdmin", show_alert=True)
            return
        
        # Lấy thông tin đơn hàng
        cursor.execute(
            "SELECT id_buyer, name, price, quality, user_info, product_id FROM orders WHERE id_order = ? AND status = 'PENDING'",
            (order_id,)
        )
        order_row = cursor.fetchone()
        
        if not order_row:
            await q.answer("❌ Order not found or already processed", show_alert=True)
            return
        
        id_buyer, name, price, qty, user_info, product_id = order_row
        
        # Cập nhật trạng thái đơn hàng
        cursor.execute("UPDATE orders SET status = 'DONE' WHERE id_order = ?", (order_id,))
        conn.commit()
        
        # Thông báo cho người dùng
        lang = get_user_language(id_buyer)
        if lang == 'vi':
            user_msg = (
                f"✅ **Đơn hàng đã được xác nhận**\n"
                f"🆔 Mã đơn: `{order_id}`\n"
                f"🛍️ Sản phẩm: **{name}**\n"
                f"🔢 Số lượng: **{qty}**\n\n"
                f"🎉 Đơn hàng của bạn đã được xử lý thành công!"
            )
        else:
            user_msg = (
                f"✅ **Order Confirmed**\n"
                f"🆔 Order ID: `{order_id}`\n"
                f"🛍️ Product: **{name}**\n"
                f"🔢 Quantity: **{qty}**\n\n"
                f"🎉 Your order has been processed successfully!"
            )
        
        try:
            await context.bot.send_message(chat_id=id_buyer, text=user_msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Failed to notify user {id_buyer} about order confirmation: {e}")
        
        # Cập nhật message cho admin
        if lang == 'vi':
            admin_msg = f"✅ Đơn hàng `{order_id}` đã được xác nhận bởi {'Admin' if caller_id == settings.ADMIN_ID else 'SubAdmin'}"
        else:
            admin_msg = f"✅ Order `{order_id}` confirmed by {'Admin' if caller_id == settings.ADMIN_ID else 'SubAdmin'}"
        
        await q.edit_message_text(admin_msg, parse_mode="Markdown")
        logger.info(f"Order {order_id} confirmed by {caller_id}")
        
    except Exception as e:
        logger.exception(f"Error in handle_order_confirm: {e}")
        await q.answer("❌ Error confirming order", show_alert=True)
    finally:
        cursor.close()
        conn.close()


# Handler hủy đơn hàng (mode 0)
async def handle_order_cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin/Subadmin hủy đơn hàng"""
    q = update.callback_query
    if not q:
        return
    await q.answer()
    
    caller_id = q.from_user.id
    data = q.data or ""
    if not data.startswith("order_cancel:"):
        return
    
    try:
        order_id = int(data.split(":")[1])
    except (ValueError, IndexError):
        await q.answer("❌ Invalid order ID", show_alert=True)
        return
    
    conn = db_connect()
    cursor = conn.cursor()
    try:
        # Kiểm tra quyền
        cursor.execute("SELECT id_user FROM subadmins WHERE id_user = ?", (caller_id,))
        is_subadmin = cursor.fetchone()
        if caller_id != settings.ADMIN_ID and not is_subadmin:
            await q.answer("❌ You aren't ADMIN or SubAdmin", show_alert=True)
            return
        
        # Lấy thông tin đơn hàng
        cursor.execute(
            "SELECT id_buyer, name, price, quality FROM orders WHERE id_order = ? AND status = 'PENDING'",
            (order_id,)
        )
        order_row = cursor.fetchone()
        
        if not order_row:
            await q.answer("❌ Order not found or already processed", show_alert=True)
            return
        
        id_buyer, name, price, qty = order_row
        total_cost = price * qty
        
        # Hoàn tiền cho người dùng
        cursor.execute("UPDATE users SET balance = balance + ? WHERE id_user = ?", (total_cost, id_buyer))
        # Cập nhật trạng thái đơn hàng
        cursor.execute("UPDATE orders SET status = 'CANCELLED' WHERE id_order = ?", (order_id,))
        conn.commit()
        
        # Thông báo cho người dùng
        lang = get_user_language(id_buyer)
        if lang == 'vi':
            user_msg = (
                f"❌ **Đơn hàng đã bị hủy**\n"
                f"🆔 Mã đơn: `{order_id}`\n"
                f"🛍️ Sản phẩm: **{name}**\n"
                f"🔢 Số lượng: **{qty}**\n"
                f"💰 Tổng tiền: **{total_cost}$**\n\n"
                f"💵 Tiền đã được hoàn lại vào ví của bạn."
            )
        else:
            user_msg = (
                f"❌ **Order Cancelled**\n"
                f"🆔 Order ID: `{order_id}`\n"
                f"🛍️ Product: **{name}**\n"
                f"🔢 Quantity: **{qty}**\n"
                f"💰 Total: **{total_cost}$**\n\n"
                f"💵 Money has been refunded to your wallet."
            )
        
        try:
            await context.bot.send_message(chat_id=id_buyer, text=user_msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Failed to notify user {id_buyer} about order cancellation: {e}")
        
        # Cập nhật message cho admin
        if lang == 'vi':
            admin_msg = f"❌ Đơn hàng `{order_id}` đã bị hủy bởi {'Admin' if caller_id == settings.ADMIN_ID else 'SubAdmin'}. Tiền đã được hoàn lại."
        else:
            admin_msg = f"❌ Order `{order_id}` cancelled by {'Admin' if caller_id == settings.ADMIN_ID else 'SubAdmin'}. Money refunded."
        
        await q.edit_message_text(admin_msg, parse_mode="Markdown")
        logger.info(f"Order {order_id} cancelled by {caller_id}, refunded {total_cost} to user {id_buyer}")
        
    except Exception as e:
        logger.exception(f"Error in handle_order_cancel_admin: {e}")
        await q.answer("❌ Error cancelling order", show_alert=True)
    finally:
        cursor.close()
        conn.close()


# Handler mute đơn hàng
async def handle_order_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin/Subadmin mute đơn hàng để bỏ qua thông báo"""
    q = update.callback_query
    if not q:
        return
    await q.answer()
    
    caller_id = q.from_user.id
    data = q.data or ""
    if not data.startswith("order_mute:"):
        return
    
    try:
        order_id = int(data.split(":")[1])
    except (ValueError, IndexError):
        await q.answer("❌ Invalid order ID", show_alert=True)
        return
    
    conn = db_connect()
    cursor = conn.cursor()
    try:
        # Kiểm tra quyền
        cursor.execute("SELECT id_user FROM subadmins WHERE id_user = ?", (caller_id,))
        is_subadmin = cursor.fetchone()
        if caller_id != settings.ADMIN_ID and not is_subadmin:
            await q.answer("❌ You aren't ADMIN or SubAdmin", show_alert=True)
            return
        
        # Cập nhật trạng thái mute
        cursor.execute("UPDATE orders SET is_muted = 1 WHERE id_order = ?", (order_id,))
        conn.commit()
        
        await q.answer("🔇 Order muted", show_alert=True)
        await q.edit_message_text(
            q.message.text + "\n\n🔇 **Đã mute đơn hàng này**" if q.message.text else "🔇 Order muted",
            parse_mode="Markdown"
        )
        logger.info(f"Order {order_id} muted by {caller_id}")
        
    except Exception as e:
        logger.exception(f"Error in handle_order_mute: {e}")
        await q.answer("❌ Error muting order", show_alert=True)
    finally:
        cursor.close()
        conn.close()


# ad_products - Xem nhanh danh sách sản phẩm
async def ad_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    caller_id = update.message.from_user.id
    incoming_text = update.message.text or ""

    # Log admin: escape input để không vỡ MarkdownV2
    await context.bot.send_message(
        chat_id=settings.ADMIN_ID,
        text=f"🟢 ID:`{caller_id}`\nUsed: {escape_markdown(incoming_text, version=2)}",
        parse_mode="MarkdownV2",
    )

    conn = db_connect()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT id_user FROM subadmins WHERE id_user = ?", (caller_id,))
        is_subadmin = cursor.fetchone()

        if caller_id != settings.ADMIN_ID and not is_subadmin:
            await update.message.reply_text("❌ You aren't ADMIN or SubAdmin")
            await context.bot.send_message(
                chat_id=settings.ADMIN_ID,
                text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY",
                parse_mode="MarkdownV2",
            )
            return

        cursor.execute("SELECT id_product, name, price, quality FROM listproducts ORDER BY id_product")
        products = cursor.fetchall()

        if not products:
            await update.message.reply_text("❌ Không có sản phẩm nào trong shop.")
            await context.bot.send_message(
                chat_id=settings.ADMIN_ID,
                text=f"✅ ID:`{caller_id}` SUCCESSFULLY",
                parse_mode="MarkdownV2",
            )
            return

        Products = "📦 <b>DANH SÁCH SẢN PHẨM</b>\n" # dùng *...* cho MarkdownV2
        Products += "ID | Name | Price | Stock | Sold\n"
        Products += "=" * 20
        Products += "\n"

        for product_id, name, price, stock in products:
            cursor.execute("SELECT SUM(quality) FROM orders WHERE name = ? AND status = 'DONE'", (name,))
            sold_row = cursor.fetchone()
            sold = int(sold_row[0] or 0) if sold_row else 0

            product_id_str = str(product_id)
            name_str = str(name)
            price_str = str(price)
            stock_str = str(stock if stock is not None else 0)
            sold_str = str(sold)

            Products += f"<code>{product_id_str}</code> | <code>{name_str}</code> | <code>{price_str}</code> | <code>{stock_str}</code> | <code>{sold_str}</code>\n"


        await update.message.reply_text(Products, parse_mode="HTML")
        await context.bot.send_message(
            chat_id=settings.ADMIN_ID,
            text=f"✅ ID:`{caller_id}` SUCCESSFULLY",
            parse_mode="MarkdownV2",
        )

    except Exception as e:
        logger.exception(f"Error in ad_products: {e}")
        err = escape_markdown(str(e), version=2)
        await update.message.reply_text(f"❌ Error: {err}", parse_mode="MarkdownV2")
        await context.bot.send_message(
            chat_id=settings.ADMIN_ID,
            text=f"❌ ID:`{caller_id}` UNSUCCESSFULLY",
            parse_mode="MarkdownV2",
        )
    finally:
        cursor.close()
        conn.close()



        
