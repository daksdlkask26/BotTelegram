from telegram import Update
from config import settings
from telegram.ext import ContextTypes
from sqlite3 import connect
import os
import logging
from telegram.error import RetryAfter, Forbidden, BadRequest
import asyncio
from telegram.constants import ParseMode

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO,
                    filename = "action.log",
                    filemode='a' # ghi noi tiep khong ghi de
                    )
logger = logging.getLogger(__name__)


# ===============================================================================
PATH_DB = settings.PATH_DB
# Kết nối đến cơ sở dữ liệu SQLite
def db_connect():
    # Tạo thư mục data nếu chưa tồn tại
    if not os.path.exists("data"):
        os.makedirs("data")
    
    conn = connect(PATH_DB) # kết nối đến file database.db trong thư mục data, nếu file chưa tồn tại thì sẽ tự động tạo mới
    conn.execute("PRAGMA foreign_keys = ON") # bật hỗ trợ khóa ngoại trong SQLite
    return conn

def init_db():
    conn = db_connect() # connect to database
    cursor = conn.cursor()
    try:
        # khoi tao bang users neu chua ton tai 
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id_user INTEGER PRIMARY KEY,
            user_name TEXT NOT NULL,
            balance REAL DEFAULT 0,
            currency TEXT DEFAULT 'USDT',
            is_subadmin BOOLEAN DEFAULT 0,
            is_blocked BOOLEAN DEFAULT 0,
            products_bought INT DEFAULT 0,
            language TEXT DEFAULT 'en',
            created_at TEXT DEFAULT (datetime('now', '+7 hours'))
        )
    ''')
        # Add language column if it doesn't exist (for existing databases)
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'en'")
            logger.info("Added language column to users table.")
        except:
            pass  # Column already exists
        logger.info("Created table users successfully.")
    except:
        logger.error("Failed to create table users.")


    try:
        # khoi tao bang subadmin neu chua ton tai
        cursor.execute('''
    CREATE TABLE IF NOT EXISTS subadmins (
        id_user INTEGER PRIMARY KEY,
        created_at TEXT DEFAULT (datetime('now', '+7 hours'))   
    )
''')
        logger.info("Created table subadmins successfully.")
    except:
        logger.error("Failed to create table subadmins.")

    try:
        # khoi tao bang luu danh sach san pham
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS listproducts (
    id_product     TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    price          REAL NOT NULL,
    quality        INTEGER DEFAULT 0,
    descrip        TEXT DEFAULT '@daksdlkasd',
    mode           INTEGER DEFAULT 0,
    created_at     TEXT DEFAULT (datetime('now', '+7 hours'))
);
""")
        # Migration: Nếu bảng đã tồn tại với INTEGER, cần migrate dữ liệu
        try:
            # Kiểm tra xem column có phải INTEGER không (bằng cách thử query)
            cursor.execute("SELECT typeof(id_product) FROM listproducts LIMIT 1")
            result = cursor.fetchone()
            if result and result[0] == 'integer':
                # Tạo bảng tạm
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS listproducts_new (
                        id_product     TEXT PRIMARY KEY,
                        name           TEXT NOT NULL,
                        price          REAL NOT NULL,
                        quality        INTEGER DEFAULT 0,
                        descrip        TEXT DEFAULT '@daksdlkasd',
                        created_at     TEXT DEFAULT (datetime('now', '+7 hours'))
                    )
                """)
                # Copy dữ liệu (convert INTEGER sang TEXT)
                cursor.execute("""
                    INSERT INTO listproducts_new 
                    SELECT CAST(id_product AS TEXT), name, price, quality, descrip, created_at 
                    FROM listproducts
                """)
                # Xóa bảng cũ và đổi tên bảng mới
                cursor.execute("DROP TABLE listproducts")
                cursor.execute("ALTER TABLE listproducts_new RENAME TO listproducts")
                conn.commit()
                logger.info("Migrated listproducts id_product from INTEGER to TEXT")
        except Exception as e:
            # Nếu không có dữ liệu hoặc đã là TEXT rồi, bỏ qua
            logger.info(f"Migration check for listproducts: {e}")
        
        # Migration: Thêm cột mode nếu chưa có
        try:
            cursor.execute("ALTER TABLE listproducts ADD COLUMN mode INTEGER DEFAULT 0")
            logger.info("Added mode column to listproducts table.")
        except:
            pass  # Column already exists
        # Đảm bảo các sản phẩm cũ có mode = 0
        cursor.execute("UPDATE listproducts SET mode = 0 WHERE mode IS NULL")
        
        logger.info("CREATED listproducts successfully")
    except:
        logger.error("CREATE listproducts UN successfully")


    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
        id_order INTEGER PRIMARY KEY,
        id_buyer INTEGER NOT NULL,
        name TEXT NOT NULL,
        price REAL NOT NULL,
        quality INTEGER NOT NULL,
        status DEFAULT 'Pending',
        created_at TEXT DEFAULT (datetime('now', '+7 hours')),
        is_exported BOOLEAN DEFAULT 0,
        user_info TEXT,
        product_id TEXT,
        is_muted BOOLEAN DEFAULT 0,
        last_notified_at TEXT
                       )
""")
        # Add is_exported column if it doesn't exist (for existing databases)
        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN is_exported BOOLEAN DEFAULT 0")
            logger.info("Added is_exported column to orders table.")
        except:
            pass  # Column already exists
        # Add user_info column for mode 0 orders
        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN user_info TEXT")
            logger.info("Added user_info column to orders table.")
        except:
            pass  # Column already exists
        # Add product_id column
        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN product_id TEXT")
            logger.info("Added product_id column to orders table.")
        except:
            pass  # Column already exists
        # Add is_muted column
        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN is_muted BOOLEAN DEFAULT 0")
            logger.info("Added is_muted column to orders table.")
        except:
            pass  # Column already exists
        # Add last_notified_at column
        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN last_notified_at TEXT")
            logger.info("Added last_notified_at column to orders table.")
        except:
            pass  # Column already exists
        logger.info("CREATED orders successfully")
    except:
        logger.error("CREATE orders UN successfully")

    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS recharge_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_user INTEGER NOT NULL,
        amount REAL NOT NULL,
        method TEXT DEFAULT 'manual',
        status TEXT DEFAULT 'SUCCESS',
        txid TEXT,
        created_at TEXT DEFAULT (datetime('now', '+7 hours')),
        is_exported BOOLEAN DEFAULT 0,
        FOREIGN KEY (id_user) REFERENCES users(id_user) ON DELETE CASCADE
                       )
""")
        # Add is_exported column if it doesn't exist (for existing databases)
        try:
            cursor.execute("ALTER TABLE recharge_history ADD COLUMN is_exported BOOLEAN DEFAULT 0")
            logger.info("Added is_exported column to recharge_history table.")
        except:
            pass  # Column already exists
        logger.info("CREATED recharge_history successfully")
    except:
        logger.error("CREATE recharge_history UN successfully")

    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS recharge_orders (
        order_code TEXT PRIMARY KEY,
        id_user INTEGER NOT NULL,
        amount_vnd INTEGER NOT NULL,
        amount_usdt REAL NOT NULL,
        status TEXT DEFAULT 'PENDING',
        txid TEXT,
        created_at TEXT DEFAULT (datetime('now', '+7 hours')),
        paid_at TEXT,
        product_id TEXT,
        product_qty INTEGER,
        product_name TEXT,
        expires_at TEXT,
        FOREIGN KEY (id_user) REFERENCES users(id_user) ON DELETE CASCADE
                       )
""")
        # Migration: Thêm columns cho product info nếu chưa có
        try:
            cursor.execute("ALTER TABLE recharge_orders ADD COLUMN product_id TEXT")
            logger.info("Added product_id column to recharge_orders table.")
        except:
            pass  # Column already exists
        try:
            cursor.execute("ALTER TABLE recharge_orders ADD COLUMN product_qty INTEGER")
            logger.info("Added product_qty column to recharge_orders table.")
        except:
            pass  # Column already exists
        try:
            cursor.execute("ALTER TABLE recharge_orders ADD COLUMN product_name TEXT")
            logger.info("Added product_name column to recharge_orders table.")
        except:
            pass  # Column already exists
        try:
            cursor.execute("ALTER TABLE recharge_orders ADD COLUMN expires_at TEXT")
            logger.info("Added expires_at column to recharge_orders table.")
        except:
            pass  # Column already exists
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_recharge_orders_user ON recharge_orders(id_user)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_recharge_orders_status ON recharge_orders(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_recharge_orders_expires ON recharge_orders(expires_at)")
        logger.info("CREATED recharge_orders successfully")
    except:
        logger.error("CREATE recharge_orders UN successfully")

    try:
        # Tạo bảng lưu stock items để kiểm tra trùng lặp
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id TEXT NOT NULL,
        item_content TEXT NOT NULL,
        status TEXT DEFAULT 'PENDING',
        created_at TEXT DEFAULT (datetime('now', '+7 hours')),
        sold_at TEXT,
        sold_to_user_id INTEGER,
        sold_order_id INTEGER,
        UNIQUE(product_id, item_content),
        FOREIGN KEY (product_id) REFERENCES listproducts(id_product) ON DELETE CASCADE
                       )
""")
        # Migration: Thêm cột status và sold_at nếu chưa có
        try:
            cursor.execute("ALTER TABLE stock_items ADD COLUMN status TEXT DEFAULT 'PENDING'")
            logger.info("Added status column to stock_items table.")
        except:
            pass  # Column already exists
        try:
            cursor.execute("ALTER TABLE stock_items ADD COLUMN sold_at TEXT")
            logger.info("Added sold_at column to stock_items table.")
        except:
            pass  # Column already exists
        # Migration: tracking người mua / order cho item đã bán
        try:
            cursor.execute("ALTER TABLE stock_items ADD COLUMN sold_to_user_id INTEGER")
            logger.info("Added sold_to_user_id column to stock_items table.")
        except:
            pass  # Column already exists
        try:
            cursor.execute("ALTER TABLE stock_items ADD COLUMN sold_order_id INTEGER")
            logger.info("Added sold_order_id column to stock_items table.")
        except:
            pass  # Column already exists
        # Cập nhật các items cũ thành PENDING nếu chưa có status
        cursor.execute("UPDATE stock_items SET status = 'PENDING' WHERE status IS NULL")
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_items_product ON stock_items(product_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_items_content ON stock_items(item_content)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_items_status ON stock_items(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_items_sold_to ON stock_items(sold_to_user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_items_sold_order ON stock_items(sold_order_id)")
        logger.info("CREATED stock_items successfully")
    except:
        logger.error("CREATE stock_items UN successfully")

    conn.commit()
    cursor.close()
    conn.close()
    # Đóng kết nối đến cơ sở dữ liệu
    return