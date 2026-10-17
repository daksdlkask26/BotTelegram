"""
Translation strings for the Telegram bot.
Supports English (en) and Vietnamese (vi).
English is the default language.
"""

translations = {
    'en': {
        # Common
        'common.back': '⬅️ Back',
        'common.error': '❌ Error',
        'common.not_found': 'Not found',
        'common.success': '✅ Success',
        'common.blocked': 'You are blocked',
        'common.admin': 'admin',
        'flow.busy': '⚠️ You have a pending flow. Please finish or cancel it first.',
        'flow.product_qty': '⚠️ You are currently selecting product quantity.\n\nTo cancel: Use /dashboard or /start',
        'flow.sepay_amount': '⚠️ You are currently entering recharge amount (VN Bank/SePay).\n\nTo cancel: Use /cancelrecharge, /dashboard or /start',
        'flow.sepay_pending': '⚠️ You have a pending SePay payment.\n\nTo cancel: Use /dashboard or /start',
        'flow.crypto_txid': '⚠️ You are currently entering Crypto TxID.\n\nTo cancel: Use /cancelrecharge, /dashboard or /start',
        'recharge.cancelled': '✅ Recharge cancelled successfully. You can start a new recharge anytime.',
        'recharge.no_pending': 'ℹ️ You don\'t have any pending recharge flow.',
        'flow.stock_add': '⚠️ You are currently updating product stock.\n\nTo cancel: Use /dashboard or /start',
        'flow.product_description': '⚠️ You are currently entering product description.\n\nTo cancel: Use /dashboard or /start',
        'flow.unknown': '⚠️ You have a pending flow.\n\nTo cancel: Use /dashboard or /start',
        
        # Start command
        'start.welcome': (
            "👋 Welcome!\n\n"
            "Here’s how to get started:\n"
            "1) 🛍️ Browse products\n"
            "2) 💰 Top up your balance\n"
            "3) 📋 Check your orders\n\n"
            "Tips:\n"
            "- Use /dashboard for the main menu\n"
            "- Use /help to see all commands\n"
        ),
        'start.blocked': 'You are blocked',
        
        # Help command
        'help.title': 'Help Information',
        'help.commands': 'Available commands:',
        'help.dashboard': '/dashboard - Show your dashboard',
        'help.listproducts': '/listproducts - Show all products',
        'help.addfund': '/addfund - Add funds to your account',
        'help.myid': '/myid - Show your user ID',
        'help.aboutme': '/aboutme - Show your account information',
        
        # Dashboard
        'dashboard.title': '📊 Dashboard',
        'dashboard.analytics': 'Analytics',
        'dashboard.balance': 'Balance',
        'dashboard.orders': 'Orders',
        'dashboard.products': 'Products',
        'dashboard.payment': 'Payment',
        'dashboard.support': 'Support',
        'dashboard.user_info': 'User Info',
        'dashboard.add_balance': 'Add Balance',
        'dashboard.my_orders': 'My Orders',
        'dashboard.list_products': 'List Products',
        'dashboard.actions': 'Recharge History',
        'dashboard.languages': 'Language',
        'dashboard.reload': '🔄 Reload',
        'analytics.title': '📈 Analytics',
        'analytics.products_title': 'Products purchased:',
        'analytics.total_spent': 'Total spent',
        'analytics.total_recharge': 'Total recharge',
        'analytics.total_canceled': 'Canceled orders',
        
        # User Info
        'user_info.title': '👤 Your account information:',
        'user_info.id': 'ID',
        'user_info.username': 'Username',
        'user_info.balance': 'Balance',
        'user_info.currency': 'Currency',
        'user_info.products_bought': 'Products Bought',
        'user_info.created_at': 'Created At',
        'user_info.not_found': '❌ Your information isn\'t found',
        
        # Products
        'products.title': '📦 Products',
        'products.not_found': 'No products available',
        'products.name': 'Name',
        'products.price': 'Price',
        'products.stock': 'Stock',
        'products.description': 'Description',
        'products.description_prompt': '📝 Enter product description (or send /skip to skip):',
        'products.description_added': '✅ Product description added successfully!',
        'products.description_skipped': '✅ Product added without description.',
        'products.buy': 'Buy',
        'products.back': 'Back to list',
        'products.confirm_buy': 'Confirm Purchase',
        'products.quantity': 'Quantity',
        'products.total': 'Total',
        'products.insufficient_balance': '❌ Insufficient balance',
        'products.out_of_stock': '❌ Out of stock',
        'products.purchase_success': '✅ Purchase successful!',
        
        # Orders
        'orders.title': '📋 My Orders',
        'orders.empty': 'You have no orders yet',
        'orders.order_id': 'Order ID',
        'orders.product': 'Product',
        'orders.quantity': 'Quantity',
        'orders.price': 'Price',
        'orders.status': 'Status',
        'orders.pending': 'Pending',
        'orders.completed': 'Completed',
        'orders.cancelled': 'Cancelled',
        'orders.exporting': '⏳ Exporting all orders...',
        'orders.exported': '✅ All orders have been exported',

        # Actions / Recharge History
        'actions.title': '📜 Recharge History',
        'actions.empty': 'No recharge history yet',
        'actions.amount': 'Amount',
        'actions.method': 'Method',
        'actions.status': 'Status',
        'actions.txid': 'TxID',
        'actions.time': 'Time',
        'actions.exporting': '⏳ Exporting all recharge history...',
        'actions.exported': '✅ All recharge history has been exported',
        
        # Payment
        'payment.title': '💳 Payment Methods',
        'payment.crypto': 'Crypto Recharge',
        'payment.vn_bank': 'Vietnam Bank',
        'payment.auto_qr': 'Auto Topup (QR)',

        # SePay Auto Topup
        'sepay.prompt_amount': 'Enter the amount to top up (VND):',
        'sepay.invalid_amount': '❌ Invalid amount. Please enter digits only.',
        'sepay.min_amount': '❌ Minimum amount is 2000 VND.',
        'sepay.not_configured': '❌ Bank info not configured. Please contact admin.',
        'sepay.qr_title': '🧾 Scan QR to pay',
        'sepay.amount_vnd': 'Amount',
        'sepay.amount_usdt': 'Converted',
        'sepay.order_code': 'Order code',
        'sepay.scan_note': 'Please transfer the exact amount. The system will auto-credit after payment.',
        'sepay.confirm_button': '✅ I have paid',
        'sepay.cancel_button': '❌ Cancel',
        'sepay.check_button': '🔄 Check again',
        'sepay.cancel_order_button': '❌ Cancel order',
        'sepay.confirmed': '✅ Payment marked. The system will auto-credit after the bank confirms.',
        'sepay.cancelled': '❌ Payment cancelled. You can start a new top up anytime.',
        'sepay.not_found': '❌ Order not found.',
        'sepay.qr_generating': '⏳ Generating payment QR...',
        'sepay.qr_expires': 'QR expires in:',
        'sepay.auto_cancel_note': 'Order will be automatically cancelled after 5 minutes if not paid.',
        'sepay.success': (
            "✅ Recharge successful\n"
            "• Order: <code>{order_code}</code>\n"
            "• Amount: <code>{amount_vnd} VND</code>\n"
            "• Converted: <code>{amount_usdt} USDT</code>"
        ),
        
        # Crypto Recharge
        'crypto.title': '🪙 Crypto Recharge',
        'crypto.binance_id': '💰 Binance ID:',
        'crypto.warning': '⚠️ Send only USDT to the correct network.',
        'crypto.warning_detail': 'If you send the wrong network, funds may be lost.',
        'crypto.trc20': 'USDT (TRC20):',
        'crypto.bep20': 'USDT (BEP20):',
        'crypto.not_configured': 'Not configured',
        'crypto.contact_admin': '📩 After payment, contact admin to confirm:',
        'crypto.txid_prompt': 'Send your Binance Order ID or TxID to auto-credit:',
        'crypto.not_found': '❌ Transaction not found. Please check and try again.',
        'crypto.duplicate': '❌ This transaction was already credited.',
        'crypto.confirmed': '✅ Payment confirmed. Added {amount} {currency} to your balance.',
        'crypto.too_old': '❌ Transaction is older than 24 hours and cannot be used.',
        
        # VN Bank Recharge
        'vn_bank.title': '🏦 Vietnam Bank Transfer',
        'vn_bank.bank': 'Bank',
        'vn_bank.bank_code': 'Bank Code',
        'vn_bank.account_number': 'Account Number',
        'vn_bank.branch': 'Branch',
        'vn_bank.owner': 'Account Owner',
        'vn_bank.contact_admin': '📩 Contact admin:',
        'vn_bank.help': 'if you need help.',
        
        # Support
        'support.title': '📞 Support',
        'support.contact': 'Contact supporter:',
        'support.help_command': '/help How to use bot!',
        
        # Language
        'language.title': '🌐 Language Settings',
        'language.current': 'Current language:',
        'language.select': 'Select your preferred language:',
        'language.english': '🇬🇧 English',
        'language.vietnamese': '🇻🇳 Tiếng Việt',
        'language.changed': '✅ Language changed to',
        'language.error': '❌ Failed to change language',
        
        # Errors
        'error.telegram': '❌ Telegram error:',
        'error.generic': '❌ ERROR:',
        'error.blocked': '❌ You are blocked',

        # Admin notifications (user language)
        'admin.order_new': (
            "New order\n"
            "=======\n"
            "ID buyer:{buyer_id}\n"
            "OrderID: {order_id}\n"
            "Product ID: {product_id}\n"
            "Product Name: {product_name}\n"
            "Quality: {quantity}\n"
            "Price: {price} USD\n"
            "Total: {total} USD\n"
            "Status: Pending"
        ),
        'admin.order_success': (
            "Order success\n"
            "=======\n"
            "ID buyer:{buyer_id}\n"
            "OrderID: {order_id}\n"
            "Product ID: {product_id}\n"
            "Product Name: {product_name}\n"
            "Quality: {quantity}\n"
            "Price: {price} USD\n"
            "Total: {total} USD\n"
            "Status: Successful"
        ),
        'admin.recharge_new': (
            "New recharge\n"
            "=======\n"
            "ID buyer: {buyer_id}\n"
            "Order Recharge: {order_code}\n"
            "Amount: {amount} VND\n"
            "Current balance: {current_balance} USDT\n"
            "Status: Pending"
        ),
        'admin.recharge_success': (
            "Recharge success\n"
            "=======\n"
            "ID buyer: {buyer_id}\n"
            "Order Recharge: {order_code}\n"
            "Amount: {amount} VND\n"
            "Current balance: {current_balance} USDT\n"
            "After recharge: {after_balance} USDT\n"
            "Status: Successful"
        ),
    },
    
    'vi': {
        # Common
        'common.back': '⬅️ Quay lại',
        'common.error': '❌ Lỗi',
        'common.not_found': 'Không tìm thấy',
        'common.success': '✅ Thành công',
        'common.blocked': 'Bạn đã bị chặn',
        'common.admin': 'admin',
        'flow.busy': '⚠️ Bạn đang có một luồng đang xử lý. Vui lòng hoàn tất hoặc hủy trước.',
        'flow.product_qty': '⚠️ Bạn đang chọn số lượng sản phẩm.\n\nĐể hủy: Dùng /dashboard hoặc /start',
        'flow.sepay_amount': '⚠️ Bạn đang nhập số tiền nạp (Ngân hàng VN/SePay).\n\nĐể hủy: Dùng /cancelrecharge, /dashboard hoặc /start',
        'flow.sepay_pending': '⚠️ Bạn có một giao dịch SePay đang chờ.\n\nĐể hủy: Dùng /cancelrecharge, /dashboard hoặc /start',
        'flow.crypto_txid': '⚠️ Bạn đang nhập TxID Crypto.\n\nĐể hủy: Dùng /cancelrecharge, /dashboard hoặc /start',
        'recharge.cancelled': '✅ Đã hủy nạp tiền thành công. Bạn có thể bắt đầu nạp mới bất cứ lúc nào.',
        'recharge.no_pending': 'ℹ️ Bạn không có luồng nạp tiền nào đang chờ.',
        'flow.stock_add': '⚠️ Bạn đang cập nhật tồn kho sản phẩm.\n\nĐể hủy: Dùng /dashboard hoặc /start',
        'flow.product_description': '⚠️ Bạn đang nhập mô tả sản phẩm.\n\nĐể hủy: Dùng /dashboard hoặc /start',
        'flow.unknown': '⚠️ Bạn đang có một luồng đang xử lý.\n\nĐể hủy: Dùng /dashboard hoặc /start',
        
        # Start command
        'start.welcome': (
            "👋 Xin chào!\n\n"
            "Bắt đầu nhanh trong 10 giây:\n"
            "1) 🛍️ Xem danh sách sản phẩm\n"
            "2) 💰 Nạp tiền vào số dư\n"
            "3) 📋 Xem đơn hàng của bạn\n\n"
            "Gợi ý:\n"
            "- Dùng /dashboard để mở menu chính\n"
            "- Dùng /help để xem toàn bộ lệnh\n"
        ),
        'start.blocked': 'Bạn đã bị chặn',
        
        # Help command
        'help.title': 'Thông tin trợ giúp',
        'help.commands': 'Các lệnh có sẵn:',
        'help.dashboard': '/dashboard - Hiển thị bảng điều khiển của bạn',
        'help.listproducts': '/listproducts - Hiển thị tất cả sản phẩm',
        'help.addfund': '/addfund - Nạp tiền vào tài khoản',
        'help.myid': '/myid - Hiển thị ID người dùng của bạn',
        'help.aboutme': '/aboutme - Hiển thị thông tin tài khoản của bạn',
        
        # Dashboard
        'dashboard.title': '📊 Bảng điều khiển',
        'dashboard.analytics': 'Phân tích',
        'dashboard.balance': 'Số dư',
        'dashboard.orders': 'Đơn hàng',
        'dashboard.products': 'Sản phẩm',
        'dashboard.payment': 'Thanh toán',
        'dashboard.support': 'Hỗ trợ',
        'dashboard.user_info': 'Thông tin tài khoản',
        'dashboard.add_balance': 'Nạp tiền',
        'dashboard.my_orders': 'Đơn hàng của tôi',
        'dashboard.list_products': 'Danh sách sản phẩm',
        'dashboard.actions': 'Lịch sử nạp tiền',
        'dashboard.languages': 'Ngôn ngữ',
        'dashboard.reload': '🔄 Tải lại',
        'analytics.title': '📈 Phân tích',
        'analytics.products_title': 'Sản phẩm đã mua:',
        'analytics.total_spent': 'Tổng tiền đã mua',
        'analytics.total_recharge': 'Tổng tiền đã nạp',
        'analytics.total_canceled': 'Tổng đơn đã hủy',
        
        # User Info
        'user_info.title': '👤 Thông tin tài khoản của bạn:',
        'user_info.id': 'ID',
        'user_info.username': 'Tên người dùng',
        'user_info.balance': 'Số dư',
        'user_info.currency': 'Tiền tệ',
        'user_info.products_bought': 'Sản phẩm đã mua',
        'user_info.created_at': 'Ngày tạo',
        'user_info.not_found': '❌ Không tìm thấy thông tin của bạn',
        
        # Products
        'products.title': '📦 Sản phẩm',
        'products.not_found': 'Không có sản phẩm nào',
        'products.name': 'Tên',
        'products.price': 'Giá',
        'products.stock': 'Tồn kho',
        'products.description': 'Mô tả',
        'products.description_prompt': '📝 Nhập mô tả sản phẩm (hoặc gửi /skip để bỏ qua):',
        'products.description_added': '✅ Đã thêm mô tả sản phẩm thành công!',
        'products.description_skipped': '✅ Đã thêm sản phẩm không có mô tả.',
        'products.buy': 'Mua',
        'products.back': 'Quay lại danh sách',
        'products.confirm_buy': 'Xác nhận mua',
        'products.quantity': 'Số lượng',
        'products.total': 'Tổng cộng',
        'products.insufficient_balance': '❌ Số dư không đủ',
        'products.out_of_stock': '❌ Hết hàng',
        'products.purchase_success': '✅ Mua hàng thành công!',
        
        # Orders
        'orders.title': '📋 Đơn hàng của tôi',
        'orders.empty': 'Bạn chưa có đơn hàng nào',
        'orders.order_id': 'Mã đơn hàng',
        'orders.product': 'Sản phẩm',
        'orders.quantity': 'Số lượng',
        'orders.price': 'Giá',
        'orders.status': 'Trạng thái',
        'orders.pending': 'Đang chờ',
        'orders.completed': 'Hoàn thành',
        'orders.cancelled': 'Đã hủy',
        'orders.exporting': '⏳ Đang xuất tất cả đơn hàng...',
        'orders.exported': '✅ Đã xuất xong tất cả đơn hàng',

        # Actions / Recharge History
        'actions.title': '📜 Lịch sử nạp tiền',
        'actions.empty': 'Chưa có lịch sử nạp tiền',
        'actions.amount': 'Số tiền',
        'actions.method': 'Phương thức',
        'actions.status': 'Trạng thái',
        'actions.txid': 'TxID',
        'actions.time': 'Thời gian',
        'actions.exporting': '⏳ Đang xuất tất cả lịch sử nạp tiền...',
        'actions.exported': '✅ Đã xuất xong tất cả lịch sử nạp tiền',
        
        # Payment
        'payment.title': '💳 Phương thức thanh toán',
        'payment.crypto': 'Nạp tiền Crypto',
        'payment.vn_bank': 'Ngân hàng Việt Nam',
        'payment.auto_qr': 'Nạp tự động (QR)',

        # SePay Auto Topup
        'sepay.prompt_amount': 'Nhập số tiền cần nạp (VND):',
        'sepay.invalid_amount': '❌ Số tiền không hợp lệ. Vui lòng nhập số.',
        'sepay.min_amount': '❌ Số tiền tối thiểu là 2000 VND.',
        'sepay.not_configured': '❌ Chưa cấu hình ngân hàng. Vui lòng liên hệ admin.',
        'sepay.qr_title': '🧾 Quét QR để thanh toán',
        'sepay.amount_vnd': 'Số tiền',
        'sepay.amount_usdt': 'Quy đổi',
        'sepay.order_code': 'Mã đơn',
        'sepay.scan_note': 'Vui lòng chuyển đúng số tiền. Hệ thống sẽ tự cộng sau khi thanh toán.',
        'sepay.confirm_button': '✅ Đã thanh toán',
        'sepay.cancel_button': '❌ Hủy',
        'sepay.check_button': '🔄 Kiểm tra lại',
        'sepay.cancel_order_button': '❌ Hủy đơn',
        'sepay.confirmed': '✅ Đã ghi nhận. Hệ thống sẽ tự cộng sau khi ngân hàng xác nhận.',
        'sepay.cancelled': '❌ Đã hủy thanh toán. Bạn có thể tạo nạp mới bất cứ lúc nào.',
        'sepay.not_found': '❌ Không tìm thấy đơn.',
        'sepay.qr_generating': '⏳ Đang tạo QR thanh toán...',
        'sepay.qr_expires': 'QR hết hạn sau:',
        'sepay.auto_cancel_note': 'Đơn hàng sẽ tự động hủy sau 5 phút nếu chưa thanh toán.',
        'sepay.success': (
            "✅ Nạp tiền thành công\n"
            "• Mã đơn: <code>{order_code}</code>\n"
            "• Số tiền: <code>{amount_vnd} VND</code>\n"
            "• Quy đổi: <code>{amount_usdt} USDT</code>"
        ),
        
        # Crypto Recharge
        'crypto.title': '🪙 Nạp tiền Crypto',
        'crypto.binance_id': '💰 Binance ID:',
        'crypto.warning': '⚠️ Chỉ gửi USDT đến đúng mạng lưới.',
        'crypto.warning_detail': 'Nếu bạn gửi sai mạng lưới, tiền có thể bị mất.',
        'crypto.trc20': 'USDT (TRC20):',
        'crypto.bep20': 'USDT (BEP20):',
        'crypto.not_configured': 'Chưa cấu hình',
        'crypto.contact_admin': '📩 Sau khi thanh toán, liên hệ admin để xác nhận:',
        'crypto.txid_prompt': 'Gửi Order ID Binance hoặc TxID để tự cộng tiền:',
        'crypto.not_found': '❌ Không tìm thấy giao dịch. Vui lòng kiểm tra và thử lại.',
        'crypto.duplicate': '❌ Giao dịch này đã được cộng trước đó.',
        'crypto.confirmed': '✅ Xác nhận thanh toán. Đã cộng {amount} {currency} vào số dư.',
        'crypto.too_old': '❌ Giao dịch đã quá 24 giờ nên không thể dùng.',
        
        # VN Bank Recharge
        'vn_bank.title': '🏦 Chuyển khoản ngân hàng Việt Nam',
        'vn_bank.bank': 'Ngân hàng',
        'vn_bank.bank_code': 'Mã ngân hàng',
        'vn_bank.account_number': 'Số tài khoản',
        'vn_bank.branch': 'Chi nhánh',
        'vn_bank.owner': 'Chủ tài khoản',
        'vn_bank.contact_admin': '📩 Liên hệ admin:',
        'vn_bank.help': 'nếu bạn cần trợ giúp.',
        
        # Support
        'support.title': '📞 Hỗ trợ',
        'support.contact': 'Liên hệ hỗ trợ:',
        'support.help_command': '/help Cách sử dụng bot!',
        
        # Language
        'language.title': '🌐 Cài đặt ngôn ngữ',
        'language.current': 'Ngôn ngữ hiện tại:',
        'language.select': 'Chọn ngôn ngữ bạn muốn:',
        'language.english': '🇬🇧 English',
        'language.vietnamese': '🇻🇳 Tiếng Việt',
        'language.changed': '✅ Đã đổi ngôn ngữ sang',
        'language.error': '❌ Không thể đổi ngôn ngữ',
        
        # Errors
        'error.telegram': '❌ Lỗi Telegram:',
        'error.generic': '❌ LỖI:',
        'error.blocked': '❌ Bạn đã bị chặn',

        # Admin notifications (user language)
        'admin.order_new': (
            "Đơn mới\n"
            "=======\n"
            "ID buyer:{buyer_id}\n"
            "OrderID: {order_id}\n"
            "Product ID: {product_id}\n"
            "Product Name: {product_name}\n"
            "Quality: {quantity}\n"
            "Price: {price} USD\n"
            "Total: {total} USD\n"
            "Status: Pending"
        ),
        'admin.order_success': (
            "Đơn vừa thành công\n"
            "=======\n"
            "ID buyer:{buyer_id}\n"
            "OrderID: {order_id}\n"
            "Product ID: {product_id}\n"
            "Product Name: {product_name}\n"
            "Quality: {quantity}\n"
            "Price: {price} USD\n"
            "Total: {total} USD\n"
            "Status: Successful"
        ),
        'admin.recharge_new': (
            "Nạp mới\n"
            "=======\n"
            "ID buyer: {buyer_id}\n"
            "Order Recharge: {order_code}\n"
            "Amount: {amount} VND\n"
            "Current balance: {current_balance} USDT\n"
            "Status: Pending"
        ),
        'admin.recharge_success': (
            "Nạp thành công\n"
            "=======\n"
            "ID buyer: {buyer_id}\n"
            "Order Recharge: {order_code}\n"
            "Amount: {amount} VND\n"
            "Current balance: {current_balance} USDT\n"
            "After recharge: {after_balance} USDT\n"
            "Status: Successful"
        ),
    }
}
