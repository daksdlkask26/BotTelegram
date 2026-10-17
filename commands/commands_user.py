from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from config import settings
from telegram.ext import ContextTypes
from sqlite3 import connect
import os
import logging
from telegram.error import RetryAfter, Forbidden, BadRequest
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram.constants import ParseMode
import random, html
from telegram.helpers import escape_markdown
import time
import urllib.parse
from commands.dbconfig import db_connect
from commands.commands_admin import handle_stock_add_input
from i18n import get_text, set_user_language, get_user_language, DEFAULT_LANGUAGE
from look_up import find_pay_transaction_by_id, check_deposit_by_txid
from io import BytesIO
import httpx



logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO,
                    filename = "action.log",
                    filemode='a' # ghi noi tiep khong ghi de
                    )
logger = logging.getLogger(__name__)

EXCHANGE_RATE_VND = 25000
CRYPTO_LOOKBACK_HOURS = 24


def get_active_flow(context: ContextTypes.DEFAULT_TYPE):
    return context.user_data.get("active_flow")


def clear_active_flow(context: ContextTypes.DEFAULT_TYPE):
    for key in (
        "active_flow",
        "awaiting_sepay_amount",
        "awaiting_crypto_txid",
        "awaiting_product_description",
        "product_description_id",
        "stock_add_pending",
        "stock_add_product_id",
        "stock_add_count",
    ):
        context.user_data.pop(key, None)


async def notify_flow_busy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    active_flow = get_active_flow(context)
    
    # Xác định loại flow và thông báo tương ứng
    flow_key = f"flow.{active_flow}" if active_flow else "flow.unknown"
    
    # Kiểm tra xem translation key có tồn tại không
    try:
        msg = get_text(user_id, flow_key)
        # Nếu không tìm thấy, fallback về flow.unknown
        if msg == f"[{flow_key}]":
            msg = get_text(user_id, "flow.unknown")
    except:
        msg = get_text(user_id, "flow.unknown")
    
    if update.callback_query:
        await update.callback_query.answer()
        await context.bot.send_message(chat_id=user_id, text=msg)
    elif update.message:
        await update.message.reply_text(msg)


def build_product_text(user_id: int, name: str, product_id: str, price: float, stock: int, qty: int, descrip: str):
    total = price * qty
    # Format mô tả đẹp hơn
    descrip_text = descrip if descrip and descrip.strip() and descrip != "@daksdlkasd" else None
    
    # Format giá và tổng tiền với 2 chữ số thập phân
    price_str = f"{price:.2f}"
    total_str = f"{total:.2f}"
    
    # Separator
    separator = "━━━━━━━━━━━━━━"
    
    # Lấy ngôn ngữ để hiển thị labels phù hợp
    from i18n import get_user_language
    lang = get_user_language(user_id)
    
    if lang == 'vi':
        # Format tiếng Việt
        text = (
            f"🛍️ **{name}**\n"
            f"{separator}\n"
            f"🆔 ID        : `{product_id}`\n"
            f"💰 Giá       : **{price_str} $**\n"
            f"📦 Tồn kho   : **{stock}**\n"
        )
        
        # Thêm mô tả nếu có
        if descrip_text:
            text += f"\n📄 **Mô tả**\n> {descrip_text}\n"
        
        text += (
            f"{separator}\n"
            f"🔢 Số lượng  : **{qty}**\n"
            f"🧾 Tổng tiền : **{total_str} $**"
        )
    else:
        # Format tiếng Anh
        text = (
            f"🛍️ **{name}**\n"
            f"{separator}\n"
            f"🆔 ID        : `{product_id}`\n"
            f"💰 Price     : **{price_str} $**\n"
            f"📦 Stock     : **{stock}**\n"
        )
        
        # Thêm mô tả nếu có
        if descrip_text:
            text += f"\n📄 **Description**\n> {descrip_text}\n"
        
        text += (
            f"{separator}\n"
            f"🔢 Quantity  : **{qty}**\n"
            f"🧾 Total     : **{total_str} $**"
        )
    
    return text


def build_product_keyboard(user_id: int, product_id: str, qty: int, step: int = 1, back_to_list: bool = True):
    """Build product keyboard with quantity selector and step mode buttons
    
    Args:
        user_id: User ID
        product_id: Product ID
        qty: Current quantity
        step: Current step mode
        back_to_list: If True, back button goes to list products; if False, goes to dashboard
    """
    # Các mode step có sẵn
    step_modes = [1, 2, 5, 10, 20, 50, 100]
    
    # Tạo nút cho các mode step (highlight mode hiện tại)
    step_buttons = []
    for mode in step_modes:
        if mode == step:
            # Mode đang chọn: hiển thị với dấu ✓
            step_buttons.append(InlineKeyboardButton(f"✓{mode}", callback_data=f"qtymode:{product_id}:{qty}:{mode}"))
        else:
            step_buttons.append(InlineKeyboardButton(str(mode), callback_data=f"qtymode:{product_id}:{qty}:{mode}"))
    
    # Chia thành 2 hàng cho đẹp (4 nút hàng 1, 3 nút hàng 2)
    step_row1 = step_buttons[:4]  # 1, 2, 5, 10
    step_row2 = step_buttons[4:]   # 20, 50, 100
    
    # Nút Back: quay về list products nếu back_to_list=True, ngược lại về dashboard
    back_callback = "back_listproducts:NONE" if back_to_list else "back_dashboard:NONE"
    
    # Lấy ngôn ngữ để hiển thị labels
    from i18n import get_user_language
    lang = get_user_language(user_id)
    
    if lang == 'vi':
        buy_wallet_text = "💳 Mua bằng ví"
        
    else:
        buy_wallet_text = "💳 Buy with wallet"
    
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➖", callback_data=f"qty:{product_id}:{qty-step}:{step}"),
            InlineKeyboardButton(f"{qty}", callback_data="qtynoop"),
            InlineKeyboardButton("➕", callback_data=f"qty:{product_id}:{qty+step}:{step}")
        ],
        step_row1,  # Mode buttons row 1: 1, 2, 5, 10
        step_row2,  # Mode buttons row 2: 20, 50, 100
        [InlineKeyboardButton(text=buy_wallet_text, callback_data=f"buy:{product_id}:{qty}")],
        [InlineKeyboardButton(get_text(user_id, 'common.back'), callback_data=back_callback)]
    ])


# process /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    # Clear any pending flow when user starts fresh
    clear_active_flow(context)

    user_id = update.message.from_user.id if update.message else None
    user_name = update.message.from_user.name
    text = update.message.text

    conn = db_connect()
    cursor = conn.cursor()

    try:
        # Kiểm tra xem người dùng đã tồn tại trong bảng users chưa
        cursor.execute("SELECT id_user FROM users WHERE id_user = ?", (user_id,))
        row = cursor.fetchone() # Lấy một dòng kết quả

        if row:
            # Người dùng đã tồn tại, không cần thêm nữa
            pass
        else:
            # Người dùng chưa tồn tại, thêm vào bảng users với ngôn ngữ mặc định
            now_vn = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "INSERT INTO users (id_user, user_name, language, created_at) VALUES (?, ?, ?, ?)",
                (user_id, user_name, DEFAULT_LANGUAGE, now_vn, )
            )
            conn.commit()
            logger.info(f"Added new user: ID={user_id}, Username={user_name}")

        cursor.execute("SELECT * FROM users WHERE id_user = ? and is_blocked = 1", (user_id,))
        data = cursor.fetchone()
        
        if data:
            logger.info(f"{user_id} is blocked but using /start")
            await update.message.reply_text(get_text(user_id, 'start.blocked'))
            return

        # Gửi tin nhắn chào mừng + nút thao tác nhanh (onboarding)
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Dashboard", callback_data="back_dashboard:NONE")],
            [InlineKeyboardButton("🛍️ Products", callback_data="go_listproducts:NONE")],
            [InlineKeyboardButton("💰 Add Balance", callback_data="go_payment_info:NONE")],
            [
                InlineKeyboardButton("📋 My Orders", callback_data="go_orders:NONE"),
                InlineKeyboardButton("📜 Recharge History", callback_data="go_actions:NONE"),
            ],
            [
                InlineKeyboardButton("🌐 Language", callback_data="go_languages:NONE"),
                InlineKeyboardButton("💬 Support", callback_data="go_support:NONE"),
            ],
        ])
        await update.message.reply_text(get_text(user_id, 'start.welcome'), reply_markup=buttons)

    except Exception as e:
        logger.exception("Failed to create table users.")  # in ra full traceback

    finally:
        cursor.close()
        conn.close()

# process /help for client
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    user_id = update.message.from_user.id
    text=update.message.text

    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id_user = ? and is_blocked = 1", (user_id,))
    data = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if data:
        logger.info(f"{user_id} is blocked but using /start")
        await update.message.reply_text(get_text(user_id, 'common.blocked'))
        return

    admin_username = (settings.USER_NAME and settings.USER_NAME.strip()) or get_text(user_id, 'common.admin')
    lang = get_user_language(user_id)

    if lang == "vi":
        msg = (
            "📖 <b>HƯỚNG DẪN NHANH</b>\n\n"
            "🧭 <b>Menu chính</b>\n"
            "• <code>/start</code> — Mở hướng dẫn + menu nhanh\n"
            "• <code>/dashboard</code> — Mở menu chính\n\n"
            "🛍️ <b>Mua hàng</b>\n"
            "• <code>/listproducts</code> — Xem danh sách sản phẩm\n"
            "• Chọn sản phẩm → chọn số lượng → mua bằng ví hoặc mua trực tiếp\n\n"
            "💰 <b>Nạp tiền</b>\n"
            "• <code>/addfund</code> — Chọn phương thức nạp (Crypto / VN Bank)\n"
            "• <code>/cancelrecharge</code> — Hủy luồng nạp đang chờ\n\n"
            "📋 <b>Đơn hàng & lịch sử</b>\n"
            "• Trong <code>/dashboard</code> → <b>Đơn hàng</b> / <b>Lịch sử nạp</b>\n\n"
            "👤 <b>Tài khoản</b>\n"
            "• <code>/myid</code> — Xem ID\n"
            "• <code>/aboutme</code> — Xem thông tin tài khoản\n"
            "• <code>/language</code> — Đổi ngôn ngữ\n\n"
            f"💬 <b>Hỗ trợ:</b> {get_text(user_id, 'support.contact')} <b>{admin_username}</b>\n"
        )
    else:
        msg = (
            "📖 <b>QUICK HELP</b>\n\n"
            "🧭 <b>Main menu</b>\n"
            "• <code>/start</code> — Welcome + quick menu\n"
            "• <code>/dashboard</code> — Open main menu\n\n"
            "🛍️ <b>Shopping</b>\n"
            "• <code>/listproducts</code> — Browse products\n"
            "• Pick product → choose quantity → buy with wallet or buy directly\n\n"
            "💰 <b>Top up</b>\n"
            "• <code>/addfund</code> — Choose topup method (Crypto / VN Bank)\n"
            "• <code>/cancelrecharge</code> — Cancel pending topup flow\n\n"
            "📋 <b>Orders & history</b>\n"
            "• In <code>/dashboard</code> → <b>My Orders</b> / <b>Recharge History</b>\n\n"
            "👤 <b>Account</b>\n"
            "• <code>/myid</code> — Show your ID\n"
            "• <code>/aboutme</code> — Show account info\n"
            "• <code>/language</code> — Change language\n\n"
            f"💬 <b>Support:</b> {get_text(user_id, 'support.contact')} <b>{admin_username}</b>\n"
        )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Dashboard", callback_data="back_dashboard:NONE")],
        [InlineKeyboardButton("🛍️ Products", callback_data="go_listproducts:NONE")],
        [InlineKeyboardButton("💰 Add Balance", callback_data="go_payment_info:NONE")],
    ])

    logger.info(f"Displayed help command to user ID={update.message.from_user.id}")
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=buttons)
    return


# process /myid for client
async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # if client don't say anything
    if not update.message:
        return
    
    user_id = update.message.from_user.id
    username = update.message.from_user.name

    text = update.message.text

    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id_user = ? and is_blocked = 1", (user_id,))
    data = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if data:
        logger.info(f"{user_id} is blocked but using /start")
        await update.message.reply_text(get_text(user_id, 'common.blocked'))
        return

    text_reply = f"{get_text(user_id, 'user_info.id')}: `{user_id}`\n{get_text(user_id, 'user_info.username')}: {username}"
    logger.info(f"Get user ID command: ID: {user_id} Username: {username}" )
    await update.message.reply_text(text_reply, parse_mode="Markdown")
    return


async def aboutme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    caller_id = update.message.from_user.id
    text = update.message.text

    conn = db_connect()
    cursor = conn.cursor()
    try:

        # LƯU Ý: phải là (caller_id,) để tạo tuple
        cursor.execute("SELECT * FROM users WHERE id_user = ?", (caller_id,))
        row = cursor.fetchone()
        cursor.close()

        if not row:
            await update.message.reply_text(get_text(caller_id, 'user_info.not_found'))
            logger.info(f"{caller_id} doesn't find information")
            return

        # Map dữ liệu thành dict cho dễ xử lý
        #(id_user, username, balance, currency, issubadmin,isblocked, products_bought, language, created_at)
        user = {
            "id_user":     html.escape(str(row[0])),
            "user_name":   html.escape(str(row[1])),
            "balance":     html.escape(str(row[2])),
            "currency":    row[3],
            "is_subadmin": bool(row[4]),
            "is_blocked":  bool(row[5]),
            "products_bought": html.escape(str(row[6])),
            "created_at":  html.escape(str(row[8] if len(row) > 8 else row[7])),
        }

        # Format tin nhắn trả lời 
        msg = f"""{get_text(caller_id, 'user_info.title')}
• {get_text(caller_id, 'user_info.id')}: <code>{user['id_user']}</code>
• {get_text(caller_id, 'user_info.username')}: {user['user_name']}
• {get_text(caller_id, 'user_info.balance')}: {user['balance']} {user['currency']}
• Sub-admin: {'✅' if user['is_subadmin'] else '❌'}
• Is Blocked: {'✅' if user['is_blocked'] else '❌'}
• {get_text(caller_id, 'user_info.products_bought')}: {user['products_bought']}
• {get_text(caller_id, 'user_info.created_at')}: {user['created_at']} GMT+7"""
        await update.message.reply_text(text=msg, parse_mode="HTML")

    except Exception as e:
        logger.exception("Aboutme command failed: {e}")
        await update.message.reply_text("❌ Error command.")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# /listproducts
async def listproducts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if get_active_flow(context):
        await notify_flow_busy(update, context)
        return
    
    caller_id = update.message.from_user.id
    text = update.message.text

    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM users WHERE is_blocked=1 AND id_user=?", (caller_id,))
        if cursor.fetchone():
            await update.message.reply_text(get_text(caller_id, 'common.blocked'))
            return

        cursor.execute("SELECT id_product, name, price FROM listproducts ORDER BY id_product")
        rows = cursor.fetchall()
        if not rows:
            await update.message.reply_text(get_text(caller_id, 'products.not_found'))
            return

        buttons = [[InlineKeyboardButton(text=f"{name} — {price}$", callback_data=f"prod:{pid}")]
                   for (pid, name, price) in rows]

        buttons.append([InlineKeyboardButton(get_text(caller_id, 'dashboard.reload'), callback_data="reload_products:NONE")])
        buttons.append([InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")])

        await update.message.reply_text(
            get_text(caller_id, 'products.title') + ":",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    finally:            
        cursor.close()
        conn.close()


async def handle_reload_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()

    caller_id = q.from_user.id
    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM users WHERE is_blocked=1 AND id_user=?", (caller_id,))
        if cursor.fetchone():
            await q.edit_message_text(get_text(caller_id, 'common.blocked'))
            return

        cursor.execute("SELECT id_product, name, price FROM listproducts ORDER BY id_product")
        rows = cursor.fetchall()
        if not rows:
            await q.edit_message_text(get_text(caller_id, 'products.not_found'))
            return

        buttons = [[InlineKeyboardButton(text=f"{name} — {price}$", callback_data=f"prod:{pid}")]
                   for (pid, name, price) in rows]
        buttons.append([InlineKeyboardButton(get_text(caller_id, 'dashboard.reload'), callback_data="reload_products:NONE")])
        buttons.append([InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")])

        await q.edit_message_text(
            get_text(caller_id, 'products.title') + ":",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    finally:
        cursor.close()
        conn.close()

# Hàm chung để tạo dashboard menu - đảm bảo tính nhất quán
def create_dashboard_menu(user_id: int) -> InlineKeyboardMarkup:
    """Tạo menu dashboard với format chuyên nghiệp và nhất quán"""
    return InlineKeyboardMarkup([
        # Nhóm 1: Thông tin cá nhân
        [InlineKeyboardButton(f"👤 {get_text(user_id, 'dashboard.user_info')}", callback_data="go_user_info:adfasd")],
        
        # Nhóm 2: Mua sắm
        [InlineKeyboardButton(f"🛍️ {get_text(user_id, 'dashboard.list_products')}", callback_data="go_listproducts:NONE")],
        
        # Nhóm 3: Quản lý đơn hàng và lịch sử
        [
            InlineKeyboardButton(f"📋 {get_text(user_id, 'dashboard.my_orders')}", callback_data="go_orders:NONE"),
            InlineKeyboardButton(f"📜 {get_text(user_id, 'dashboard.actions')}", callback_data="go_actions:NONE")
        ],
        
        # Nhóm 4: Nạp tiền
        [InlineKeyboardButton(f"💰 {get_text(user_id, 'dashboard.add_balance')}", callback_data="go_payment_info:NONE")],
        
        # Nhóm 5: Cài đặt và hỗ trợ
        [
            InlineKeyboardButton(f"🌐 {get_text(user_id, 'dashboard.languages')}", callback_data="go_languages:NONE"),
            InlineKeyboardButton(f"💬 {get_text(user_id, 'dashboard.support')}", callback_data="go_support:NONE")
        ],
        
        # Nhóm 6: Phân tích (đặt cuối)
        [InlineKeyboardButton(f"📊 {get_text(user_id, 'dashboard.analytics')}", callback_data="go_analytics:NONE")]
    ])

# dashboard
async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    # Clear any pending flow when user goes to dashboard (allows canceling flows)
    clear_active_flow(context)
    
    caller_id = update.effective_user.id
    text = update.message.text

    conn = db_connect()
    cursor = conn.cursor()

    try:
        # Nếu không phải admin thì kiểm tra bị chặn hay không
        if caller_id != settings.ADMIN_ID:
            cursor.execute(
                "SELECT 1 FROM users WHERE id_user = ? AND is_blocked = 1",
                (caller_id,)
            )
            row = cursor.fetchone()
            if row:  # Nếu có kết quả -> bị chặn
                await update.message.reply_text(get_text(caller_id, 'common.blocked'))
                return

        # Sử dụng hàm chung để tạo menu dashboard
        buttons = create_dashboard_menu(caller_id)
        await update.message.reply_text(text=get_text(caller_id, 'dashboard.title'), reply_markup=buttons)
        return

    except Exception as e:
        await update.message.reply_text(f"❌ Error System: {e}")
        return

    finally:
        cursor.close()
        conn.close()

# add_fund
async def add_fund(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # if client don't say anything
    if not update.message:
        return
    
    user_id = update.message.from_user.id
    username = update.message.from_user.name

    conn = db_connect()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM users WHERE id_user = ? and is_blocked = 1", (user_id,))
        data = cursor.fetchone()
        
        if data:
            logger.info(f"{user_id} is blocked but using /addfund")
            await update.message.reply_text(get_text(user_id, 'common.blocked'))
            return

        # Hiển thị menu Payment Methods giống như luồng Add Balance
        text = f"💰 **{get_text(user_id, 'payment.title')}**\n"
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(user_id, 'payment.crypto'), callback_data="crypto_recharge:NONE")],
            [InlineKeyboardButton(get_text(user_id, 'common.back'), callback_data="back_dashboard:NONE")],
        ])

        logger.info(f"User {user_id} ({username}) used /addfund")
        await update.message.reply_text(text=text, reply_markup=buttons, parse_mode="Markdown")
        
    except Exception as e:
        logger.exception(f"Add fund command failed for user {user_id}: {e}")
        await update.message.reply_text(get_text(user_id, 'error.generic'))
    finally:
        cursor.close()
        conn.close()
    return
    
# callback_data click buy
async def product_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()

    id_user = q.from_user.id

    if get_active_flow(context) not in (None, "product_qty"):
        await notify_flow_busy(update, context)
        return

    data = q.data
    if not data.startswith("prod:"):
        return

    try:
        # Hỗ trợ cả số và chữ cho product_id
        product_id_str = data.split(":", 1)[1].strip().upper()
        product_id = product_id_str
    except (ValueError, IndexError):
        await q.edit_message_text(get_text(id_user, 'products.not_found'))
        return

    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name, price, quality, descrip FROM listproducts WHERE id_product = ?", (product_id,))
        row = cursor.fetchone()
    except Exception as e:
        logger.exception("SQL error: %s", e)
        row = None
    finally:
        cursor.close()
        conn.close()

    if not row:
        await q.edit_message_text(get_text(id_user, 'products.not_found'))
        return

    name, price, quality, descrip = row
    qty = 1
    step = 1  # Step mode mặc định là 1
    stock = quality if quality is not None else 0
    
    # Lưu trạng thái: đang xem sản phẩm từ list products
    context.user_data["previous_state"] = "listproducts"
    context.user_data["viewing_product_id"] = product_id
    
    text = build_product_text(id_user, name, product_id, price, stock, qty, descrip)
    keyboard = build_product_keyboard(id_user, product_id, qty, step, back_to_list=True)

    context.user_data["active_flow"] = "product_qty"
    await q.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def handle_qty_adjust(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()

    if get_active_flow(context) not in (None, "product_qty"):
        await notify_flow_busy(update, context)
        return

    data = q.data or ""
    if not data.startswith("qty:"):
        return
    parts = data.split(":")
    if len(parts) < 3:
        return
    try:
        # Hỗ trợ cả số và chữ cho product_id
        product_id = str(parts[1]).strip().upper()
        qty = int(parts[2])
        # Lấy step mode (mặc định là 1 nếu không có)
        step = int(parts[3]) if len(parts) >= 4 else 1
    except (ValueError, IndexError):
        return
    
    # Validate step mode
    valid_steps = [1, 2, 5, 10, 20, 50, 100]
    if step not in valid_steps:
        step = 1
    
    # Đảm bảo qty không nhỏ hơn 1
    if qty < 1:
        qty = 1

    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name, price, quality, descrip FROM listproducts WHERE id_product = ?", (product_id,))
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not row:
        await q.edit_message_text(get_text(q.from_user.id, 'products.not_found'))
        return

    name, price, quality, descrip = row
    stock = quality if quality is not None else 0
    if stock and qty > stock:
        qty = stock
    text = build_product_text(q.from_user.id, name, product_id, price, stock, qty, descrip)
    # Giữ nguyên trạng thái back_to_list từ context hoặc mặc định True
    back_to_list = context.user_data.get("previous_state") == "listproducts"
    keyboard = build_product_keyboard(q.from_user.id, product_id, qty, step, back_to_list=back_to_list)
    await q.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def handle_qty_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle step mode selection (1, 2, 5, 10, 20, 50, 100)"""
    q = update.callback_query
    if not q:
        return
    await q.answer()

    if get_active_flow(context) not in (None, "product_qty"):
        await notify_flow_busy(update, context)
        return

    data = q.data or ""
    if not data.startswith("qtymode:"):
        return
    parts = data.split(":")
    if len(parts) < 4:
        return
    try:
        product_id = str(parts[1]).strip().upper()
        qty = int(parts[2])
        step = int(parts[3])
    except (ValueError, IndexError):
        return

    # Validate step mode
    valid_steps = [1, 2, 5, 10, 20, 50, 100]
    if step not in valid_steps:
        step = 1

    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name, price, quality, descrip FROM listproducts WHERE id_product = ?", (product_id,))
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not row:
        await q.edit_message_text(get_text(q.from_user.id, 'products.not_found'))
        return

    name, price, quality, descrip = row
    stock = quality if quality is not None else 0
    if stock and qty > stock:
        qty = stock
    text = build_product_text(q.from_user.id, name, product_id, price, stock, qty, descrip)
    # Giữ nguyên trạng thái back_to_list từ context hoặc mặc định True
    back_to_list = context.user_data.get("previous_state") == "listproducts"
    keyboard = build_product_keyboard(q.from_user.id, product_id, qty, step, back_to_list=back_to_list)
    await q.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


async def handle_qty_noop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()

# callback_data buy confirm, ví dụ: "buy:123:1"  (123 = id_product, 1 = quantity)
async def handle_buy_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()
    # Trong callback, update.message = None -> dùng q.from_user / q.message
    id_user = q.from_user.id

    if get_active_flow(context) not in (None, "product_qty"):
        await notify_flow_busy(update, context)
        return

    data = q.data              # ❗ q.data là thuộc tính, KHÔNG phải hàm
    if not data.startswith("buy:"):
        return

    # parse: buy:<id_product>:<qty?>
    parts = data.split(":")
    if len(parts) < 2:
        buttom = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(id_user, 'common.back'), callback_data="back_dashboard:NONE")]
        ])
        await q.edit_message_text(get_text(id_user, 'error.generic'), reply_markup=buttom, parse_mode="Markdown")
        return
    try:
        # Hỗ trợ cả số và chữ cho id_product
        id_product = parts[1].strip().upper()
        qty = int(parts[2]) if len(parts) >= 3 else 1
    except (ValueError, IndexError):
        buttom = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(id_user, 'common.back'), callback_data="back_dashboard:NONE")]
        ])
        await q.edit_message_text(get_text(id_user, 'error.generic'), reply_markup=buttom, parse_mode="Markdown")
        return

    conn = db_connect()
    cursor = conn.cursor()
    try:
        # Lấy user (đặt đúng tên cột của bạn: id_user hay user_id? user_name hay name?)
        cursor.execute("SELECT user_name, balance FROM users WHERE id_user = ?", (id_user,))
        row = cursor.fetchone()
        if not row:
            buttom = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(id_user, 'common.back'), callback_data="back_dashboard:NONE")]
        ])
            await q.edit_message_text(get_text(id_user, 'error.generic'), reply_markup=buttom, parse_mode="Markdown")
            return
        username, balance = row

        # Lấy thông tin sản phẩm (bao gồm mode)
        cursor.execute("SELECT price, name, quality, mode, descrip FROM listproducts WHERE id_product = ?", (id_product,))
        product_info = cursor.fetchone()
        if not product_info:
            buttom = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(id_user, 'common.back'), callback_data="back_dashboard:NONE")]
        ])
            await q.edit_message_text(get_text(id_user, 'error.generic'), reply_markup=buttom, parse_mode="Markdown")
            return
        price, name, stock, product_mode, descrip = product_info
        product_mode = product_mode if product_mode is not None else 0

        # Kiểm tra tồn kho
        if stock is not None and stock < qty:
            # Quay về sản phẩm với nút Back về list products
            step = 1
            cursor.execute("SELECT descrip FROM listproducts WHERE id_product = ?", (id_product,))
            descrip_row = cursor.fetchone()
            descrip = descrip_row[0] if descrip_row else None
            error_text = f"{get_text(id_user, 'products.out_of_stock')}. {get_text(id_user, 'products.stock')}: {stock}"
            product_text = build_product_text(id_user, name, id_product, price, stock, qty, descrip or "")
            full_text = f"{error_text}\n\n{product_text}"
            keyboard = build_product_keyboard(id_user, id_product, qty, step, back_to_list=True)
            await q.edit_message_text(full_text, reply_markup=keyboard, parse_mode="Markdown")
            return

        total_cost = price * qty
        # Kiểm tra số dư
        if balance < total_cost:
            # Quay về sản phẩm với nút Back về list products
            step = 1
            cursor.execute("SELECT descrip FROM listproducts WHERE id_product = ?", (id_product,))
            descrip_row = cursor.fetchone()
            descrip = descrip_row[0] if descrip_row else None
            error_text = f"{get_text(id_user, 'products.insufficient_balance')}: {balance}$ — {get_text(id_user, 'products.total')}: {total_cost}$"
            product_text = build_product_text(id_user, name, id_product, price, stock, qty, descrip or "")
            full_text = f"{error_text}\n\n{product_text}"
            keyboard = build_product_keyboard(id_user, id_product, qty, step, back_to_list=True)
            await q.edit_message_text(full_text, reply_markup=keyboard, parse_mode="Markdown")
            return

        # Trừ tiền
        cursor.execute("UPDATE users SET balance = balance - ? WHERE id_user = ?", (total_cost, id_user))
        
        # Tạo order ID
        id_order = random.randint(1001, 9999)
        while cursor.execute("SELECT * FROM orders WHERE id_order = ?", (id_order,)):
            if (not cursor.fetchone()):
                break
            else:
                id_order = random.randint(1001, 9999)
        
        now_vn = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
        
        # Xử lý theo mode
        if product_mode == 0:
            # Mode 0: Yêu cầu người dùng nhập thông tin
            # Tạo order với status PENDING, chưa có user_info
            cursor.execute(
                "INSERT INTO orders (id_order, id_buyer, name, price, quality, status, created_at, product_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (id_order, id_user, name, price, qty, "PENDING", now_vn, id_product)
            )
            cursor.execute("UPDATE users SET products_bought = products_bought + 1 WHERE id_user = ?", (id_user,))
            conn.commit()
            
            # Yêu cầu người dùng nhập thông tin
            lang = get_user_language(id_user)
            if lang == 'vi':
                prompt_text = (
                    f"📝 **Vui lòng nhập thông tin đơn hàng**\n\n"
                    f"🛍️ Sản phẩm: **{name}**\n"
                    f"🔢 Số lượng: **{qty}**\n"
                    f"💰 Tổng tiền: **{total_cost}$**\n"
                    f"🆔 Mã đơn: `{id_order}`\n\n"
                )
                if descrip and descrip.strip() and descrip != '@daksdlkasd':
                    prompt_text += f"**📄 Yêu cầu thông tin:**\n{descrip}\n\n"
                prompt_text += "💡 Gửi thông tin theo yêu cầu trên. Bot sẽ gửi đơn hàng đến admin để xử lý."
            else:
                prompt_text = (
                    f"📝 **Please enter order information**\n\n"
                    f"🛍️ Product: **{name}**\n"
                    f"🔢 Quantity: **{qty}**\n"
                    f"💰 Total: **{total_cost}$**\n"
                    f"🆔 Order ID: `{id_order}`\n\n"
                )
                if descrip and descrip.strip() and descrip != '@daksdlkasd':
                    prompt_text += f"**📄 Information required:**\n{descrip}\n\n"
                prompt_text += "💡 Send the information as requested. Bot will send the order to admin for processing."
            
            # Lưu trạng thái đang chờ thông tin
            context.user_data["awaiting_order_info"] = True
            context.user_data["order_info_order_id"] = id_order
            context.user_data["order_info_product_id"] = id_product
            context.user_data["order_info_product_name"] = name
            context.user_data["order_info_qty"] = qty
            context.user_data["order_info_total"] = total_cost
            context.user_data["active_flow"] = "order_info"
            
            buttom = InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Hủy đơn" if lang == 'vi' else "❌ Cancel order", callback_data=f"cancel_order_info:{id_order}")]
            ])
            await q.edit_message_text(prompt_text, reply_markup=buttom, parse_mode="Markdown")
            logger.info(f"{id_user} bought {name} qty={qty} cost={total_cost} (wallet, mode=0, waiting for info)")
            return
        
        else:
            # Mode 1: Tự động giao hàng (logic cũ)
            items_to_deliver = []
            if stock is not None and stock > 0:
                # Lấy qty items từ stock_items (chỉ lấy items chưa bán)
                cursor.execute(
                    "SELECT id, item_content FROM stock_items WHERE product_id = ? AND status = 'PENDING' ORDER BY id LIMIT ?",
                    (id_product, qty)
                )
                items_to_deliver = cursor.fetchall()
                
                if len(items_to_deliver) < qty:
                    logger.warning(f"Not enough items in stock_items for {id_product}. Requested: {qty}, Available: {len(items_to_deliver)}")
                
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
                cursor.execute("UPDATE listproducts SET quality = quality - ? WHERE id_product = ?", (qty, id_product))

            cursor.execute(
                "INSERT INTO orders (id_order, id_buyer, name, price, quality, status, created_at, product_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (id_order, id_user, name, price, qty, "DONE", now_vn, id_product)
            )
            cursor.execute("UPDATE users SET products_bought = products_bought + 1 WHERE id_user = ?", (id_user,))

            conn.commit()

            logger.info(f"{id_user} bought {name} qty={qty} cost={total_cost} (wallet, mode=1)")

            # Gửi items cho người dùng
            if items_to_deliver:
                await context.bot.send_message(
                    chat_id=id_user,
                    text=f"📦 **{get_text(id_user, 'products.purchase_success')}**\n🛍️ {name}\n🔢 Quality: {qty}\n\n**Order details:**"
                )
                for idx, (item_id, item_content) in enumerate(items_to_deliver, 1):
                    await context.bot.send_message(
                        chat_id=id_user,
                        text=f"**Item {idx}/{len(items_to_deliver)}:**\n```\n{item_content}\n```",
                        parse_mode="Markdown"
                    )
            else:
                await context.bot.send_message(
                    chat_id=id_user,
                    text=f"✅ **{get_text(id_user, 'products.purchase_success')}**\n🛍️ {name}\n🔢 Quantity: {qty}\n💸 Total: {total_cost}$\n\n⚠️ Please contact admin to receive the goods."
                )

            admin_order_new = get_text(
                id_user,
                "admin.order_new",
                buyer_id=id_user,
                order_id=id_order,
                product_id=id_product,
                product_name=name,
                quantity=qty,
                price=price,
                total=total_cost,
            )
            admin_order_success = get_text(
                id_user,
                "admin.order_success",
                buyer_id=id_user,
                order_id=id_order,
                product_id=id_product,
                product_name=name,
                quantity=qty,
                price=price,
                total=total_cost,
            )
            await context.bot.send_message(chat_id=settings.ADMIN_ID, text=admin_order_new)
            await context.bot.send_message(chat_id=settings.ADMIN_ID, text=admin_order_success)

            text = (
                f"✅ **{get_text(id_user, 'products.purchase_success')}**\n"
                f"👤 {get_text(id_user, 'user_info.username')}: `{username}`\n"
                f"🛍 {get_text(id_user, 'products.name')}: **{name}**\n"  
                f"🔢 {get_text(id_user, 'products.quantity')}: `{qty}`\n"
                f"💸 {get_text(id_user, 'products.total')}: `{total_cost}$`"
            )
            if items_to_deliver:
                text += f"\n\n📦 Delivered {len(items_to_deliver)} item(s). Check messages for details."
            buttom = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(id_user, 'common.back'), callback_data="back_dashboard:NONE")]
            ])
            await q.edit_message_text(text, reply_markup=buttom, parse_mode="Markdown")
            return

    except Exception as e:
        logger.exception(f"[BUY WALLET] ERROR: {e}")
        buttom = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(id_user, 'common.back'), callback_data="back_dashboard:NONE")]
        ])
        await q.edit_message_text(get_text(id_user, 'error.generic'), reply_markup=buttom, parse_mode="Markdown")
        return
    finally:
        cursor.close()
        conn.close()


# Handler nhận thông tin đơn hàng từ người dùng (mode 0)
async def handle_order_info_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý thông tin đơn hàng từ người dùng (mode 0)"""
    if not update.message:
        return
    
    if not context.user_data.get("awaiting_order_info"):
        return
    
    user_id = update.effective_user.id
    user_info = update.message.text.strip()
    order_id = context.user_data.get("order_info_order_id")
    product_id = context.user_data.get("order_info_product_id")
    product_name = context.user_data.get("order_info_product_name")
    qty = context.user_data.get("order_info_qty")
    total_cost = context.user_data.get("order_info_total")
    
    if not order_id:
        await update.message.reply_text("❌ Lỗi: Không tìm thấy thông tin đơn hàng.")
        return
    
    conn = db_connect()
    cursor = conn.cursor()
    try:
        # Cập nhật order với thông tin người dùng
        cursor.execute(
            "UPDATE orders SET user_info = ?, status = 'PENDING' WHERE id_order = ? AND id_buyer = ?",
            (user_info, order_id, user_id)
        )
        conn.commit()
        
        # Lấy thông tin user
        cursor.execute("SELECT user_name FROM users WHERE id_user = ?", (user_id,))
        user_row = cursor.fetchone()
        username = user_row[0] if user_row else str(user_id)
        
        # Gửi thông báo cho admin và subadmin
        lang = get_user_language(user_id)
        if lang == 'vi':
            admin_msg = (
                f"🆕 **ĐƠN HÀNG MỚI (Cần xử lý thủ công)**\n"
                f"🆔 Order ID: `{order_id}`\n"
                f"👤 User: {username} (`{user_id}`)\n"
                f"🛍️ Sản phẩm: **{product_name}**\n"
                f"🆔 Product ID: `{product_id}`\n"
                f"🔢 Số lượng: **{qty}**\n"
                f"💰 Tổng tiền: **{total_cost}$**\n\n"
                f"📝 **Thông tin từ người dùng:**\n{user_info}\n\n"
                f"⚠️ Vui lòng xử lý đơn hàng này."
            )
        else:
            admin_msg = (
                f"🆕 **NEW ORDER (Manual processing required)**\n"
                f"🆔 Order ID: `{order_id}`\n"
                f"👤 User: {username} (`{user_id}`)\n"
                f"🛍️ Product: **{product_name}**\n"
                f"🆔 Product ID: `{product_id}`\n"
                f"🔢 Quantity: **{qty}**\n"
                f"💰 Total: **{total_cost}$**\n\n"
                f"📝 **User information:**\n{user_info}\n\n"
                f"⚠️ Please process this order."
            )
        
        # Tạo nút xác nhận/hủy/mute
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Xác nhận", callback_data=f"order_confirm:{order_id}"),
                InlineKeyboardButton("❌ Hủy đơn", callback_data=f"order_cancel:{order_id}")
            ],
            [InlineKeyboardButton("🔇 Mute", callback_data=f"order_mute:{order_id}")]
        ])
        
        # Gửi cho admin
        await context.bot.send_message(
            chat_id=settings.ADMIN_ID,
            text=admin_msg,
            reply_markup=buttons,
            parse_mode="Markdown"
        )
        
        # Gửi cho tất cả subadmin
        cursor.execute("SELECT id_user FROM subadmins")
        subadmins = cursor.fetchall()
        for (subadmin_id,) in subadmins:
            try:
                await context.bot.send_message(
                    chat_id=subadmin_id,
                    text=admin_msg,
                    reply_markup=buttons,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Failed to send order notification to subadmin {subadmin_id}: {e}")
        
        # Thông báo cho người dùng
        if lang == 'vi':
            user_msg = (
                f"✅ **Đã gửi thông tin đơn hàng**\n"
                f"🆔 Mã đơn: `{order_id}`\n"
                f"🛍️ Sản phẩm: **{product_name}**\n"
                f"🔢 Số lượng: **{qty}**\n"
                f"💰 Tổng tiền: **{total_cost}$**\n\n"
                f"📝 Thông tin bạn đã gửi:\n{user_info}\n\n"
                f"⏳ Đơn hàng đã được gửi đến admin. Bạn sẽ nhận thông báo khi đơn hàng được xử lý."
            )
        else:
            user_msg = (
                f"✅ **Order information sent**\n"
                f"🆔 Order ID: `{order_id}`\n"
                f"🛍️ Product: **{product_name}**\n"
                f"🔢 Quantity: **{qty}**\n"
                f"💰 Total: **{total_cost}$**\n\n"
                f"📝 Information you sent:\n{user_info}\n\n"
                f"⏳ Order has been sent to admin. You will be notified when the order is processed."
            )
        
        await update.message.reply_text(user_msg, parse_mode="Markdown")
        
        # Clear flow
        for key in ("awaiting_order_info", "order_info_order_id", "order_info_product_id", 
                   "order_info_product_name", "order_info_qty", "order_info_total", "active_flow"):
            context.user_data.pop(key, None)
        
        logger.info(f"Order {order_id} info received from user {user_id}")
        
    except Exception as e:
        logger.exception(f"Error in handle_order_info_input: {e}")
        await update.message.reply_text("❌ Lỗi khi xử lý thông tin đơn hàng. Vui lòng thử lại.")
    finally:
        cursor.close()
        conn.close()


# Handler hủy nhập thông tin đơn hàng
async def handle_cancel_order_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hủy việc nhập thông tin đơn hàng"""
    q = update.callback_query
    if not q:
        return
    await q.answer()
    
    user_id = q.from_user.id
    data = q.data or ""
    if not data.startswith("cancel_order_info:"):
        return
    
    try:
        order_id = int(data.split(":")[1])
    except (ValueError, IndexError):
        return
    
    conn = db_connect()
    cursor = conn.cursor()
    try:
        # Xóa order và hoàn tiền
        cursor.execute("SELECT id_buyer, price, quality FROM orders WHERE id_order = ? AND id_buyer = ?", (order_id, user_id))
        order_row = cursor.fetchone()
        
        if order_row:
            buyer_id, price, qty = order_row
            total_cost = price * qty
            
            # Hoàn tiền
            cursor.execute("UPDATE users SET balance = balance + ? WHERE id_user = ?", (total_cost, buyer_id))
            # Xóa order
            cursor.execute("DELETE FROM orders WHERE id_order = ? AND id_buyer = ?", (order_id, user_id))
            conn.commit()
            
            lang = get_user_language(user_id)
            if lang == 'vi':
                msg = f"❌ Đã hủy đơn hàng {order_id}. Tiền đã được hoàn lại vào ví."
            else:
                msg = f"❌ Order {order_id} cancelled. Money has been refunded to wallet."
            
            await q.edit_message_text(msg, parse_mode="Markdown")
            logger.info(f"Order {order_id} cancelled by user {user_id}, refunded {total_cost}")
        
    except Exception as e:
        logger.exception(f"Error in handle_cancel_order_info: {e}")
    finally:
        cursor.close()
        conn.close()
    
    # Clear flow
    for key in ("awaiting_order_info", "order_info_order_id", "order_info_product_id", 
               "order_info_product_name", "order_info_qty", "order_info_total", "active_flow"):
        context.user_data.pop(key, None)

# callback_data buy_direct:product_id:qty - Mua trực tiếp qua SePay
async def handle_buy_direct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle direct purchase via SePay QR payment"""
    q = update.callback_query
    if not q:
        return
    await q.answer()
    
    id_user = q.from_user.id

    if get_active_flow(context) not in (None, "product_qty"):
        await notify_flow_busy(update, context)
        return

    data = q.data
    if not data.startswith("buy_direct:"):
        return

    # parse: buy_direct:<id_product>:<qty?>
    parts = data.split(":")
    if len(parts) < 2:
        buttom = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(id_user, 'common.back'), callback_data="back_dashboard:NONE")]
        ])
        await q.edit_message_text(get_text(id_user, 'error.generic'), reply_markup=buttom, parse_mode="Markdown")
        return
    try:
        id_product = parts[1].strip().upper()
        qty = int(parts[2]) if len(parts) >= 3 else 1
    except (ValueError, IndexError):
        buttom = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(id_user, 'common.back'), callback_data="back_dashboard:NONE")]
        ])
        await q.edit_message_text(get_text(id_user, 'error.generic'), reply_markup=buttom, parse_mode="Markdown")
        return

    conn = db_connect()
    cursor = conn.cursor()
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(id_user, 'common.back'), callback_data="back_dashboard:NONE")]
    ])
    
    try:
        # Kiểm tra user bị chặn
        cursor.execute("SELECT 1 FROM users WHERE id_user = ? AND is_blocked = 1", (id_user,))
        if cursor.fetchone():
            await q.edit_message_text(get_text(id_user, 'common.blocked'), reply_markup=buttons, parse_mode="Markdown")
            return

        # Lấy thông tin sản phẩm
        cursor.execute("SELECT price, name, quality FROM listproducts WHERE id_product = ?", (id_product,))
        product_info = cursor.fetchone()
        if not product_info:
            await q.edit_message_text(get_text(id_user, 'products.not_found'), reply_markup=buttons, parse_mode="Markdown")
            return
        price, name, stock = product_info

        # Kiểm tra tồn kho
        if stock is not None and stock < qty:
            error_text = f"{get_text(id_user, 'products.out_of_stock')}. {get_text(id_user, 'products.stock')}: {stock}"
            await q.edit_message_text(error_text, reply_markup=buttons, parse_mode="Markdown")
            return

        # Tính tổng tiền cần thanh toán
        total_cost_usdt = price * qty
        # Chuyển đổi sang VND
        amount_vnd = int(total_cost_usdt * EXCHANGE_RATE_VND)
        amount_usdt = total_cost_usdt

        # Kiểm tra cấu hình ngân hàng
        bank_acc = str(getattr(settings, "VN_BANK_ACCOUNT", "") or "").strip()
        bank_code = str(getattr(settings, "VN_BANK_CODE", "") or "").strip()
        bank_name = str(getattr(settings, "VN_BANK_NAME", "") or "").strip()
        bank_param = bank_code or bank_name

        if not bank_acc or not bank_param:
            await q.edit_message_text(get_text(id_user, 'sepay.not_configured'), reply_markup=buttons, parse_mode="HTML")
            return

        # Tạo order code với prefix BUY để phân biệt
        order_code = f"BUY{id_user}{int(time.time())}"
        while True:
            cursor.execute("SELECT 1 FROM recharge_orders WHERE order_code = ?", (order_code,))
            if cursor.fetchone():
                order_code = f"BUY{id_user}{int(time.time())}{random.randint(10,99)}"
            else:
                break

        # Lưu thông tin sản phẩm vào recharge_orders
        cursor.execute(
            "INSERT INTO recharge_orders (order_code, id_user, amount_vnd, amount_usdt, status, product_id, product_qty, product_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (order_code, id_user, amount_vnd, amount_usdt, "PENDING", id_product, qty, name)
        )
        conn.commit()

        # Tạo QR code
        description = urllib.parse.quote(order_code)
        bank_param_safe = urllib.parse.quote(bank_param)
        qr_url = f"https://qr.sepay.vn/img?acc={bank_acc}&bank={bank_param_safe}&amount={amount_vnd}&des={description}"

        # Lấy ngôn ngữ để hiển thị
        from i18n import get_user_language
        lang = get_user_language(id_user)
        
        # Thêm thời gian hết hạn vào database (5 phút)
        expires_at = (datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")) + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE recharge_orders SET expires_at = ? WHERE order_code = ?", (expires_at, order_code))
        conn.commit()
        
        # Tạo caption với đầy đủ tiếng Việt và tiếng Anh
        if lang == 'vi':
            caption = (
                f"🧾 Quét QR để thanh toán và mua sản phẩm\n"
                f"🛍️ Sản phẩm: <b>{name}</b>\n"
                f"🔢 Số lượng: <b>{qty}</b>\n"
                f"💰 Số tiền: <code>{amount_vnd:,} VND</code>\n"
                f"💵 Quy đổi: <code>{amount_usdt:.4f} USDT</code>\n"
                f"🆔 Mã đơn: <code>{order_code}</code>\n"
                f"⏰ {get_text(id_user, 'sepay.qr_expires')} <b>5 phút</b>\n\n"
                f"⚠️ Vui lòng chuyển đúng số tiền. Sau khi thanh toán, đơn hàng sẽ được tự động tạo.\n"
                f"⏳ {get_text(id_user, 'sepay.auto_cancel_note')}"
            )
        else:
            caption = (
                f"🧾 Scan QR to pay and purchase product\n"
                f"🛍️ Product: <b>{name}</b>\n"
                f"🔢 Quantity: <b>{qty}</b>\n"
                f"💰 Amount: <code>{amount_vnd:,} VND</code>\n"
                f"💵 Converted: <code>{amount_usdt:.4f} USDT</code>\n"
                f"🆔 Order code: <code>{order_code}</code>\n"
                f"⏰ {get_text(id_user, 'sepay.qr_expires')} <b>5 minutes</b>\n\n"
                f"⚠️ Please transfer the exact amount. After payment, the order will be automatically created.\n"
                f"⏳ {get_text(id_user, 'sepay.auto_cancel_note')}"
            )
        
        # Ban đầu chỉ hiển thị 2 nút: "I have paid" và "Cancel"
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(get_text(id_user, 'sepay.confirm_button'), callback_data=f"sepay_confirm:{order_code}"),
                InlineKeyboardButton(get_text(id_user, 'sepay.cancel_button'), callback_data=f"sepay_cancel:{order_code}")
            ]
        ])

        await q.edit_message_text(get_text(id_user, 'sepay.qr_generating'), parse_mode="HTML")
        await context.bot.send_photo(
            chat_id=id_user,
            photo=qr_url,
            caption=caption,
            reply_markup=buttons,
            parse_mode="HTML"
        )
        context.user_data["active_flow"] = "sepay_pending"
        context.user_data["sepay_order_code"] = order_code

    except Exception as e:
        logger.exception(f"[BUY DIRECT] ERROR: {e}")
        await q.edit_message_text(get_text(id_user, 'error.generic'), reply_markup=buttons, parse_mode="Markdown")
    finally:
        cursor.close()
        conn.close()

async def handle_back_to_listproducts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back button to return to list products"""
    q = update.callback_query
    if not q:
        return
    await q.answer()

    caller_id = q.from_user.id
    
    # Clear active flow khi quay về list
    clear_active_flow(context)

    conn = db_connect()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT 1 FROM users WHERE is_blocked=1 AND id_user=?", (caller_id,))
        if cursor.fetchone():
            buttom = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
            ])
            await q.edit_message_text(get_text(caller_id, 'common.blocked'), reply_markup=buttom, parse_mode="Markdown")
            return

        cursor.execute("SELECT id_product, name, price FROM listproducts ORDER BY id_product")
        rows = cursor.fetchall()
        if not rows:
            buttom = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
            ])
            await q.edit_message_text(get_text(caller_id, 'products.not_found'), reply_markup=buttom, parse_mode="Markdown")
            return

        buttons = [[InlineKeyboardButton(text=f"{name} — {price}$", callback_data=f"prod:{pid}")]
                   for (pid, name, price) in rows]
        
        buttons.append([InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")])
        await q.edit_message_text(get_text(caller_id, 'products.title') + ":", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

    except Exception as e:
        logger.exception("ERROR back to listproducts: %s", e)
        buttom = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
        ])
        await q.edit_message_text(get_text(caller_id, 'error.generic'), reply_markup=buttom, parse_mode="Markdown")
    finally:
        cursor.close()
        conn.close()

async def handler_back_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q: 
        return
    await q.answer()

    data = q.data
    if not data.startswith("back:"):
        return
    
    parts = data.split(":")
    if len(parts) < 2:
        buttom = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
        ])
        await q.edit_message_text(get_text(caller_id, 'error.generic'), reply_markup=buttom, parse_mode="Markdown")
    
    caller_id = q.from_user.id

    conn = db_connect()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT 1 FROM users WHERE is_blocked=1 AND id_user=?", (caller_id,))
        if cursor.fetchone():
            buttom = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
            ])
            await q.edit_message_text(get_text(caller_id, 'common.blocked'), reply_markup=buttom, parse_mode="Markdown")
            return

        cursor.execute("SELECT id_product, name, price FROM listproducts ORDER BY id_product")
        rows = cursor.fetchall()
        if not rows:
            buttom = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
            ])
            await q.edit_message_text(get_text(caller_id, 'products.not_found'), reply_markup=buttom, parse_mode="Markdown")
            return

        buttons = [[InlineKeyboardButton(text=f"{name} — {price}$", callback_data=f"prod:{pid}")]
                   for (pid, name, price) in rows]
        
        buttons.append([InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")])
        await q.edit_message_text(get_text(caller_id, 'products.title') + ":", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

    except:
        logger.info("ERROR back")
        buttom = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
        ])
        await q.edit_message_text(get_text(caller_id, 'error.generic'), reply_markup=buttom, parse_mode="Markdown")
    finally:
        cursor.close()
        conn.close()

async def handle_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()

    caller_id = q.from_user.id

    conn = db_connect()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM users WHERE id_user = ?", (caller_id,))
        row = cursor.fetchone()

        if not row:
            logger.info("%s doesn't find information", caller_id)
            buttom = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
            ])
            await q.edit_message_text(
                get_text(caller_id, 'user_info.not_found'),
                reply_markup=buttom
            )
            return

        # Lấy thông tin user
        # Cấu trúc bảng users: id_user, user_name, balance, currency, is_subadmin, is_blocked, products_bought, language, created_at
        try:
            user_id_raw = row[0]
            username_raw = row[1] or "N/A"
            balance_raw = float(row[2] or 0)
            currency_raw = row[3] or "USDT"
            is_subadmin = bool(row[4])
            is_blocked = bool(row[5])
            bought = int(row[6] or 0)
            language = (row[7] if len(row) > 7 and row[7] is not None else 'en') or 'en'
            created = (row[8] if len(row) > 8 and row[8] is not None else "N/A") or "N/A"
        except (IndexError, ValueError, TypeError) as e:
            logger.exception(f"Error parsing user row: {e}, row length: {len(row) if row else 0}")
            raise
        
        # Tính tỷ giá và số tiền VND
        balance_vnd = int(balance_raw * EXCHANGE_RATE_VND)
        
        # Format balance (không escape để tránh lỗi thừa \)
        balance_str = f"{balance_raw:.2f}"
        currency_str = currency_raw
        
        # Lấy tên ngôn ngữ
        lang_name = "Tiếng Việt" if language == 'vi' else "English"
        
        # Format created_at (chỉ lấy phần ngày giờ, không có timezone)
        if created and created != "N/A":
            try:
                # Nếu có format datetime, chỉ lấy phần đầu (YYYY-MM-DD HH:MM:SS)
                created_display = str(created).split()[0] if ' ' in str(created) else str(created)
                # Giới hạn độ dài
                if len(created_display) > 20:
                    created_display = created_display[:20]
            except:
                created_display = str(created)[:20] if created else "N/A"
        else:
            created_display = "N/A"
        
        # Escape cho MarkdownV2 (chỉ escape các phần trong text message)
        user_id_escaped = escape_markdown(str(user_id_raw), version=2)
        username_escaped = escape_markdown(str(username_raw), version=2)
        
        # Tạo message với tỷ giá
        lang = get_user_language(caller_id)
        # Escape dấu = trong tỷ giá cho MarkdownV2
        exchange_rate_escaped = escape_markdown(f"{EXCHANGE_RATE_VND:,}", version=2)
        if lang == 'vi':
            msg = (
                f"{get_text(caller_id, 'user_info.title')}\n"
                f"• *{get_text(caller_id, 'user_info.id')}:* `{user_id_escaped}`\n"
                f"• *{get_text(caller_id, 'user_info.username')}:* `{username_escaped}`\n"
                f"• *Tỷ giá:* 1 USDT \\= {exchange_rate_escaped} VND\n"
            )
        else:
            msg = (
                f"{get_text(caller_id, 'user_info.title')}\n"
                f"• *{get_text(caller_id, 'user_info.id')}:* `{user_id_escaped}`\n"
                f"• *{get_text(caller_id, 'user_info.username')}:* `{username_escaped}`\n"
                f"• *Exchange rate:* 1 USDT \\= {exchange_rate_escaped} VND\n"
            )

        # Tạo nút - tách Created At và Language thành 2 nút riêng
        # Không escape trong button text vì button không cần markdown
        buttom = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"💰 {get_text(caller_id, 'user_info.balance')}: {balance_str} {currency_str}", callback_data="Balance:NONE"),
                InlineKeyboardButton(f"☑️ {get_text(caller_id, 'user_info.products_bought')}: {bought}", callback_data="Bought:NONE")
            ],
            [
                InlineKeyboardButton(f"Admin {'✅' if is_subadmin else '❌'}", callback_data="Admin:NONE"),
                InlineKeyboardButton(f"Blocked {'✅' if is_blocked else '❌'}", callback_data="Blocked:NONE")
            ],
            [
                InlineKeyboardButton(f"🌐 Language: {lang_name}", callback_data="Language:NONE"),
                InlineKeyboardButton(f"📅 {get_text(caller_id, 'user_info.created_at')}: {created_display}", callback_data="Join:NONE")
            ],
            [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
        ])

        await q.edit_message_text(
            text=msg,
            reply_markup=buttom,
            parse_mode="MarkdownV2"
        )

    except Exception as e:
        logger.exception("Aboutme command failed: %s", e)
        buttom = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
        ])
        await q.edit_message_text(get_text(caller_id, 'error.generic'), reply_markup=buttom)

    finally:
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass


# handle_back_dashboard
async def handle_back_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    
    await q.answer()

    caller_id = q.from_user.id

    clear_active_flow(context)

    conn = db_connect()
    cursor = conn.cursor()

    try:
        # Nếu không phải admin thì kiểm tra bị chặn hay không
        if caller_id != settings.ADMIN_ID:
            cursor.execute(
                "SELECT 1 FROM users WHERE id_user = ? AND is_blocked = 1",
                (caller_id,)
            )
            row = cursor.fetchone()
            if row:  # Nếu có kết quả -> bị chặn
                await q.edit_message_text(get_text(caller_id, 'common.blocked'))
                return

        # Sử dụng hàm chung để tạo menu dashboard - đảm bảo tính nhất quán
        buttons = create_dashboard_menu(caller_id)
        await q.edit_message_text(text=get_text(caller_id, 'dashboard.title'), reply_markup=buttons)
        return

    except Exception as e:
        buttom = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
        ])
        await q.edit_message_text(f"{get_text(caller_id, 'error.generic')} {e}", reply_markup=buttom, parse_mode="Markdown")

        return

    finally:
        cursor.close()
        conn.close()

# handle_listproduct
async def handle_listproduct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return 
    
    await q.answer()

    caller_id = q.from_user.id

    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM users WHERE is_blocked=1 AND id_user=?", (caller_id,))
        if cursor.fetchone():
            buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
        ])
            await q.edit_message_text(get_text(caller_id, 'common.blocked'), reply_markup= buttons)
            return

        cursor.execute("SELECT id_product, name, price FROM listproducts ORDER BY id_product")
        rows = cursor.fetchall()
        if not rows:
            buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
        ])
            await q.edit_message_text(get_text(caller_id, 'products.not_found'), reply_markup=buttons)
            return

        buttons = [[InlineKeyboardButton(text=f"{name} — {price}$", callback_data=f"prod:{pid}")]
                   for (pid, name, price) in rows]
        
        buttons.append([InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")])

        await q.edit_message_text(get_text(caller_id, 'products.title') + ":", reply_markup=InlineKeyboardMarkup(buttons))
    
    except Exception as e:
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
        ])
        await q.edit_message_text(f"{get_text(caller_id, 'error.generic')} {e}", reply_markup= buttons)

    finally:
        cursor.close()
        conn.close()

# handle_support
async def handle_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query

    if not q:
        return
    user_id = q.from_user.id
    
    await q.answer()

    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id_user = ? and is_blocked = 1", (user_id,))
    data = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if data:
        logger.info(f"{user_id} is blocked but using /start")
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(user_id, 'common.back'), callback_data="back_dashboard:NONE")]
        ])
        await q.edit_message_text(get_text(user_id, 'common.blocked'), reply_markup= buttons)
        return

    admin_username = (settings.USER_NAME and settings.USER_NAME.strip()) or get_text(user_id, 'common.admin')
    text_msg = f"""
{get_text(user_id, 'support.contact')} <b>{admin_username}</b>
{get_text(user_id, 'support.help_command')}
"""

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(user_id, 'common.back'), callback_data="back_dashboard:NONE")]
    ])
    await q.edit_message_text(text=text_msg, reply_markup= buttons, parse_mode="HTML")
    logger.info(f"Displayed help command to user ID={q.from_user.id}")
    return

async def handle_add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    if get_active_flow(context):
        await notify_flow_busy(update, context)
        return

    caller_id = q.from_user.id
    await q.answer()

    conn = db_connect()
    cursor = conn.cursor()

    try:
        # chặn user bị block (trừ admin)
        if caller_id != settings.ADMIN_ID:
            cursor.execute("SELECT 1 FROM users WHERE is_blocked = 1 AND id_user = ?", (caller_id,))
            if cursor.fetchone():
                logger.info(f"{caller_id} is blocked")
                buttons = InlineKeyboardMarkup([
                    [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
                ])
                await q.edit_message_text(text=get_text(caller_id, 'common.blocked'), reply_markup=buttons)
                return

        text = f"💰 **{get_text(caller_id, 'payment.title')}**\n"
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(caller_id, 'payment.crypto'), callback_data="crypto_recharge:NONE")],
            [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")],
        ])

        logger.info(f"{caller_id} used add balance")
        await q.edit_message_text(text=text, reply_markup=buttons, parse_mode="Markdown")

    except Exception as e:
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="back_dashboard:NONE")]
        ])
        logger.info(f"Add balance fail {caller_id}, {e}")
        await q.edit_message_text(text="❌ ERROR.", reply_markup=buttons, parse_mode="Markdown")

    finally:
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass

async def handle_sepay_recharge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    if get_active_flow(context) not in (None, "sepay_amount", "sepay_pending"):
        await notify_flow_busy(update, context)
        return

    caller_id = q.from_user.id
    await q.answer()

    conn = db_connect()
    cursor = conn.cursor()
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="go_payment_info:NONE")]
    ])

    try:
        if caller_id != settings.ADMIN_ID:
            cursor.execute("SELECT 1 FROM users WHERE is_blocked = 1 AND id_user = ?", (caller_id,))
            if cursor.fetchone():
                await q.edit_message_text(get_text(caller_id, 'common.blocked'), reply_markup=buttons)
                return

        clear_active_flow(context)
        context.user_data["active_flow"] = "sepay_amount"
        context.user_data["awaiting_sepay_amount"] = True
        await q.edit_message_text(
            text=get_text(caller_id, 'sepay.prompt_amount'),
            reply_markup=buttons,
            parse_mode="HTML"
        )

    except Exception as e:
        logger.exception("handle_sepay_recharge failed: %s", e)
        await q.edit_message_text(get_text(caller_id, 'error.generic'), reply_markup=buttons)

    finally:
        cursor.close()
        conn.close()


async def handle_sepay_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if context.user_data.get("stock_add_pending"):
        await handle_stock_add_input(update, context)
        return

    if context.user_data.get("awaiting_crypto_txid"):
        await handle_crypto_txid_input(update, context)
        return

    if context.user_data.get("awaiting_product_description"):
        await handle_product_description_input(update, context)
        return

    if not context.user_data.get("awaiting_sepay_amount"):
        return

    caller_id = update.message.from_user.id
    text = (update.message.text or "").strip().replace(",", "")

    if not text.isdigit():
        await update.message.reply_text(get_text(caller_id, 'sepay.invalid_amount'))
        return

    amount_vnd = int(text)
    if amount_vnd < 2000:
        await update.message.reply_text(get_text(caller_id, 'sepay.min_amount'))
        return

    bank_acc = str(getattr(settings, "VN_BANK_ACCOUNT", "") or "").strip()
    bank_code = str(getattr(settings, "VN_BANK_CODE", "") or "").strip()
    bank_name = str(getattr(settings, "VN_BANK_NAME", "") or "").strip()
    bank_param = bank_code or bank_name

    if not bank_acc or not bank_param:
        await update.message.reply_text(get_text(caller_id, 'sepay.not_configured'))
        context.user_data.pop("awaiting_sepay_amount", None)
        return

    amount_usdt = round(amount_vnd / EXCHANGE_RATE_VND, 4)

    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM users WHERE id_user = ? AND is_blocked = 1", (caller_id,))
        if cursor.fetchone():
            await update.message.reply_text(get_text(caller_id, 'common.blocked'))
            return

        cursor.execute("SELECT balance FROM users WHERE id_user = ?", (caller_id,))
        balance_row = cursor.fetchone()
        current_balance = balance_row[0] if balance_row else 0

        order_code = f"SP{caller_id}{int(time.time())}"
        while True:
            cursor.execute("SELECT 1 FROM recharge_orders WHERE order_code = ?", (order_code,))
            if cursor.fetchone():
                order_code = f"SP{caller_id}{int(time.time())}{random.randint(10,99)}"
            else:
                break

        # Thêm thời gian hết hạn vào database (5 phút)
        expires_at = (datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")) + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO recharge_orders (order_code, id_user, amount_vnd, amount_usdt, status, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
            (order_code, caller_id, amount_vnd, amount_usdt, "PENDING", expires_at)
        )
        conn.commit()

        description = urllib.parse.quote(order_code)
        bank_param_safe = urllib.parse.quote(bank_param)
        qr_url = f"https://qr.sepay.vn/img?acc={bank_acc}&bank={bank_param_safe}&amount={amount_vnd}&des={description}"

        # Tạo caption với đầy đủ tiếng Việt và tiếng Anh
        lang = get_user_language(caller_id)
        if lang == 'vi':
            caption = (
                f"{get_text(caller_id, 'sepay.qr_title')}\n"
                f"{get_text(caller_id, 'sepay.amount_vnd')}: <code>{amount_vnd:,} VND</code>\n"
                f"{get_text(caller_id, 'sepay.amount_usdt')}: <code>{amount_usdt:.4f} USDT</code>\n"
                f"{get_text(caller_id, 'sepay.order_code')}: <code>{order_code}</code>\n"
                f"⏰ {get_text(caller_id, 'sepay.qr_expires')} <b>5 phút</b>\n\n"
                f"{get_text(caller_id, 'sepay.scan_note')}\n"
                f"⏳ {get_text(caller_id, 'sepay.auto_cancel_note')}"
            )
        else:
            caption = (
                f"{get_text(caller_id, 'sepay.qr_title')}\n"
                f"{get_text(caller_id, 'sepay.amount_vnd')}: <code>{amount_vnd:,} VND</code>\n"
                f"{get_text(caller_id, 'sepay.amount_usdt')}: <code>{amount_usdt:.4f} USDT</code>\n"
                f"{get_text(caller_id, 'sepay.order_code')}: <code>{order_code}</code>\n"
                f"⏰ {get_text(caller_id, 'sepay.qr_expires')} <b>5 minutes</b>\n\n"
                f"{get_text(caller_id, 'sepay.scan_note')}\n"
                f"⏳ {get_text(caller_id, 'sepay.auto_cancel_note')}"
            )

        # Ban đầu chỉ hiển thị 2 nút: "I have paid" và "Cancel"
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(get_text(caller_id, 'sepay.confirm_button'), callback_data=f"sepay_confirm:{order_code}"),
                InlineKeyboardButton(get_text(caller_id, 'sepay.cancel_button'), callback_data=f"sepay_cancel:{order_code}")
            ]
        ])

        try:
            r = httpx.get(qr_url, timeout=20, follow_redirects=True)
            r.raise_for_status()

            ct = (r.headers.get("content-type") or "").lower()
            if not ct.startswith("image/"):
                # log để biết qr_url đang trả gì (HTML/JSON)
                raise ValueError(f"QR URL is not an image. content-type={ct}, url={qr_url}")

            bio = BytesIO(r.content)
            bio.name = "qr.png"   # quan trọng: telegram cần filename
            bio.seek(0)


            text = (
                f"{caption}\n\n"
                f"🔗 <b>QR link</b> (open to scan):\n"
                f"{qr_url}\n\n"
                f"✅ {get_text(caller_id,'sepay.scan_note')}"
            )

            await update.message.reply_text(
                text=text,
                reply_markup=buttons,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )


        except Exception as e:
            # fallback: nếu ảnh lỗi thì gửi text + link
            await update.message.reply_text(
                f"❌ ERROR: {e}\n\nQR URL: {qr_url}",
                parse_mode="HTML"
            )
            raise	

        await update.message.reply_photo(
            photo=qr_url,
            caption=caption,
            reply_markup=buttons,
            parse_mode="HTML"
        )

        context.user_data["active_flow"] = "sepay_pending"

        admin_recharge_new = get_text(
            caller_id,
            "admin.recharge_new",
            buyer_id=caller_id,
            order_code=order_code,
            amount=amount_vnd,
            current_balance=current_balance,
        )
        await context.bot.send_message(chat_id=settings.ADMIN_ID, text=admin_recharge_new)

    except Exception as e:
        logger.exception("handle_sepay_amount_input failed: %s", e)
        await update.message.reply_text(get_text(caller_id, 'error.generic'))
    finally:
        context.user_data.pop("awaiting_sepay_amount", None)
        cursor.close()
        conn.close()


def _extract_amount_currency(tx: dict):
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


def _extract_tx_time_ms(tx: dict):
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


async def skip_product_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /skip command to skip product description"""
    if not update.message:
        return
    
    caller_id = update.message.from_user.id
    
    # Chỉ xử lý nếu đang trong flow product_description
    if not context.user_data.get("awaiting_product_description"):
        await update.message.reply_text("ℹ️ Không có mô tả sản phẩm nào đang chờ xử lý.")
        return
    
    # Kiểm tra xem có phải admin/subadmin không
    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM subadmins WHERE id_user = ?", (caller_id,))
        row = cursor.fetchone()
        is_admin = (caller_id == settings.ADMIN_ID) or row
        
        if not is_admin:
            await update.message.reply_text("❌ Bạn không có quyền thực hiện lệnh này.")
            context.user_data.pop("awaiting_product_description", None)
            context.user_data.pop("product_description_id", None)
            clear_active_flow(context)
            return
        
        product_id = context.user_data.get("product_description_id")
        if not product_id:
            await update.message.reply_text("❌ Không tìm thấy thông tin sản phẩm.")
            context.user_data.pop("awaiting_product_description", None)
            clear_active_flow(context)
            return
        
        # Bỏ qua mô tả
        context.user_data.pop("awaiting_product_description", None)
        context.user_data.pop("product_description_id", None)
        clear_active_flow(context)
        
        await update.message.reply_text(get_text(caller_id, 'products.description_skipped'))
        await context.bot.send_message(text=f"✅ ID:`{caller_id}` Product description skipped (ID: {product_id})", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        
    except Exception as e:
        logger.exception("skip_product_description failed: %s", e)
        await update.message.reply_text(f"❌ Lỗi khi bỏ qua mô tả: {e}")
        context.user_data.pop("awaiting_product_description", None)
        context.user_data.pop("product_description_id", None)
        clear_active_flow(context)
    finally:
        cursor.close()
        conn.close()


async def handle_product_description_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle product description input after adding product"""
    if not update.message:
        return
    
    caller_id = update.message.from_user.id
    text = (update.message.text or "").strip()
    
    # Kiểm tra xem có phải admin/subadmin không
    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM subadmins WHERE id_user = ?", (caller_id,))
        row = cursor.fetchone()
        is_admin = (caller_id == settings.ADMIN_ID) or row
        
        if not is_admin:
            context.user_data.pop("awaiting_product_description", None)
            context.user_data.pop("product_description_id", None)
            clear_active_flow(context)
            return
        
        product_id = context.user_data.get("product_description_id")
        if not product_id:
            context.user_data.pop("awaiting_product_description", None)
            clear_active_flow(context)
            return
        
        # Cập nhật mô tả vào database
        if text:
            cursor.execute("UPDATE listproducts SET descrip = ? WHERE id_product = ?", (text, product_id))
            conn.commit()
            await update.message.reply_text(get_text(caller_id, 'products.description_added'))
            await context.bot.send_message(text=f"✅ ID:`{caller_id}` Product description added (ID: {product_id})", chat_id=settings.ADMIN_ID, parse_mode="Markdown")
        else:
            # Nếu text rỗng, bỏ qua
            await update.message.reply_text(get_text(caller_id, 'products.description_skipped'))
        
        # Clear flow
        context.user_data.pop("awaiting_product_description", None)
        context.user_data.pop("product_description_id", None)
        clear_active_flow(context)
        
    except Exception as e:
        logger.exception("handle_product_description_input failed: %s", e)
        await update.message.reply_text(f"❌ Lỗi khi thêm mô tả: {e}")
        context.user_data.pop("awaiting_product_description", None)
        context.user_data.pop("product_description_id", None)
        clear_active_flow(context)
    finally:
        cursor.close()
        conn.close()


async def handle_crypto_txid_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    if not context.user_data.get("awaiting_crypto_txid"):
        return

    caller_id = update.message.from_user.id
    code = (update.message.text or "").strip()
    if not code:
        await update.message.reply_text(get_text(caller_id, 'crypto.txid_prompt'))
        return

    is_txid = len(code) >= 60 and all(c in "0123456789abcdefABCDEFx" for c in code)
    window_end = int(time.time() * 1000)
    window_start = window_end - (CRYPTO_LOOKBACK_HOURS * 3600 * 1000)

    tx_id = None
    amount = 0.0
    currency = "USDT"
    tx_time_ms = 0

    try:
        if is_txid:
            deposit = await asyncio.to_thread(check_deposit_by_txid, code)
            if deposit and deposit.get("confirmed"):
                tx_id = code
                amount = float(deposit.get("amount", 0))
                currency = str(deposit.get("currency", "USDT")).upper()
                tx_time_ms = int(deposit.get("timestamp", window_end))
        else:
            tx = await asyncio.to_thread(
                find_pay_transaction_by_id,
                code,
                start_time_ms=window_start,
                end_time_ms=window_end,
            )
            if tx:
                tx_id = str(tx.get("transactionId") or tx.get("orderId") or tx.get("bizId") or code)
                amount, currency = _extract_amount_currency(tx)
                tx_time_ms = _extract_tx_time_ms(tx)
    except Exception as e:
        logger.exception("handle_crypto_txid_input failed: %s", e)

    if not tx_id or amount <= 0:
        await update.message.reply_text(get_text(caller_id, 'crypto.not_found'))
        return

    if window_end - int(tx_time_ms) > (CRYPTO_LOOKBACK_HOURS * 3600 * 1000):
        await update.message.reply_text(get_text(caller_id, 'crypto.too_old'))
        return

    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM recharge_history WHERE txid = ?", (tx_id,))
        if cursor.fetchone():
            await update.message.reply_text(get_text(caller_id, 'crypto.duplicate'))
            return

        amount_usdt = float(amount)
        cursor.execute("UPDATE users SET balance = balance + ? WHERE id_user = ?", (amount_usdt, caller_id))
        cursor.execute(
            "INSERT INTO recharge_history (id_user, amount, method, status, txid) VALUES (?, ?, ?, ?, ?)",
            (caller_id, amount_usdt, "binance", "SUCCESS", tx_id),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    context.user_data.pop("awaiting_crypto_txid", None)
    clear_active_flow(context)
    
    await context.bot.send_message(
        chat_id=settings.ADMIN_ID,
        text=f"✅ ID:{caller_id} Crypto recharge successful: {amount_usdt} {currency}, txid: {tx_id}"
    )
    await update.message.reply_text(
        get_text(caller_id, 'crypto.confirmed').format(amount=amount_usdt, currency=currency)
    )


async def handle_sepay_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()

    caller_id = q.from_user.id
    data = q.data or ""
    if not data.startswith("sepay_confirm:"):
        return
    order_code = data.split(":", 1)[1].strip()

    conn = db_connect()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT 1 FROM recharge_orders WHERE order_code = ? AND id_user = ?",
            (order_code, caller_id)
        )
        if not cursor.fetchone():
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
            ])
            await q.edit_message_text(get_text(caller_id, 'sepay.not_found'), reply_markup=buttons)
            return

        # Sau khi nhấn "I have paid", cập nhật để hiển thị "Check again" và "Cancel order"
        lang = get_user_language(caller_id)
        if lang == 'vi':
            confirmed_caption = (
                f"✅ **Đã ghi nhận thanh toán**\n"
                f"🆔 Mã đơn: `{order_code}`\n\n"
                f"⏳ Hệ thống sẽ tự động cộng tiền sau khi ngân hàng xác nhận.\n"
                f"💡 Bạn có thể kiểm tra lại trạng thái đơn hàng bất cứ lúc nào."
            )
        else:
            confirmed_caption = (
                f"✅ **Payment Marked**\n"
                f"🆔 Order code: `{order_code}`\n\n"
                f"⏳ The system will auto-credit after the bank confirms.\n"
                f"💡 You can check the order status anytime."
            )
        
        # Cập nhật nút: hiển thị "Check again" và "Cancel order"
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(get_text(caller_id, 'sepay.check_button'), callback_data=f"sepay_check:{order_code}"),
                InlineKeyboardButton(get_text(caller_id, 'sepay.cancel_order_button'), callback_data=f"sepay_cancel:{order_code}")
            ]
        ])

        try:
            await q.edit_message_caption(
                caption=confirmed_caption,
                reply_markup=buttons,
                parse_mode="Markdown"
            )
        except:
            # Nếu không phải photo message, dùng edit_message_text
            await q.edit_message_text(confirmed_caption, reply_markup=buttons, parse_mode="Markdown")
        
        # Không clear flow ngay, để user có thể check lại hoặc cancel
    except Exception as e:
        logger.exception("handle_sepay_confirm failed: %s", e)
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
        ])
        await q.edit_message_text(get_text(caller_id, 'error.generic'), reply_markup=buttons)
    finally:
        cursor.close()
        conn.close()


# Handler kiểm tra trạng thái đơn hàng
async def handle_sepay_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()
    
    id_user = q.from_user.id
    data = q.data or ""
    if not data.startswith("sepay_check:"):
        return
    
    try:
        order_code = data.split(":", 1)[1].strip()
    except (ValueError, IndexError):
        await q.edit_message_text("❌ Invalid order code")
        return
    
    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT status, created_at, expires_at, amount_vnd, amount_usdt, product_name, product_qty FROM recharge_orders WHERE order_code = ? AND id_user = ?",
            (order_code, id_user)
        )
        row = cursor.fetchone()
        
        if not row:
            await q.answer("❌ Không tìm thấy đơn hàng", show_alert=True)
            return
        
        status, created_at, expires_at, amount_vnd, amount_usdt, product_name, product_qty = row
        lang = get_user_language(id_user)
        
        # Kiểm tra thời gian hết hạn
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
        
        if expires_at:
            expires_dt = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
            expires_dt = expires_dt.replace(tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
            time_left = expires_dt - now
            minutes_left = int(time_left.total_seconds() / 60)
            seconds_left = int(time_left.total_seconds() % 60)
        else:
            minutes_left = 0
            seconds_left = 0
        
        if lang == 'vi':
            if status == "SUCCESS":
                status_text = "✅ Đã thanh toán thành công"
                status_emoji = "✅"
            elif status == "CANCELLED":
                status_text = "❌ Đơn hàng đã bị hủy"
                status_emoji = "❌"
            elif minutes_left <= 0:
                status_text = "⏰ Đơn hàng đã hết hạn"
                status_emoji = "⏰"
            else:
                status_text = f"⏳ Đang chờ thanh toán (còn {minutes_left} phút {seconds_left} giây)"
                status_emoji = "⏳"
            
            message = (
                f"{status_emoji} **Tình trạng đơn hàng**\n"
                f"🆔 Mã đơn: `{order_code}`\n"
                f"📊 Trạng thái: {status_text}\n"
                f"💰 Số tiền: {amount_vnd:,} VND ({amount_usdt:.4f} USDT)\n"
            )
            if product_name:
                message += f"🛍️ Sản phẩm: {product_name}\n"
                message += f"🔢 Số lượng: {product_qty}\n"
            if expires_at and minutes_left > 0:
                message += f"⏰ Hết hạn sau: {minutes_left} phút {seconds_left} giây\n"
            elif expires_at and minutes_left <= 0:
                message += f"⏰ Đã hết hạn\n"
        else:
            if status == "SUCCESS":
                status_text = "✅ Payment successful"
                status_emoji = "✅"
            elif status == "CANCELLED":
                status_text = "❌ Order cancelled"
                status_emoji = "❌"
            elif minutes_left <= 0:
                status_text = "⏰ Order expired"
                status_emoji = "⏰"
            else:
                status_text = f"⏳ Pending payment ({minutes_left}m {seconds_left}s left)"
                status_emoji = "⏳"
            
            message = (
                f"{status_emoji} **Order Status**\n"
                f"🆔 Order code: `{order_code}`\n"
                f"📊 Status: {status_text}\n"
                f"💰 Amount: {amount_vnd:,} VND ({amount_usdt:.4f} USDT)\n"
            )
            if product_name:
                message += f"🛍️ Product: {product_name}\n"
                message += f"🔢 Quantity: {product_qty}\n"
            if expires_at and minutes_left > 0:
                message += f"⏰ Expires in: {minutes_left} minutes {seconds_left} seconds\n"
            elif expires_at and minutes_left <= 0:
                message += f"⏰ Expired\n"
        
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(id_user, 'sepay.check_button'), callback_data=f"sepay_check:{order_code}")]
        ])
        
        await q.edit_message_text(message, reply_markup=buttons, parse_mode="Markdown")
        
    except Exception as e:
        logger.exception(f"Error in handle_sepay_check: {e}")
        lang = get_user_language(id_user)
        if lang == 'vi':
            await q.answer("❌ Lỗi khi kiểm tra đơn hàng", show_alert=True)
        else:
            await q.answer("❌ Error checking order", show_alert=True)
    finally:
        cursor.close()
        conn.close()


async def handle_sepay_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hủy đơn hàng SePay"""
    q = update.callback_query
    if not q:
        return
    await q.answer()

    caller_id = q.from_user.id
    data = q.data or ""
    if not data.startswith("sepay_cancel:"):
        return

    try:
        order_code = data.split(":", 1)[1].strip()
    except (ValueError, IndexError):
        await q.answer("❌ Invalid order code", show_alert=True)
        return

    conn = db_connect()
    cursor = conn.cursor()
    try:
        # Kiểm tra đơn hàng có tồn tại và thuộc về user không
        cursor.execute(
            "SELECT status, product_id, amount_usdt FROM recharge_orders WHERE order_code = ? AND id_user = ?",
            (order_code, caller_id)
        )
        row = cursor.fetchone()
        
        if not row:
            lang = get_user_language(caller_id)
            if lang == 'vi':
                await q.answer("❌ Không tìm thấy đơn hàng", show_alert=True)
            else:
                await q.answer("❌ Order not found", show_alert=True)
            return
        
        status, product_id, amount_usdt = row
        
        # Nếu đã thanh toán hoặc đã hủy, không cho hủy lại
        if status == "SUCCESS":
            lang = get_user_language(caller_id)
            if lang == 'vi':
                await q.answer("❌ Đơn hàng đã thanh toán, không thể hủy", show_alert=True)
            else:
                await q.answer("❌ Order already paid, cannot cancel", show_alert=True)
            return
        elif status == "CANCELLED":
            lang = get_user_language(caller_id)
            if lang == 'vi':
                await q.answer("❌ Đơn hàng đã bị hủy", show_alert=True)
            else:
                await q.answer("❌ Order already cancelled", show_alert=True)
            return
        
        # Nếu là đơn mua sản phẩm (có product_id), hoàn tiền
        if product_id:
            cursor.execute("UPDATE users SET balance = balance + ? WHERE id_user = ?", (amount_usdt, caller_id))
        
        # Cập nhật trạng thái đơn hàng thành CANCELLED
        cursor.execute(
            "UPDATE recharge_orders SET status = 'CANCELLED' WHERE order_code = ? AND id_user = ?",
            (order_code, caller_id)
        )
        conn.commit()
        
        lang = get_user_language(caller_id)
        if lang == 'vi':
            cancel_msg = f"❌ Đã hủy đơn hàng {order_code}"
            if product_id:
                cancel_msg += f"\n💵 Tiền đã được hoàn lại vào ví."
        else:
            cancel_msg = f"❌ Order {order_code} cancelled"
            if product_id:
                cancel_msg += f"\n💵 Money has been refunded to wallet."
        
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
        ])
        
        try:
            await q.edit_message_caption(
                caption=cancel_msg,
                reply_markup=buttons,
                parse_mode="Markdown"
            )
        except:
            await q.edit_message_text(cancel_msg, reply_markup=buttons, parse_mode="Markdown")
        
        clear_active_flow(context)
        logger.info(f"Order {order_code} cancelled by user {caller_id}")
        
    except Exception as e:
        logger.exception("handle_sepay_cancel failed: %s", e)
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
        ])
        await q.edit_message_text(get_text(caller_id, 'error.generic'), reply_markup=buttons)
    finally:
        cursor.close()
        conn.close()


# handle_orders
async def handle_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return 
    
    await q.answer()

    caller_id = q.from_user.id

    conn = db_connect()
    cursor = conn.cursor()

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
    ])

    try:
        # xu ly neu nguoi dung dang bi chan hoac chua nhan nut start
        cursor.execute("SELECT * FROM users WHERE is_blocked =1 AND id_user = ?", (caller_id,))
        if caller_id != settings.ADMIN_ID:
            if cursor.fetchone():
                logger.info(f"{caller_id} is blocked")
                await q.edit_message_text(text=get_text(caller_id, 'common.blocked'), reply_markup=buttons)
                return
        
        # Thông báo đang xuất
        await q.edit_message_text(get_text(caller_id, 'orders.exporting'), reply_markup=buttons, parse_mode="Markdown")
        
        # Lấy tất cả đơn hàng chưa xuất
        cursor.execute(
            "SELECT id_order, id_buyer, name, price, quality, status, created_at FROM orders WHERE id_buyer = ? AND (is_exported = 0 OR is_exported IS NULL)",
            (caller_id,)
        )
        rows = cursor.fetchall()

        if not rows:
            logger.info("No orders to export in DB")
            await q.edit_message_text(get_text(caller_id, 'orders.empty'), reply_markup=buttons, parse_mode="Markdown")
            return
        
        # Gửi từng đơn hàng trong tin nhắn riêng biệt
        exported_count = 0
        for idx, row in enumerate(rows, 1):
            id_order   = html.escape(str(row[0]))
            id_buyer   = html.escape(str(row[1]))
            name       = html.escape(str(row[2]))
            price      = float(row[3])
            quality    = int(row[4])
            status     = html.escape(str(row[5] or "Pending"))
            created_at = html.escape(str(row[6]))
            
            # Tính total
            total = price * quality
            # Format total với dấu phẩy nếu là số lớn
            total_str = f"{total:,.0f}$" if total >= 1000 else f"{total}$"
            
            # Format created_at nếu cần
            try:
                dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                created_formatted = dt.strftime("%d/%m/%Y %H:%M:%S")
            except:
                created_formatted = created_at

            text = (
                f"📦 <b>ORDER</b>\n"
                f"🆔 OrderID: <code>{id_order}</code>\n"
                f"📊 Quantity: {quality}\n"
                f"💵 Total: {total_str}\n"
                f"📄 Status: {status}\n"
                f"📦 Product: {name}\n"
                f"🕐 Created: {created_formatted}"
            )
            try:
                await context.bot.send_message(chat_id=caller_id, text=text, parse_mode=ParseMode.HTML)
                # Đánh dấu đã xuất
                cursor.execute("UPDATE orders SET is_exported = 1 WHERE id_order = ?", (id_order,))
                exported_count += 1
            except Exception as e:
                logger.error(f"Error sending order {id_order} to user {caller_id}: {e}")
        
        # Commit tất cả các thay đổi
        conn.commit()
        
        # Thông báo đã xuất xong
        if exported_count > 0:
            await context.bot.send_message(
                chat_id=caller_id,
                text=get_text(caller_id, 'orders.exported'),
                parse_mode="Markdown"
            )

    except Exception as e:
        logger.error(f"Error in handle_orders for user {caller_id}: {e}")
        await q.edit_message_text(text=get_text(caller_id, 'error.generic'), reply_markup=buttons, parse_mode="Markdown")
        return
    

    finally:
        cursor.close()
        conn.close()

async def handle_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    await q.answer()
    caller_id = q.from_user.id

    conn = db_connect()
    cursor = conn.cursor()

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
    ])

    try:
        if caller_id != settings.ADMIN_ID:
            cursor.execute("SELECT 1 FROM users WHERE is_blocked = 1 AND id_user = ?", (caller_id,))
            if cursor.fetchone():
                await q.edit_message_text(get_text(caller_id, 'common.blocked'), reply_markup=buttons)
                return

        cursor.execute("SELECT currency FROM users WHERE id_user = ?", (caller_id,))
        row = cursor.fetchone()
        currency = html.escape(str(row[0])) if row and row[0] else "USDT"

        # Thông báo đang xuất
        await q.edit_message_text(get_text(caller_id, 'actions.exporting'), reply_markup=buttons, parse_mode="HTML")

        # Lấy tất cả lịch sử nạp tiền chưa xuất
        cursor.execute(
            "SELECT id, amount, method, status, txid, created_at FROM recharge_history "
            "WHERE id_user = ? AND (is_exported = 0 OR is_exported IS NULL) ORDER BY created_at DESC",
            (caller_id,)
        )
        rows = cursor.fetchall()

        if not rows:
            await q.edit_message_text(get_text(caller_id, 'actions.empty'), reply_markup=buttons)
            return

        # Gửi từng lịch sử nạp tiền trong tin nhắn riêng biệt
        exported_count = 0
        for idx, row in enumerate(rows, 1):
            history_id = row[0]
            amount = float(row[1])
            method = html.escape(str(row[2] or "-"))
            status = html.escape(str(row[3] or "-"))
            txid = html.escape(str(row[4] or "-"))
            created_at = html.escape(str(row[5] or "-"))
            
            # Format amount với dấu phẩy nếu là số lớn
            amount_str = f"{amount:,.0f} {currency}" if amount >= 1000 else f"{amount} {currency}"
            
            # Format created_at nếu cần
            try:
                dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                created_formatted = dt.strftime("%d/%m/%Y %H:%M:%S")
            except:
                created_formatted = created_at

            text = (
                f"📜 <b>RECHARGE</b>\n"
                f"🆔 RechargeID: <code>{history_id}</code>\n"
                f"💵 Amount: {amount_str}\n"
                f"📋 Method: {method}\n"
                f"📄 Status: {status}\n"
                f"🔗 TxID: <code>{txid}</code>\n"
                f"🕐 Created: {created_formatted}"
            )
            try:
                await context.bot.send_message(chat_id=caller_id, text=text, parse_mode=ParseMode.HTML)
                # Đánh dấu đã xuất
                cursor.execute("UPDATE recharge_history SET is_exported = 1 WHERE id = ?", (history_id,))
                exported_count += 1
            except Exception as e:
                logger.error(f"Error sending recharge history {history_id} to user {caller_id}: {e}")
        
        # Commit tất cả các thay đổi
        conn.commit()
        
        # Thông báo đã xuất xong
        if exported_count > 0:
            await context.bot.send_message(
                chat_id=caller_id,
                text=get_text(caller_id, 'actions.exported'),
                parse_mode="HTML"
            )

    except Exception as e:
        logger.exception("handle_actions failed: %s", e)
        await q.edit_message_text(get_text(caller_id, 'error.generic'), reply_markup=buttons)

    finally:
        cursor.close()
        conn.close()


async def handle_analytics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()

    caller_id = q.from_user.id
    conn = db_connect()
    cursor = conn.cursor()
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="back_dashboard:NONE")]
    ])

    try:
        cursor.execute("SELECT 1 FROM users WHERE is_blocked=1 AND id_user=?", (caller_id,))
        if cursor.fetchone():
            await q.edit_message_text(get_text(caller_id, 'common.blocked'), reply_markup=buttons)
            return

        cursor.execute(
            "SELECT name, SUM(quality) FROM orders "
            "WHERE id_buyer = ? AND status = 'DONE' GROUP BY name",
            (caller_id,),
        )
        product_rows = cursor.fetchall()
        products_lines = [get_text(caller_id, 'analytics.products_title')]
        if product_rows:
            for name, qty in product_rows:
                products_lines.append(f"- {html.escape(str(name))}: {int(qty or 0)}")
        else:
            products_lines.append("-")

        cursor.execute(
            "SELECT SUM(price * quality) FROM orders WHERE id_buyer = ? AND status = 'DONE'",
            (caller_id,),
        )
        total_spent = cursor.fetchone()[0] or 0

        cursor.execute(
            "SELECT SUM(amount) FROM recharge_history WHERE id_user = ? AND status = 'SUCCESS'",
            (caller_id,),
        )
        total_recharge = cursor.fetchone()[0] or 0

        cursor.execute(
            "SELECT COUNT(*) FROM orders WHERE id_buyer = ? AND status = 'CANCELED'",
            (caller_id,),
        )
        total_canceled = cursor.fetchone()[0] or 0

        lines = [
            get_text(caller_id, 'analytics.title'),
            "",
            *products_lines,
            "",
            f"{get_text(caller_id, 'analytics.total_spent')}: {total_spent} USD",
            f"{get_text(caller_id, 'analytics.total_recharge')}: {total_recharge} USDT",
            f"{get_text(caller_id, 'analytics.total_canceled')}: {total_canceled}",
        ]

        await q.edit_message_text("\n".join(lines), reply_markup=buttons)
    finally:
        cursor.close()
        conn.close()

async def handle_vn_recharge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    if get_active_flow(context) not in (None, "sepay_amount", "sepay_pending"):
        await notify_flow_busy(update, context)
        return

    await q.answer()
    caller_id = q.from_user.id

    conn = db_connect()
    cursor = conn.cursor()

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="go_payment_info:NONE")]
    ])

    try:
        # Block check (bỏ qua nếu là admin)
        if caller_id != settings.ADMIN_ID:
            cursor.execute("SELECT 1 FROM users WHERE is_blocked = 1 AND id_user = ?", (caller_id,))
            if cursor.fetchone():
                await q.edit_message_text(get_text(caller_id, 'common.blocked'), reply_markup=buttons)
                return

        owner   = html.escape(str(getattr(settings, "VN_OWNER_NAME", "") or "N/A"))
        bank    = html.escape(str(getattr(settings, "VN_BANK_NAME", "") or "N/A"))
        code    = html.escape(str(getattr(settings, "VN_BANK_CODE", "") or "N/A"))
        acc     = html.escape(str(getattr(settings, "VN_BANK_ACCOUNT", "") or "N/A"))
        admin_username = (settings.USER_NAME and settings.USER_NAME.strip()) or get_text(caller_id, 'common.admin')

        # Nếu bạn có VN_BRANCH thì lấy, không có thì bỏ dòng
        branch_val = getattr(settings, "VN_BRANCH", None)
        branch = html.escape(str(branch_val)) if branch_val else None

        lines = [
            f"🏦 <b>{get_text(caller_id, 'vn_bank.title')}</b>",
            "",
            f"<b>{get_text(caller_id, 'vn_bank.owner')}:</b> <code>{owner}</code>",
            f"<b>{get_text(caller_id, 'vn_bank.bank')}:</b> <code>{bank}</code>",
            f"<b>{get_text(caller_id, 'vn_bank.bank_code')}:</b> <code>{code}</code>",
            f"<b>{get_text(caller_id, 'vn_bank.account_number')}:</b> <code>{acc}</code>",
        ]
        if branch:
            lines.append(f"<b>{get_text(caller_id, 'vn_bank.branch')}:</b> <code>{branch}</code>")

        lines += [
            "",
            f"{get_text(caller_id, 'vn_bank.contact_admin')} <b>{admin_username}</b> {get_text(caller_id, 'vn_bank.help')}",
            "",
            f"{get_text(caller_id, 'sepay.prompt_amount')}"
        ]

        clear_active_flow(context)
        context.user_data["active_flow"] = "sepay_amount"
        context.user_data["awaiting_sepay_amount"] = True
        text = "\n".join(lines)

        await q.edit_message_text(text=text, reply_markup=buttons, parse_mode="HTML")

    except BadRequest as e:
        # Nếu message không đổi hoặc lỗi Telegram khác
        await q.edit_message_text(text=f"{get_text(caller_id, 'error.telegram')} {e}", reply_markup=buttons)

    except Exception as e:
        await q.edit_message_text(text=f"{get_text(caller_id, 'error.generic')} {e}", reply_markup=buttons)

    finally:
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass
    return



async def handle_crypto_recharge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    if get_active_flow(context) not in (None, "crypto_txid"):
        await notify_flow_busy(update, context)
        return

    await q.answer()
    caller_id = q.from_user.id

    conn = db_connect()
    cursor = conn.cursor()

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(caller_id, 'common.back'), callback_data="go_payment_info:NONE")]
    ])

    try:
        # Block check (bỏ qua nếu là admin)
        if caller_id != settings.ADMIN_ID:
            cursor.execute("SELECT 1 FROM users WHERE is_blocked = 1 AND id_user = ?", (caller_id,))
            if cursor.fetchone():
                await q.edit_message_text(get_text(caller_id, 'common.blocked'), reply_markup=buttons)
                return

        trc20 = str(getattr(settings, "TRC20_ADDRESS", "") or "").strip()
        bep20 = str(getattr(settings, "BEP20_ADDRESS", "") or "").strip()
        binance_id = str(getattr(settings, "BINANCE_ID", "") or "").strip()
        admin_username = (settings.USER_NAME and settings.USER_NAME.strip()) or get_text(caller_id, 'common.admin')

        lines = [
            f"🪙 <b>{get_text(caller_id, 'crypto.title')}</b>",
            "",
            f"💰 <b>{get_text(caller_id, 'crypto.binance_id')}</b> <code>{binance_id}</code>",
            "",
            f"⚠️ <b>{get_text(caller_id, 'crypto.warning')}</b>",
            get_text(caller_id, 'crypto.warning_detail'),
            "",
        ]

        if trc20:
            lines += [
                f"<b>{get_text(caller_id, 'crypto.trc20')}</b>",
                f"<code>{html.escape(trc20)}</code>",
                "",
            ]
        else:
            lines += [f"<b>{get_text(caller_id, 'crypto.trc20')}</b> <i>{get_text(caller_id, 'crypto.not_configured')}</i>", ""]

        if bep20:
            lines += [
                f"<b>{get_text(caller_id, 'crypto.bep20')}</b>",
                f"<code>{html.escape(bep20)}</code>",
                "",
            ]
        else:
            lines += [f"<b>{get_text(caller_id, 'crypto.bep20')}</b> <i>{get_text(caller_id, 'crypto.not_configured')}</i>", ""]

        lines += [
            f"{get_text(caller_id, 'crypto.contact_admin')}",
            f"<b>{admin_username}</b>",
            "",
            get_text(caller_id, 'crypto.txid_prompt'),
        ]

        clear_active_flow(context)
        context.user_data["active_flow"] = "crypto_txid"
        context.user_data["awaiting_crypto_txid"] = True
        text = "\n".join(lines)

        await q.edit_message_text(text=text, reply_markup=buttons, parse_mode="HTML")

    except BadRequest as e:
        await q.edit_message_text(text=f"{get_text(caller_id, 'error.telegram')} {e}", reply_markup=buttons)

    except Exception as e:
        await q.edit_message_text(text=f"{get_text(caller_id, 'error.generic')} {e}", reply_markup=buttons)

    finally:
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass

# Cancel recharge command - Cancel ongoing recharge flow
async def cancel_recharge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to cancel ongoing recharge flow (VN Bank/SePay/Crypto)"""
    if not update.message:
        return
    
    user_id = update.message.from_user.id
    active_flow = get_active_flow(context)
    
    # Kiểm tra xem có flow nạp tiền nào đang active không
    recharge_flows = ["sepay_amount", "sepay_pending", "crypto_txid"]
    
    if active_flow not in recharge_flows and not context.user_data.get("awaiting_sepay_amount") and not context.user_data.get("awaiting_crypto_txid"):
        await update.message.reply_text(get_text(user_id, 'recharge.no_pending'))
        return
    
    # Clear các flow liên quan đến nạp tiền
    clear_active_flow(context)
    
    # Thông báo hủy thành công
    await update.message.reply_text(get_text(user_id, 'recharge.cancelled'))
    logger.info(f"User {user_id} cancelled recharge flow")


# Language command - Change user language
async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to change user's language preference"""
    # Handle both callback query (button click) and message (command)
    q = update.callback_query
    is_callback = q is not None
    
    if is_callback:
        await q.answer()
        user_id = q.from_user.id
    else:
        if not update.message:
            return
        user_id = update.message.from_user.id
    
    conn = db_connect()
    cursor = conn.cursor()
    
    try:
        # Check if user is blocked
        cursor.execute("SELECT * FROM users WHERE id_user = ? and is_blocked = 1", (user_id,))
        data = cursor.fetchone()
        if data:
            blocked_text = get_text(user_id, 'common.blocked')
            if is_callback:
                await q.edit_message_text(blocked_text)
            else:
                await update.message.reply_text(blocked_text)
            return
        
        # Get current language
        current_lang = get_user_language(user_id)
        lang_name = "English" if current_lang == 'en' else "Tiếng Việt"
        
        # Create language selection buttons - cùng một hàng
        language_buttons = [
            InlineKeyboardButton(
                get_text(user_id, 'language.english') + (" ✅" if current_lang == 'en' else ""),
                callback_data="lang:en"
            ),
            InlineKeyboardButton(
                get_text(user_id, 'language.vietnamese') + (" ✅" if current_lang == 'vi' else ""),
                callback_data="lang:vi"
            )
        ]
        
        # Tạo keyboard: language buttons cùng hàng, và nút Back nếu là callback
        keyboard_rows = [[language_buttons[0], language_buttons[1]]]  # Cùng một hàng
        
        # Chỉ thêm nút Back nếu là callback (từ button click), không thêm nếu là command
        if is_callback:
            keyboard_rows.append([InlineKeyboardButton(get_text(user_id, 'common.back'), callback_data="back_dashboard:NONE")])
        
        buttons = InlineKeyboardMarkup(keyboard_rows)
        
        text = f"""
{get_text(user_id, 'language.title')}

{get_text(user_id, 'language.current')} {lang_name}

{get_text(user_id, 'language.select')}
"""
        
        if is_callback:
            await q.edit_message_text(text, reply_markup=buttons)
        else:
            await update.message.reply_text(text, reply_markup=buttons)
        
    except Exception as e:
        logger.error(f"Error in language_command: {e}")
        error_text = get_text(user_id, 'language.error')
        if is_callback:
            await q.edit_message_text(error_text)
        else:
            await update.message.reply_text(error_text)
    finally:
        cursor.close()
        conn.close()

# Handle language change callback
async def handle_language_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle language change callback"""
    q = update.callback_query
    if not q:
        return
    
    await q.answer()
    user_id = q.from_user.id
    lang_code = q.data.split(':')[1]  # lang:en or lang:vi
    
    conn = db_connect()
    cursor = conn.cursor()
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(user_id, 'common.back'), callback_data="back_dashboard:NONE")]
    ])
    
    try:
        # Check if user is blocked
        cursor.execute("SELECT * FROM users WHERE id_user = ? and is_blocked = 1", (user_id,))
        data = cursor.fetchone()
        if data:
            await q.edit_message_text(get_text(user_id, 'common.blocked'), reply_markup=buttons)
            return
        
        # Set new language
        if set_user_language(user_id, lang_code):
            lang_name = "English" if lang_code == 'en' else "Tiếng Việt"
            # Get text in new language
            new_lang = get_user_language(user_id)
            text = f"{get_text(user_id, 'language.changed')} {lang_name}"
            await q.edit_message_text(text, reply_markup=buttons)
        else:
            await q.edit_message_text(get_text(user_id, 'language.error'), reply_markup=buttons)
            
    except Exception as e:
        logger.error(f"Error in handle_language_change: {e}")
        await q.edit_message_text(get_text(user_id, 'language.error'), reply_markup=buttons)
    finally:
        cursor.close()
        conn.close()
