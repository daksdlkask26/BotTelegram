from telegram.error import TimedOut, NetworkError
import asyncio
import threading
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from config import settings
from commands.commands_user import start, help_command, myid, aboutme, listproducts, product_clicked, handle_qty_adjust, handle_qty_noop, handle_qty_mode, handle_buy_confirm, handle_buy_direct, handler_back_list, handle_back_to_listproducts, dashboard, handle_user_info, handle_back_dashboard, handle_listproduct, handle_support, handle_add_balance, handle_sepay_recharge, handle_sepay_amount_input, handle_sepay_confirm, handle_sepay_cancel, handle_sepay_check, handle_orders, handle_actions, handle_analytics, handle_reload_products, add_fund, handle_vn_recharge, handle_crypto_recharge, language_command, handle_language_change, cancel_recharge, skip_product_description, handle_order_info_input, handle_cancel_order_info
from commands.commands_admin import broadcast, block_user, unblock_user, users, help_subadmin, detailuser, addproduct, removeproduct, banlist, listorders, message, updatestock, push_item, pull_item, pull_items, handle_stock_add_input, handle_done_stock, ad_products, my_stocks, my_stock, handle_order_confirm, handle_order_cancel_admin, handle_order_mute, analyst_pr
from commands.commands_boss import refund, add_admin, remove_admin, subAdmins, help_admin, admin_stats
from commands.dbconfig import init_db, logger
from sepay_webhook import app as sepay_app
# from services.logger import setup_logger
# from services.db import init_engine, create_all
# from handlers import commands, callbacks, messages
# from middlewares.rate_limit import guard
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ===============================================================================

# ===============================================================================

def add_handlers(app: Application):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("aboutme", aboutme))
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(CommandHandler("addfund", add_fund))
    app.add_handler(CommandHandler("listproducts", listproducts))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("cancelrecharge", cancel_recharge))
    app.add_handler(CommandHandler("skip", skip_product_description))

    app.add_handler(CommandHandler("add_admin", add_admin))
    app.add_handler(CommandHandler("remove_admin", remove_admin))
    app.add_handler(CommandHandler("subAdmins", subAdmins))
    app.add_handler(CommandHandler("users", users))
    app.add_handler(CommandHandler("refund", refund))
    app.add_handler(CommandHandler("help_admin", help_admin))
    app.add_handler(CommandHandler("admin_stats", admin_stats))
    app.add_handler(CommandHandler("stats", admin_stats))

    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("block_user", block_user))
    app.add_handler(CommandHandler("unblock_user", unblock_user))
    app.add_handler(CommandHandler("bandlist", banlist))
    app.add_handler(CommandHandler("help_subadmin", help_subadmin))
    app.add_handler(CommandHandler("detailuser", detailuser))
    app.add_handler(CommandHandler("addproduct", addproduct))
    app.add_handler(CommandHandler("removeproduct", removeproduct))
    app.add_handler(CommandHandler("pushItem", push_item))
    app.add_handler(CommandHandler("pullItem", pull_item))
    app.add_handler(CommandHandler("pullItems", pull_items))
    app.add_handler(CommandHandler("listorders", listorders))
    app.add_handler(CommandHandler("message", message))
    app.add_handler(CommandHandler("updatestock", updatestock))
    app.add_handler(CommandHandler("ad_products", ad_products))
    app.add_handler(CommandHandler("analystPr", analyst_pr))
    app.add_handler(CommandHandler("done", handle_done_stock))  # Handler cho /done trong stock add flow
    app.add_handler(CommandHandler("myStocks", my_stocks))  # Xem tất cả sản phẩm trong kho
    app.add_handler(CommandHandler("myStock", my_stock))  # Xem chi tiết kho của một sản phẩm

    # app.add_handler(CommandHandler("listproducts", listproducts))

    app.add_handler(CallbackQueryHandler(product_clicked, pattern=r"^prod:"))
    app.add_handler(CallbackQueryHandler(handle_qty_mode, pattern=r"^qtymode:"))  # Phải đăng ký trước qty: để tránh conflict
    app.add_handler(CallbackQueryHandler(handle_qty_adjust, pattern=r"^qty:"))
    app.add_handler(CallbackQueryHandler(handle_qty_noop, pattern=r"^qtynoop$"))
    app.add_handler(CallbackQueryHandler(handle_buy_confirm, pattern=r"^buy:"))
    app.add_handler(CallbackQueryHandler(handle_buy_direct, pattern=r"^buy_direct:"))
    app.add_handler(CallbackQueryHandler(handler_back_list, pattern=r"^back:"))
    app.add_handler(CallbackQueryHandler(handle_back_to_listproducts, pattern=r"^back_listproducts:"))
    app.add_handler(CallbackQueryHandler(handle_user_info, pattern=r"^go_user_info:"))
    app.add_handler(CallbackQueryHandler(handle_back_dashboard, pattern=r"^back_dashboard:"))
    app.add_handler(CallbackQueryHandler(handle_listproduct, pattern=r"^go_listproducts:"))
    app.add_handler(CallbackQueryHandler(handle_support, pattern=r"^go_support:"))
    app.add_handler(CallbackQueryHandler(handle_add_balance, pattern=r"^go_payment_info:"))
    app.add_handler(CallbackQueryHandler(handle_sepay_recharge, pattern=r"^sepay_recharge:"))
    app.add_handler(CallbackQueryHandler(handle_sepay_confirm, pattern=r"^sepay_confirm:"))
    app.add_handler(CallbackQueryHandler(handle_sepay_cancel, pattern=r"^sepay_cancel:"))
    app.add_handler(CallbackQueryHandler(handle_sepay_check, pattern=r"^sepay_check:"))
    app.add_handler(CallbackQueryHandler(handle_order_confirm, pattern=r"^order_confirm:"))
    app.add_handler(CallbackQueryHandler(handle_order_cancel_admin, pattern=r"^order_cancel:"))
    app.add_handler(CallbackQueryHandler(handle_order_mute, pattern=r"^order_mute:"))
    app.add_handler(CallbackQueryHandler(handle_cancel_order_info, pattern=r"^cancel_order_info:"))
    app.add_handler(CallbackQueryHandler(handle_orders, pattern=r"^go_orders:"))
    app.add_handler(CallbackQueryHandler(handle_actions, pattern=r"^go_actions:"))
    app.add_handler(CallbackQueryHandler(handle_analytics, pattern=r"^go_analytics:"))
    app.add_handler(CallbackQueryHandler(handle_vn_recharge, pattern=r"^vn_recharge:"))
    app.add_handler(CallbackQueryHandler(handle_crypto_recharge, pattern=r"^crypto_recharge:"))
    app.add_handler(CallbackQueryHandler(handle_reload_products, pattern=r"^reload_products:"))
    app.add_handler(CallbackQueryHandler(language_command, pattern=r"^go_languages:"))
    app.add_handler(CallbackQueryHandler(handle_language_change, pattern=r"^lang:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_sepay_amount_input))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_stock_add_input))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_order_info_input))
    # app.add_handler(CallbackQueryHandler(listproducts_cb, pattern=r"^back:list$"))   # cho nút quay lại
# (nếu có buy/view thì đăng ký thêm)

# ===============================================================================

async def set_commands(application: Application):
    commands = [
        ("dashboard", "Show dashboard about you"),
        ("start", "Start the bot"),
        ("listproducts", "Show all products"),
        ("addfund", "Charge balance"),
        ("myid", "Show your ID"),
        ("aboutme", "Show your information"),
        ("help", "Show help information"),
        ("language", "Change language / Đổi ngôn ngữ")
]
    await application.bot.set_my_commands(commands)
    logger.info("✅ Bot commands set.")

def start_webhook_server():
    sepay_app.run(host="0.0.0.0", port=settings.PORT, use_reloader=False)

async def notify_pending_orders(app: Application, context):
    app: Application = context.job.data
    """Thông báo mỗi 1h cho admin/subadmin về các đơn hàng PENDING chưa được xử lý"""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from commands.dbconfig import db_connect
    from i18n import get_user_language
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    conn = db_connect()
    cursor = conn.cursor()
    try:
        now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
        one_hour_ago = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        
        # Tìm các đơn hàng PENDING chưa được thông báo trong 1h gần đây và chưa bị mute
        cursor.execute("""
            SELECT id_order, id_buyer, name, price, quality, user_info, product_id, created_at, last_notified_at
            FROM orders 
            WHERE status = 'PENDING' 
            AND is_muted = 0
            AND (last_notified_at IS NULL OR last_notified_at <= ?)
        """, (one_hour_ago,))
        pending_orders = cursor.fetchall()
        
        if not pending_orders:
            return
        
        # Lấy danh sách admin và subadmin
        admin_ids = [settings.ADMIN_ID]
        cursor.execute("SELECT id_user FROM subadmins")
        subadmins = cursor.fetchall()
        admin_ids.extend([row[0] for row in subadmins])
        
        for order_id, id_buyer, name, price, qty, user_info, product_id, created_at, last_notified_at in pending_orders:
            # Lấy thông tin user
            cursor.execute("SELECT user_name FROM users WHERE id_user = ?", (id_buyer,))
            user_row = cursor.fetchone()
            username = user_row[0] if user_row else str(id_buyer)
            
            # Tạo thông báo
            admin_msg = (
                f"⏰ **Nhắc nhở: Đơn hàng chưa xử lý**\n"
                f"🆔 Order ID: `{order_id}`\n"
                f"👤 User: {username} (`{id_buyer}`)\n"
                f"🛍️ Sản phẩm: **{name}**\n"
                f"🆔 Product ID: `{product_id}`\n"
                f"🔢 Số lượng: **{qty}**\n"
                f"💰 Tổng tiền: **{price * qty}$**\n"
                f"📅 Tạo lúc: {created_at}\n\n"
            )
            if user_info:
                admin_msg += f"📝 **Thông tin từ người dùng:**\n{user_info}\n\n"
            admin_msg += "⚠️ Vui lòng xử lý đơn hàng này."
            
            buttons = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Xác nhận", callback_data=f"order_confirm:{order_id}"),
                    InlineKeyboardButton("❌ Hủy đơn", callback_data=f"order_cancel:{order_id}")
                ],
                [InlineKeyboardButton("🔇 Mute", callback_data=f"order_mute:{order_id}")]
            ])
            
            # Gửi cho tất cả admin và subadmin
            for admin_id in admin_ids:
                try:
                    await app.bot.send_message(
                        chat_id=admin_id,
                        text=admin_msg,
                        reply_markup=buttons,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f"Failed to notify admin {admin_id} about order {order_id}: {e}")
            
            # Cập nhật last_notified_at
            now_str = now.strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("UPDATE orders SET last_notified_at = ? WHERE id_order = ?", (now_str, order_id))
        
        if pending_orders:
            conn.commit()
            logger.info(f"Notified admins about {len(pending_orders)} pending orders")
        
    except Exception as e:
        logger.exception(f"Error in notify_pending_orders: {e}")
    finally:
        cursor.close()
        conn.close()


async def cancel_expired_orders(app: Application, context):
    app: Application = context.job.data  # lấy app đã truyền từ data
    """Tự động hủy các đơn hàng đã hết hạn (sau 5 phút)"""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from commands.dbconfig import db_connect
    from i18n import get_user_language, get_text
    
    conn = db_connect()
    cursor = conn.cursor()
    try:
        now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        
        # Tìm các đơn hàng PENDING đã hết hạn
        cursor.execute(
            "SELECT order_code, id_user, product_id, product_name, amount_vnd, amount_usdt FROM recharge_orders WHERE status = 'PENDING' AND expires_at IS NOT NULL AND expires_at <= ?",
            (now_str,)
        )
        expired_orders = cursor.fetchall()
        
        for order_code, id_user, product_id, product_name, amount_vnd, amount_usdt in expired_orders:
            # Cập nhật trạng thái thành CANCELLED
            cursor.execute(
                "UPDATE recharge_orders SET status = 'CANCELLED' WHERE order_code = ?",
                (order_code,)
            )
            
            # Gửi thông báo cho người dùng
            lang = get_user_language(id_user)
            if lang == 'vi':
                message = (
                    f"⏰ **Đơn hàng đã hết hạn**\n"
                    f"🆔 Mã đơn: `{order_code}`\n"
                    f"💰 Số tiền: {amount_vnd:,} VND ({amount_usdt:.4f} USDT)\n"
                )
                if product_name:
                    message += f"🛍️ Sản phẩm: {product_name}\n"
                message += f"\n❌ Đơn hàng đã tự động hủy do quá thời gian thanh toán (5 phút)."
            else:
                message = (
                    f"⏰ **Order Expired**\n"
                    f"🆔 Order code: `{order_code}`\n"
                    f"💰 Amount: {amount_vnd:,} VND ({amount_usdt:.4f} USDT)\n"
                )
                if product_name:
                    message += f"🛍️ Product: {product_name}\n"
                message += f"\n❌ Order automatically cancelled due to payment timeout (5 minutes)."
            
            try:
                await app.bot.send_message(
                    chat_id=id_user,
                    text=message,
                    parse_mode="Markdown"
                )
                logger.info(f"Expired order {order_code} cancelled and notified user {id_user}")
            except Exception as e:
                logger.warning(f"Failed to notify user {id_user} about expired order {order_code}: {e}")
        
        if expired_orders:
            conn.commit()
            logger.info(f"Cancelled {len(expired_orders)} expired orders")
        
    except Exception as e:
        logger.exception(f"Error in cancel_expired_orders: {e}")
    finally:
        cursor.close()
        conn.close()


# def main():
#     init_db()
#     token = settings.BOT_TOKEN
#     if not token:
#         raise RuntimeError("Thiếu BOT_TOKEN. Kiểm tra file .env hoặc biến môi trường.")
#     app = (
#         Application
#         .builder()
#         .token(token)
#         .post_init(set_commands)  # <-- hàm này tự động được gọi và await
#         .build()
#     )

#     add_handlers(app)

#     # Tạo scheduler để tự động hủy đơn hàng hết hạn mỗi phút
#     scheduler = AsyncIOScheduler()
#     scheduler.add_job(
#         cancel_expired_orders,
#         'interval',
#         minutes=1,
#         args=[app],
#         id='cancel_expired_orders',
#         replace_existing=True
#     )
#     # Tạo scheduler để thông báo đơn hàng PENDING mỗi 1 giờ
#     scheduler.add_job(
#         notify_pending_orders,
#         'interval',
#         hours=1,
#         args=[app],
#         id='notify_pending_orders',
#         replace_existing=True
#     )
#     scheduler.start()
#     logger.info("✅ Scheduler started for auto-cancelling expired orders and notifying pending orders")

#     webhook_thread = threading.Thread(target=start_webhook_server, daemon=True)
#     webhook_thread.start()
#     logger.info("✅ SePay webhook started on port %s.", settings.PORT)

#     print("Bot started...")
#     try:
#         app.run_polling()
#     except KeyboardInterrupt:
#         print("Bot stopped by user (Ctrl+C).")
#     finally:
#         # Shutdown scheduler một cách an toàn
#         try:
#             if scheduler.running:
#                 scheduler.shutdown(wait=False)
#                 logger.info("✅ Scheduler stopped.")
#         except (RuntimeError, Exception) as e:
#             # Bỏ qua lỗi nếu event loop đã đóng
#             logger.debug(f"Scheduler shutdown error (expected on Ctrl+C): {e}")

def main():
    init_db()
    token = settings.BOT_TOKEN
    if not token:
        raise RuntimeError("Thiếu BOT_TOKEN. Kiểm tra file .env hoặc biến môi trường.")

    app = (
        Application.builder()
        .token(token)
        .post_init(set_commands)
        .build()
    )

    add_handlers(app)

    # ✅ Lên lịch bằng JobQueue (chạy ổn trên Windows + Linux)
    app.job_queue.run_repeating(
        cancel_expired_orders,
        interval=60,      # 60s = 1 phút
        first=10,         # chạy sau 10 giây kể từ khi bot start
        data=app,         # truyền app qua context.job.data
        name="cancel_expired_orders",
    )

    app.job_queue.run_repeating(
        notify_pending_orders,
        interval=3600,    # 1 giờ
        first=60,         # chạy sau 60 giây
        data=app,
        name="notify_pending_orders",
    )

    logger.info("✅ JobQueue scheduled for cancel_expired_orders & notify_pending_orders")

    # ✅ webhook Flask chạy thread riêng vẫn OK
    webhook_thread = threading.Thread(target=start_webhook_server, daemon=True)
    webhook_thread.start()
    logger.info("✅ SePay webhook started on port %s.", settings.PORT)

    print("Bot started...")
    application.run_polling()


if __name__ == "__main__":
    main()
