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
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from i18n import get_user_language

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO,
                    filename = "action.log",
                    filemode='a' # ghi noi tiep khong ghi de
                    )
logger = logging.getLogger(__name__)


# Hàm thêm SubAdmin
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Kiểm tra xem có tin nhắn không
    if not update.message:
        return

    # lấy ID người dùng gửi tin nhắn
    user_id = update.message.from_user.id

    # Kiểm tra xem người dùng có phải là ADMIN chính không
    if user_id != settings.ADMIN_ID:
        logger.info(f"Attempt to add SubAdmin without ID")
        await update.message.reply_text("❌[Error] **You aren't ADMIN**", parse_mode="Markdown")
        return
    
    # Lấy tin nhắn người dùng
    user_message = update.message.text
    parts = user_message.split()  # Tách tin nhắn thành các phần
    if len(parts) < 2:
        logger.info(f"Attempt to add SubAdmin without ID")
        await update.message.reply_text("❌[Error] **Usage: /addadmin <user_id>**", parse_mode="Markdown")
        return
    raw_id = parts[1] # Lấy ID người dùng từ tin nhắn

    try:
        new_user_id = int(raw_id) # Chuyển đổi ID người dùng thành số nguyên, nếu lỗi thì báo lỗi
    except:
        text_reply = """❌[Error] **Invalid ID, {Type ID}**"""
        logger.info(f"Attempt to add SubAdmin with invalid ID: ID={raw_id}")
        await update.message.reply_text(text_reply, parse_mode="Markdown")
        return
    
    # Kiểm tra xem ID người dùng có hợp lệ không, không được trùng với ADMIN chính
    if (new_user_id == settings.ADMIN_ID):
        text_reply = """❌[Error] **Invalid ID, {Admin ID}**"""
        logger.info(f"Attempt to add MAIN ADMIN as SubAdmin: ID={new_user_id}")
        await update.message.reply_text(text_reply, parse_mode="Markdown")
        return
    
    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute("SELECT id_user FROM users WHERE id_user = ?", (new_user_id,))
    row = cursor.fetchone()
    if not row:
        logger.info(f"ID: {new_user_id} is not exist")
        await update.message.reply_text(f"❌ ID: {new_user_id} isn't in DB")
        return

    cursor.execute("SELECT * FROM users WHERE id_user = ? AND is_blocked = 1", (new_user_id,))
    row = cursor.fetchone()

    if row:
        logger.info(f"{new_user_id} is blocked")
        await update.message.reply_text(f"❌ {new_user_id} is blocked")
        return
    
    cursor.execute("SELECT id_user FROM subadmins WHERE id_user = ?", (new_user_id,))
    row = cursor.fetchone() # Lấy một dòng kết quả
    cursor.close()

    # Kiểm tra xem ID người dùng đã tồn tại trong danh sách SubAdmin chưa
    if row:
        logger.info(f"Attempt to add existing SubAdmin: ID={new_user_id}")
        await update.message.reply_text("❌[Error] **SubAdmin is exist**", parse_mode="Markdown")
        return
    

    # Thêm ID người dùng vào danh sách SubAdmin
    cursor = conn.cursor()
    cursor.execute("INSERT INTO subadmins (id_user) VALUES (?)", (new_user_id,))
    cursor.execute("UPDATE users SET is_subadmin = 1 WHERE id_user = ?", (new_user_id,))
    cursor.close()
    conn.commit()
    conn.close()
    logger.info(f"Added new SubAdmin: ID={new_user_id} by ADMIN ID={user_id}")
    await update.message.reply_text("✅ [SUCCESSFULLY] **Added admin**", parse_mode="Markdown")
    await context.bot.send_message(chat_id=new_user_id, text=f"✅ [SUCCESSFULLY] **Added admin**", parse_mode="Markdown")
    return

# Hàm xóa SubAdmin
async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Kiểm tra xem có tin nhắn không
    if not update.message:
        return
    
    # Lấy ID người dùng gửi tin nhắn
    caller_id = update.message.from_user.id

    # Kiểm tra xem người dùng có phải là ADMIN chính không
    if caller_id != settings.ADMIN_ID:
        logger.info(f"Attempt to remove SubAdmin without ID")
        await update.message.reply_text("❌[Error] **You aren't ADMIN**", parse_mode="Markdown")
        return
    
    # Lấy tin nhắn người dùng
    user_message = update.message.text
    parts = user_message.split(" ")
    if len(parts) < 2:
        logger.info(f"Attempt to remove SubAdmin without ID")
        await update.message.reply_text("❌[Error] **Usage: /addadmin <user_id>**", parse_mode="Markdown")
        return
    raw_id = parts[1]

    try:
        old_user_id = int(raw_id)
    except:
        logger.info(f"Attempt to remove SubAdmin with invalid ID: ID={raw_id}")
        await update.message.reply_text("❌[Error] **Invalid ID, {Type ID}**", parse_mode="Markdown")
        return
    
    # Kiểm tra xem ID người dùng có hợp lệ không, không được trùng với ADMIN chính
    if old_user_id == settings.ADMIN_ID:
        logger.info(f"Attempt to remove MAIN ADMIN as SubAdmin: ID={old_user_id}")
        await update.message.reply_text("❌[Error] **Can't remove MAIN ADMIN**", parse_mode="Markdown")
        return
    
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT id_user FROM subadmins WHERE id_user = ?", (old_user_id,))
    row = cursor.fetchone() # Lấy một dòng kết quả
    cursor.close()

    # Kiểm tra xem ID người dùng có tồn tại trong danh sách SubAdmin không
    if not row:
        logger.info(f"Attempt to remove non-existing SubAdmin: ID={old_user_id}")
        await update.message.reply_text("❌[Error] **SubAdmin isn't EXIST.**", parse_mode="Markdown")
        return
    
    # Xóa ID người dùng khỏi danh sách SubAdmin
    cursor = conn.cursor()
    cursor.execute("DELETE FROM subadmins WHERE id_user = ?", (old_user_id,))
    cursor.execute("UPDATE users SET is_subadmin = 0 WHERE id_user = ?", (old_user_id, ))
    cursor.close()
    conn.commit()
    conn.close()
    logger.info(f"Removed SubAdmin: ID={old_user_id} by ADMIN ID={caller_id}")
    await update.message.reply_text("✅** [SUCCESSFULLY] Removed SubAdmin.**", parse_mode="Markdown")
    await context.bot.send_message(chat_id=old_user_id, text=f"✅ [SUCCESSFULLY] **Removed admin**", parse_mode="Markdown")
    return

# Hàm liệt kê SubAdmin
async def subAdmins(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # Kiểm tra xem có tin nhắn không
    if not update.message:
        return
    
    caller_id = update.message.from_user.id # Lay ID nguoi gui tin nhan
    if (caller_id != settings.ADMIN_ID):
        await update.message.reply_text("❌[Error] You aren't ADMIN")
        return

    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT id_user FROM subadmins")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    # Kiểm tra xem có SubAdmin không
    if not rows:
        logger.info(f"Listed SubAdmins: No SubAdmin in shop, Requested by ADMIN ID={caller_id}")
        await update.message.reply_text("❌ **No SubAdmin in shop.**", parse_mode="Markdown")
        return

    text_reply = "📋 **List of SubAdmins:**\n"
    i = 1
    for row in rows:
        admin_id = row[0]
        text_reply += f"**ID**{i}: `{admin_id}`\n"
        i = i+1
    
    logger.info(f"Listed SubAdmins: Requested by ADMIN ID={caller_id}")
    await update.message.reply_text(text_reply, parse_mode="Markdown")
    return

# The function refund money for client
async def refund(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    text = update.message.text
    caller_id = update.message.from_user.id

    if caller_id != settings.ADMIN_ID:
        logger.info(f"{caller_id} requested refund money, UN successfully")
        await update.message.reply_text("❌ You aren't ADMIN")
        return
    
    parts = text.split(" ")
    if len(parts) != 3:
        logger.info(f"{caller_id} entered non valid data")
        await update.message.reply_text("❌ Non valid data")
        return
    
    try:
        amount = float(parts[1])
        id_user = int(parts[2])
    except:
        logger.info(f"{caller_id} sent message nonvalid")
        await update.message.reply_text("❌ Non valid type data (REAL, INT)")
        return
    
    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id_user = ?", (id_user,))
    if not cursor.fetchone():
        logger.info(f"{id_user} doesn't exist")
        await update.message.reply_text(f"❌ ID: {id_user} doesn't found")
        cursor.close()
        conn.close()
        return
    
    cursor.execute("UPDATE users SET balance = balance + (?) WHERE id_user = (?)", (amount, id_user, ))
    cursor.execute(
        "INSERT INTO recharge_history (id_user, amount, method, status) VALUES (?, ?, ?, ?)",
        (id_user, amount, "admin_refund", "SUCCESS")
    )
    conn.commit()
    cursor.close()
    conn.close()

    logger.info(f"UPDATED {amount}$ balance for {id_user}")
    await context.bot.send_message(chat_id=id_user, text=f"✅ Refund {amount}$ to your balance Successfully")
    await update.message.reply_text(f"✅ Updated {amount}$ for {id_user} Successfully")
    return

# Help admin
async def help_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # kiem tra co nhan tin nhan hay khong
    if not update.message:
        return
    
    caller_id = update.message.from_user.id
    if (settings.ADMIN_ID != caller_id):
        logger.info(f"{caller_id} user help_admin but NO")
        await update.message.reply_text(f"❌ You aren't MAIN ADMIN")
        return
    
    lang = get_user_language(caller_id)
    if lang == "vi":
        text = (
            "👑 <b>HƯỚNG DẪN MAIN ADMIN</b>\n\n"
            "👥 <b>Quản lý SubAdmin</b>\n"
            "• <code>/add_admin user_id</code> — Thêm SubAdmin (user phải tồn tại & không bị chặn)\n"
            "  VD: <code>/add_admin 123456789</code>\n"
            "• <code>/remove_admin user_id</code> — Gỡ SubAdmin (không gỡ Main Admin)\n"
            "• <code>/subAdmins</code> — Danh sách SubAdmin\n\n"
            "💰 <b>Tài chính</b>\n"
            "• <code>/refund amount user_id</code> — Hoàn tiền vào balance + ghi lịch sử\n"
            "  VD: <code>/refund 100.5 123456789</code>\n\n"
            "📊 <b>Thống kê</b>\n"
            "• <code>/admin_stats</code> hoặc <code>/stats</code> — Dashboard thống kê shop\n\n"
            "🛠️ <b>Ghi chú vận hành</b>\n"
            "• Các lệnh SubAdmin vẫn dùng được cho Main Admin (quản lý sản phẩm/kho/đơn/khách)\n"
            "• Đơn mode=0: xử lý bằng nút <b>✅ Xác nhận / ❌ Hủy / 🔇 Mute</b> trong tin nhắn order\n\n"
            "ℹ️ <b>Khác</b>\n"
            "• <code>/help_admin</code> — Xem hướng dẫn này\n"
        )
    else:
        text = (
            "👑 <b>MAIN ADMIN HELP</b>\n\n"
            "👥 <b>SubAdmin management</b>\n"
            "• <code>/add_admin user_id</code> — Add SubAdmin (user must exist & not blocked)\n"
            "  Ex: <code>/add_admin 123456789</code>\n"
            "• <code>/remove_admin user_id</code> — Remove SubAdmin (can’t remove Main Admin)\n"
            "• <code>/subAdmins</code> — List SubAdmins\n\n"
            "💰 <b>Finance</b>\n"
            "• <code>/refund amount user_id</code> — Refund to balance + log history\n"
            "  Ex: <code>/refund 100.5 123456789</code>\n\n"
            "📊 <b>Stats</b>\n"
            "• <code>/admin_stats</code> or <code>/stats</code> — Shop statistics dashboard\n\n"
            "🛠️ <b>Ops notes</b>\n"
            "• Main Admin can also use all SubAdmin commands\n"
            "• Mode=0 orders: use buttons <b>✅ Confirm / ❌ Cancel / 🔇 Mute</b> in order message\n\n"
            "ℹ️ <b>Other</b>\n"
            "• <code>/help_admin</code> — Show this help\n"
        )
    logger.info(f"Sent help admin to ADMIN")
    await update.message.reply_text(text=text, parse_mode=ParseMode.HTML)
    return

# Admin Statistics Dashboard
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display comprehensive admin statistics dashboard"""
    if not update.message:
        return
    
    caller_id = update.message.from_user.id
    if caller_id != settings.ADMIN_ID:
        logger.info(f"{caller_id} attempted to access admin stats")
        await update.message.reply_text("❌ You aren't MAIN ADMIN")
        return
    
    conn = db_connect()
    cursor = conn.cursor()
    
    try:
        # Tính toán thời gian
        now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        month_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        
        lines = []
        
        # 👥 NGƯỜI DÙNG
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 1")
        blocked_users = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM subadmins")
        subadmins_count = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (today_start,))
        new_users_today = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (week_ago,))
        new_users_week = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (month_ago,))
        new_users_month = cursor.fetchone()[0] or 0
        
        lines.append("👥 <b>NGƯỜI DÙNG</b>")
        lines.append(f"• Tổng người dùng      : {total_users:,}")
        lines.append(f"• Người bị chặn        : {blocked_users:,}")
        lines.append(f"• Admin con            : {subadmins_count:,}")
        lines.append(f"• Mới hôm nay          : {new_users_today:,}")
        lines.append(f"• Mới 7 ngày            : {new_users_week:,}")
        lines.append(f"• Mới 30 ngày           : {new_users_month:,}")
        lines.append("")
        
        # 📦 ĐƠN HÀNG
        cursor.execute("SELECT COUNT(*) FROM orders")
        total_orders = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'Pending'")
        pending_orders = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'DONE'")
        done_orders = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'CANCELED'")
        canceled_orders = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM orders WHERE created_at >= ?", (today_start,))
        orders_today = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM orders WHERE created_at >= ?", (week_ago,))
        orders_week = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM orders WHERE created_at >= ?", (month_ago,))
        orders_month = cursor.fetchone()[0] or 0
        
        lines.append("📦 <b>ĐƠN HÀNG</b>")
        lines.append(f"• Tổng đơn đã bán      : {total_orders:,}")
        lines.append(f"• Đơn chờ thanh toán   : {pending_orders:,}")
        lines.append(f"• Đơn đã thanh toán    : {done_orders:,}")
        lines.append(f"• Đơn hoàn tiền        : {canceled_orders:,}")
        lines.append(f"• Đơn hôm nay          : {orders_today:,}")
        lines.append(f"• Đơn 7 ngày gần nhất  : {orders_week:,}")
        lines.append(f"• Đơn 30 ngày gần nhất : {orders_month:,}")
        lines.append("")
        
        # 💰 DOANH THU
        # Tổng nạp (từ recharge_history với status SUCCESS)
        cursor.execute("SELECT SUM(amount) FROM recharge_history WHERE status = 'SUCCESS'")
        total_recharge = cursor.fetchone()[0] or 0
        
        # Thanh toán trực tiếp (từ orders với status DONE)
        cursor.execute("SELECT SUM(price * quality) FROM orders WHERE status = 'DONE'")
        total_direct_payment = cursor.fetchone()[0] or 0
        
        # Doanh thu NET (tổng orders DONE)
        revenue_net = total_direct_payment
        
        # Doanh thu theo thời gian
        cursor.execute("SELECT SUM(price * quality) FROM orders WHERE status = 'DONE' AND created_at >= ?", (today_start,))
        revenue_today = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT SUM(price * quality) FROM orders WHERE status = 'DONE' AND created_at >= ?", (week_ago,))
        revenue_week = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT SUM(price * quality) FROM orders WHERE status = 'DONE' AND created_at >= ?", (month_ago,))
        revenue_month = cursor.fetchone()[0] or 0
        
        # Tổng số dư hiện tại
        cursor.execute("SELECT SUM(balance) FROM users")
        total_balance = cursor.fetchone()[0] or 0
        
        lines.append("💰 <b>DOANH THU</b>")
        lines.append(f"• Tổng nạp             : {total_recharge:,.0f} USDT")
        lines.append(f"• Thanh toán trực tiếp : {total_direct_payment:,.0f} USDT")
        lines.append(f"• Doanh thu NET        : {revenue_net:,.0f} USDT")
        lines.append(f"• Tổng số dư hiện tại  : {total_balance:,.0f} USDT")
        lines.append("")
        
        lines.append("📈 <b>DOANH THU THEO THỜI GIAN</b>")
        lines.append(f"• Hôm nay              : {revenue_today:,.0f} USDT")
        lines.append(f"• 7 ngày gần nhất      : {revenue_week:,.0f} USDT")
        lines.append(f"• 30 ngày gần nhất     : {revenue_month:,.0f} USDT")
        lines.append("")
        
        # 🏆 TOP SẢN PHẨM
        cursor.execute("""
            SELECT name, SUM(quality) as total_qty, COUNT(*) as order_count
            FROM orders 
            WHERE status = 'DONE'
            GROUP BY name 
            ORDER BY total_qty DESC 
            LIMIT 5
        """)
        top_products = cursor.fetchall()
        
        lines.append("🏆 <b>TOP SẢN PHẨM</b>")
        if top_products:
            for idx, (name, total_qty, order_count) in enumerate(top_products, 1):
                qty = int(total_qty or 0)
                count = int(order_count or 0)
                # Cắt tên sản phẩm nếu quá dài
                product_name = name[:28] if len(name) > 28 else name
                lines.append(f"{idx}. {product_name:<28} : {qty:,} đơn")
        else:
            lines.append("Chưa có dữ liệu")
        lines.append("")
        
        # 👑 TOP KHÁCH HÀNG
        cursor.execute("""
            SELECT id_buyer, SUM(price * quality) as total_spent
            FROM orders 
            WHERE status = 'DONE'
            GROUP BY id_buyer 
            ORDER BY total_spent DESC 
            LIMIT 5
        """)
        top_customers = cursor.fetchall()
        
        lines.append("👑 <b>TOP KHÁCH HÀNG</b>")
        if top_customers:
            for idx, (user_id, total_spent) in enumerate(top_customers, 1):
                spent = float(total_spent or 0)
                # Lấy username nếu có
                cursor.execute("SELECT user_name FROM users WHERE id_user = ?", (user_id,))
                user_row = cursor.fetchone()
                username = user_row[0] if user_row and user_row[0] else f"user_{user_id}"
                # Cắt username nếu quá dài
                display_name = username[:23] if len(username) > 23 else username
                lines.append(f"{idx}. {display_name:<23} : {spent:,.0f} USDT")
        else:
            lines.append("Chưa có dữ liệu")
        
        # 📊 CHỈ SỐ BỔ SUNG
        # Giá trị đơn hàng trung bình (AOV)
        if done_orders > 0:
            avg_order_value = revenue_net / done_orders
            lines.append("")
            lines.append("📊 <b>CHỈ SỐ BỔ SUNG</b>")
            lines.append(f"• Giá trị đơn TB (AOV) : {avg_order_value:,.0f} USDT")
        
        # Tổng số sản phẩm đã bán
        cursor.execute("SELECT SUM(quality) FROM orders WHERE status = 'DONE'")
        total_items_sold = cursor.fetchone()[0] or 0
        if total_items_sold > 0:
            lines.append(f"• Tổng sản phẩm đã bán : {int(total_items_sold):,}")
        
        # Số sản phẩm đang bán
        cursor.execute("SELECT COUNT(*) FROM listproducts")
        active_products = cursor.fetchone()[0] or 0
        if active_products > 0:
            lines.append(f"• Sản phẩm đang bán    : {active_products:,}")
        
        text = "\n".join(lines)
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        logger.info(f"Admin stats displayed for ADMIN ID={caller_id}")
        
    except Exception as e:
        logger.exception(f"Error in admin_stats: {e}")
        await update.message.reply_text(f"❌ Error generating statistics: {e}")
    finally:
        cursor.close()
        conn.close()
