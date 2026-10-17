# BotTele – Telegram Shop Bot

Bot Telegram bán sản phẩm số (tài khoản, key, ...) với ví nội bộ, nạp tiền tự động qua **Sepay** (chuyển khoản ngân hàng VN) và **Binance** (USDT TRC20/BEP20), kho hàng, quản lý đơn và phân quyền admin/subadmin. Hỗ trợ đa ngôn ngữ.

## Tính năng

- **Người dùng**: xem sản phẩm, chọn số lượng, mua hàng, xem dashboard/thông tin cá nhân, đổi ngôn ngữ.
- **Nạp tiền**: QR/chuyển khoản ngân hàng VN qua webhook Sepay; nạp crypto USDT (TRC20, BEP20) đối soát qua Binance API; đơn nạp có thời hạn (`ORDER_TTL_SECONDS`).
- **Quản trị**: thêm/xóa sản phẩm, quản lý kho (`pushItem`, `pullItem`, `updatestock`, ...), xử lý đơn, hoàn tiền, broadcast, khóa/mở khóa user, thống kê.
- **Phân quyền**: admin (`ADMIN_ID`), subadmin (lưu trong DB), người dùng thường.
- **Nhắc việc**: mỗi giờ gửi nhắc admin/subadmin các đơn `PENDING` chưa xử lý (có nút xác nhận / hủy / mute).

## Cấu trúc

```
main.py              Khởi tạo bot, đăng ký handler, job nhắc đơn, chạy webhook server
run.py               Entry point
config.py            Đọc cấu hình từ .env (pydantic-settings)
sepay_webhook.py     Flask webhook nhận giao dịch từ Sepay
look_up.py           Tra cứu giao dịch Binance
services/binance_api.py  Gọi Binance API (ký HMAC)
commands/            Lệnh: user, admin, boss; dbconfig.py tạo schema SQLite
i18n.py, locales.py  Đa ngôn ngữ
data/database.db     SQLite (tự tạo, không commit)
```

## Yêu cầu

- Python 3.10+
- Bot token từ [@BotFather](https://t.me/BotFather)
- (Tuỳ chọn) tài khoản Sepay và API key Binance (quyền chỉ đọc)

## Cài đặt

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirments.txt
cp .env.example .env     # rồi điền giá trị
python run.py
```

## Cấu hình (`.env`)

| Biến | Mô tả |
|---|---|
| `BOT_TOKEN` | Token bot Telegram (bắt buộc) |
| `ADMIN_ID` | Telegram ID của admin chính |
| `USER_NAME` | Username hỗ trợ hiển thị cho người dùng |
| `PATH_DB` | Đường dẫn SQLite, mặc định `data/database.db` |
| `SEPAY_WEBHOOK_KEY` | Khóa xác thực webhook Sepay |
| `WEBHOOK_PATH` | Đường dẫn webhook, mặc định `/sepay/webhook` |
| `PORT` | Cổng webhook server, mặc định `5051` |
| `ORDER_TTL_SECONDS` | Thời hạn đơn nạp, mặc định `900` |
| `BANK_ACC`, `BANK_CODE`, `BANK_NAME`, `ACC_OWNER` | Thông tin tài khoản ngân hàng nhận tiền |
| `BINANCE_API_KEY`, `BINANCE_API_SECRET`, `BINANCE_ID` | Thông tin Binance |
| `TRC20_ADDRESS`, `BEP20_ADDRESS` | Địa chỉ ví nhận USDT |

> **Bảo mật:** không commit `.env`, database hay log (đã có trong `.gitignore`). Nên dùng API key Binance chỉ có quyền đọc.

## Webhook Sepay

Trỏ webhook của Sepay tới `https://<domain>:<PORT><WEBHOOK_PATH>` (POST) và cấu hình cùng khóa `SEPAY_WEBHOOK_KEY`. Nên đặt sau reverse proxy HTTPS (nginx/caddy).

## Lệnh chính

**Người dùng:** `/start`, `/help`, `/dashboard`, `/listproducts`, `/addfund`, `/cancelrecharge`, `/myid`, `/aboutme`, `/language`

**Admin / subadmin:** `/help_admin`, `/help_subadmin`, `/addproduct`, `/removeproduct`, `/pushItem`, `/pullItem`, `/pullItems`, `/updatestock`, `/myStocks`, `/myStock`, `/listorders`, `/users`, `/detailuser`, `/refund`, `/broadcast`, `/block_user`, `/unblock_user`, `/stats`, `/add_admin`, `/remove_admin`, `/subAdmins`

## Chạy trên VPS

Chạy bằng `systemd`, `supervisor` hoặc `tmux` để bot tự khởi động lại:

```ini
[Service]
WorkingDirectory=/path/to/BotTele
ExecStart=/path/to/BotTele/.venv/bin/python run.py
Restart=always
```
