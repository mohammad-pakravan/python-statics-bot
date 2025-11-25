"""
مدیریت دیتابیس SQLite برای کانال‌ها و آمار
"""
import sqlite3
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple


class Database:
    def __init__(self, db_path='theleton.db'):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        """ایجاد اتصال به دیتابیس"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """ایجاد جداول دیتابیس"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # جدول کانال‌ها
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                title TEXT,
                invite_link TEXT,
                category TEXT,
                telegram_id INTEGER,
                previous_telegram_id INTEGER,
                is_member BOOLEAN DEFAULT 0,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # اضافه کردن ستون‌های جدید به جدول موجود (اگر وجود ندارد)
        try:
            cursor.execute('ALTER TABLE channels ADD COLUMN invite_link TEXT')
        except sqlite3.OperationalError:
            pass  # ستون قبلاً وجود دارد
        
        try:
            cursor.execute('ALTER TABLE channels ADD COLUMN category TEXT')
        except sqlite3.OperationalError:
            pass  # ستون قبلاً وجود دارد
        
        try:
            cursor.execute('ALTER TABLE channels ADD COLUMN telegram_id INTEGER')
        except sqlite3.OperationalError:
            pass  # ستون قبلاً وجود دارد
        
        try:
            cursor.execute('ALTER TABLE channels ADD COLUMN previous_telegram_id INTEGER')
        except sqlite3.OperationalError:
            pass  # ستون قبلاً وجود دارد
        
        try:
            cursor.execute('ALTER TABLE channels ADD COLUMN is_member BOOLEAN DEFAULT 0')
        except sqlite3.OperationalError:
            pass  # ستون قبلاً وجود دارد
        
        # جدول تاریخچه آمار
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channel_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                member_count INTEGER DEFAULT 0,
                views_count INTEGER DEFAULT 0,
                posts_count INTEGER DEFAULT 0,
                member_change INTEGER DEFAULT 0,
                views_change INTEGER DEFAULT 0,
                posts_change INTEGER DEFAULT 0,
                positive_change INTEGER DEFAULT 0,
                FOREIGN KEY (channel_id) REFERENCES channels(id)
            )
        ''')
        
        # جدول ادمین‌ها
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول دسته‌بندی‌ها
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_channel(self, username_or_link: str, title: str = "", added_by: int = None, invite_link: str = None, category: str = None) -> bool:
        """افزودن کانال جدید (پشتیبانی از username و invite link)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # افزودن دسته‌بندی به جدول categories (اگر وجود دارد)
            if category:
                try:
                    cursor.execute('''
                        INSERT OR IGNORE INTO categories (name)
                        VALUES (?)
                    ''', (category,))
                except Exception as e:
                    print(f"خطا در افزودن دسته‌بندی '{category}' به جدول categories: {e}")
                    # ادامه می‌دهیم حتی اگر خطا داد
            
            # تشخیص اینکه آیا invite link است یا username
            is_invite_link = username_or_link.startswith('http') or username_or_link.startswith('t.me/+') or username_or_link.startswith('+')
            
            if is_invite_link:
                # برای invite link، از خود لینک به عنوان username استفاده می‌کنیم
                username = username_or_link
                if not invite_link:
                    invite_link = username_or_link
            else:
                username = username_or_link.lstrip('@')
            
            # چک کردن اینکه آیا کانال قبلاً وجود داشته (حتی اگر غیرفعال باشد)
            cursor.execute('SELECT id, is_active FROM channels WHERE username = ?', (username,))
            existing = cursor.fetchone()
            
            if existing:
                # اگر کانال وجود دارد و غیرفعال است، آن را فعال می‌کنیم
                channel_id = dict(existing)['id']
                is_active = dict(existing)['is_active']
                
                if not is_active:
                    cursor.execute('''
                        UPDATE channels 
                        SET is_active = 1, 
                            title = COALESCE(?, title), 
                            invite_link = COALESCE(?, invite_link),
                            category = COALESCE(?, category),
                            added_by = COALESCE(?, added_by)
                        WHERE id = ?
                    ''', (title if title else None, invite_link, category, added_by, channel_id))
                    conn.commit()
                    conn.close()
                    return True
                else:
                    # کانال قبلاً فعال است
                    conn.close()
                    return False  # کانال قبلاً اضافه شده
            else:
                # کانال جدید است
                cursor.execute('''
                    INSERT INTO channels (username, title, invite_link, category, added_by)
                    VALUES (?, ?, ?, ?, ?)
                ''', (username, title, invite_link, category, added_by))
                
                conn.commit()
                success = cursor.rowcount > 0
                conn.close()
                return success
        except Exception as e:
            print(f"خطا در افزودن کانال: {e}")
            conn.close()
            return False
    
    def remove_channel(self, username: str) -> bool:
        """حذف کانال (is_active = 0، is_member بدون تغییر باقی می‌ماند تا بعد از leave تنظیم شود)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        username = username.lstrip('@')
        # فقط is_active را 0 می‌کنیم، is_member را نگه می‌داریم تا بعد از leave تنظیم شود
        cursor.execute('UPDATE channels SET is_active = 0 WHERE username = ?', (username,))
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
    
    def get_active_channels(self) -> List[Dict]:
        """دریافت لیست کانال‌های فعال که عضو هستیم (برای بررسی آمار)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, username, title, invite_link, telegram_id, is_member 
            FROM channels 
            WHERE is_active = 1 AND is_member = 1
            ORDER BY added_at DESC
        ''')
        
        channels = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return channels
    
    def get_all_active_channels(self) -> List[Dict]:
        """دریافت لیست همه کانال‌های فعال (برای نمایش در لیست)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, username, title, invite_link, telegram_id, is_member, category 
            FROM channels 
            WHERE is_active = 1
            ORDER BY added_at DESC
        ''')
        
        channels = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return channels
    
    def get_channels_to_leave(self) -> List[Dict]:
        """دریافت لیست کانال‌های غیرفعال که باید از آن‌ها خارج شد (is_active = 0 و is_member = 1)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, username, title, invite_link, telegram_id 
            FROM channels 
            WHERE is_active = 0 AND is_member = 1
            ORDER BY added_at DESC
        ''')
        
        channels = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return channels
    
    def set_channel_member_status(self, channel_id: int, is_member: bool) -> bool:
        """تنظیم وضعیت عضویت کانال"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE channels 
                SET is_member = ? 
                WHERE id = ?
            ''', (1 if is_member else 0, channel_id))
            
            conn.commit()
            success = cursor.rowcount > 0
            conn.close()
            return success
        except Exception as e:
            print(f"خطا در تنظیم وضعیت عضویت: {e}")
            conn.close()
            return False
    
    def mark_channel_left(self, channel_id: int):
        """علامت‌گذاری کانال که از آن خارج شدیم (حذف telegram_id)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('UPDATE channels SET telegram_id = NULL WHERE id = ?', (channel_id,))
            conn.commit()
        except Exception as e:
            print(f"خطا در علامت‌گذاری کانال: {e}")
        finally:
            conn.close()
    
    def update_channel_telegram_id(self, channel_id: int, telegram_id: int):
        """به‌روزرسانی telegram_id کانال و ذخیره ID قبلی اگر تغییر کرده"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # دریافت telegram_id فعلی
            cursor.execute('SELECT telegram_id FROM channels WHERE id = ?', (channel_id,))
            current_id = cursor.fetchone()
            
            if current_id and current_id[0] and current_id[0] != telegram_id:
                # ID تغییر کرده، ذخیره ID قبلی
                cursor.execute('''
                    UPDATE channels 
                    SET telegram_id = ?, previous_telegram_id = ? 
                    WHERE id = ?
                ''', (telegram_id, current_id[0], channel_id))
            else:
                # اولین بار است یا تغییر نکرده
                cursor.execute('''
                    UPDATE channels 
                    SET telegram_id = ? 
                    WHERE id = ?
                ''', (telegram_id, channel_id))
            
            conn.commit()
        except Exception as e:
            print(f"خطا در به‌روزرسانی telegram_id: {e}")
        finally:
            conn.close()
    
    def reset_channel_stats(self, channel_id: int = None) -> bool:
        """صفر کردن آمار شمارش کانال(ها) - حفظ title, is_active, member_count فعلی"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            if channel_id:
                # صفر کردن آمار یک کانال خاص
                # دریافت آخرین member_count
                cursor.execute('''
                    SELECT member_count FROM channel_stats 
                    WHERE channel_id = ? 
                    ORDER BY recorded_at DESC 
                    LIMIT 1
                ''', (channel_id,))
                result = cursor.fetchone()
                current_member_count = result[0] if result else 0
                
                # صفر کردن تغییرات در آخرین رکورد
                cursor.execute('''
                    UPDATE channel_stats 
                    SET member_change = 0,
                        views_change = 0,
                        posts_change = 0,
                        positive_change = 0
                    WHERE id = (
                        SELECT id FROM channel_stats 
                        WHERE channel_id = ? 
                        ORDER BY recorded_at DESC 
                        LIMIT 1
                    )
                ''', (channel_id,))
                
                conn.commit()
                conn.close()
                return True
            else:
                # صفر کردن آمار همه کانال‌ها
                cursor.execute('''
                    UPDATE channel_stats 
                    SET member_change = 0,
                        views_change = 0,
                        posts_change = 0,
                        positive_change = 0
                ''')
                
                conn.commit()
                conn.close()
                return True
        except Exception as e:
            print(f"خطا در Reset آمار: {e}")
            conn.close()
            return False
    
    def get_all_categories(self) -> List[str]:
        """دریافت لیست تمام دسته‌بندی‌های موجود (فقط از جدول categories)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT name 
            FROM categories 
            ORDER BY name
        ''')
        
        categories = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        return categories
    
    def sync_categories_from_channels(self) -> int:
        """همگام‌سازی دسته‌بندی‌های موجود در channels با جدول categories
        
        این متد همه دسته‌بندی‌های منحصر به فرد از جدول channels را می‌خواند
        و آن‌هایی که در جدول categories وجود ندارند را اضافه می‌کند.
        
        Returns:
            تعداد دسته‌بندی‌های جدیدی که اضافه شدند
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # دریافت همه دسته‌بندی‌های منحصر به فرد از channels
            cursor.execute('''
                SELECT DISTINCT category 
                FROM channels 
                WHERE category IS NOT NULL AND category != ''
            ''')
            
            categories_from_channels = [row[0] for row in cursor.fetchall()]
            
            # دریافت دسته‌بندی‌های موجود در جدول categories
            cursor.execute('SELECT name FROM categories')
            existing_categories = {row[0] for row in cursor.fetchall()}
            
            # افزودن دسته‌بندی‌های جدید
            added_count = 0
            for category in categories_from_channels:
                if category not in existing_categories:
                    try:
                        cursor.execute('''
                            INSERT OR IGNORE INTO categories (name)
                            VALUES (?)
                        ''', (category,))
                        added_count += 1
                    except Exception as e:
                        print(f"خطا در افزودن دسته‌بندی '{category}': {e}")
            
            conn.commit()
            conn.close()
            return added_count
        except Exception as e:
            print(f"خطا در همگام‌سازی دسته‌بندی‌ها: {e}")
            conn.close()
            return 0
    
    def cleanup_orphaned_categories(self) -> int:
        """حذف دسته‌بندی‌هایی که هیچ کانال فعالی ندارند
        
        Returns:
            تعداد دسته‌بندی‌های حذف شده
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # دریافت همه دسته‌بندی‌ها
            cursor.execute('SELECT name FROM categories')
            all_categories = [row[0] for row in cursor.fetchall()]
            
            # دریافت دسته‌بندی‌هایی که حداقل یک کانال فعال دارند
            cursor.execute('''
                SELECT DISTINCT category 
                FROM channels 
                WHERE is_active = 1 
                AND category IS NOT NULL 
                AND category != ''
            ''')
            categories_with_channels = {row[0] for row in cursor.fetchall()}
            
            # حذف دسته‌بندی‌های بدون کانال فعال
            removed_count = 0
            for category in all_categories:
                if category not in categories_with_channels:
                    try:
                        cursor.execute('DELETE FROM categories WHERE name = ?', (category,))
                        removed_count += 1
                    except Exception as e:
                        print(f"خطا در حذف دسته‌بندی '{category}': {e}")
            
            conn.commit()
            conn.close()
            return removed_count
        except Exception as e:
            print(f"خطا در پاکسازی دسته‌بندی‌های بدون استفاده: {e}")
            conn.close()
            return 0
    
    def get_categories_with_active_channels(self) -> List[str]:
        """دریافت لیست دسته‌بندی‌هایی که حداقل یک کانال فعال دارند"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # دریافت دسته‌بندی‌های کانال‌های فعال
        cursor.execute('''
            SELECT DISTINCT category 
            FROM channels 
            WHERE is_active = 1 
            AND category IS NOT NULL 
            AND category != ''
            ORDER BY category
        ''')
        
        categories = [row[0] for row in cursor.fetchall()]
        conn.close()
        return categories
    
    def add_category(self, category_name: str) -> bool:
        """افزودن دسته‌بندی جدید به جدول categories"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO categories (name)
                VALUES (?)
            ''', (category_name,))
            
            conn.commit()
            success = cursor.rowcount > 0
            conn.close()
            return success
        except Exception as e:
            print(f"خطا در افزودن دسته‌بندی: {e}")
            conn.close()
            return False
    
    def delete_category_from_table(self, category_name: str) -> bool:
        """حذف دسته‌بندی از جدول categories"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('DELETE FROM categories WHERE name = ?', (category_name,))
            conn.commit()
            success = cursor.rowcount > 0
            conn.close()
            return success
        except Exception as e:
            print(f"خطا در حذف دسته‌بندی: {e}")
            conn.close()
            return False
    
    def get_channels_count_by_category(self, category: str) -> int:
        """شمارش تعداد کانال‌های یک دسته‌بندی"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) 
            FROM channels 
            WHERE category = ? AND is_active = 1
        ''', (category,))
        
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    def delete_category(self, category: str) -> bool:
        """حذف دسته‌بندی (تبدیل همه کانال‌های آن به NULL و حذف از جدول categories)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # تبدیل category کانال‌ها به NULL
            cursor.execute('''
                UPDATE channels 
                SET category = NULL 
                WHERE category = ?
            ''', (category,))
            
            # حذف از جدول categories
            cursor.execute('DELETE FROM categories WHERE name = ?', (category,))
            
            conn.commit()
            success = cursor.rowcount > 0
            conn.close()
            return success
        except Exception as e:
            print(f"خطا در حذف دسته‌بندی: {e}")
            conn.close()
            return False
    
    def get_channel_by_username(self, username: str) -> Optional[Dict]:
        """دریافت اطلاعات کانال با یوزرنیم یا invite link"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # برای username معمولی، @ را حذف می‌کنیم
        # برای invite link، بدون تغییر استفاده می‌کنیم
        if username.startswith('http') or username.startswith('t.me/+') or username.startswith('+'):
            # این یک invite link است، بدون تغییر استفاده می‌کنیم
            search_username = username
        else:
            # این یک username است، @ را حذف می‌کنیم
            search_username = username.lstrip('@')
        
        cursor.execute('SELECT * FROM channels WHERE username = ?', (search_username,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def get_channel_by_id(self, channel_id: int) -> Optional[Dict]:
        """دریافت اطلاعات کانال با ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM channels WHERE id = ?', (channel_id,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def get_last_stats(self, channel_id: int) -> Optional[Dict]:
        """دریافت آخرین آمار ثبت شده برای یک کانال"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM channel_stats 
            WHERE channel_id = ? 
            ORDER BY recorded_at DESC 
            LIMIT 1
        ''', (channel_id,))
        
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def get_yesterday_stats(self, channel_id: int) -> Optional[Dict]:
        """دریافت آمار دیروز برای یک کانال"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # دریافت آخرین آمار امروز
        cursor.execute('''
            SELECT * FROM channel_stats 
            WHERE channel_id = ? 
            ORDER BY recorded_at DESC 
            LIMIT 1
        ''', (channel_id,))
        
        today_stat = cursor.fetchone()
        if not today_stat:
            conn.close()
            return None
        
        today_stat = dict(today_stat)
        today_date = today_stat['recorded_at']
        
        # تبدیل تاریخ امروز به datetime
        try:
            if isinstance(today_date, str):
                today_dt = datetime.fromisoformat(today_date.replace('Z', '+00:00'))
            else:
                today_dt = today_date
            yesterday_dt = today_dt - timedelta(days=1)
            yesterday_date = yesterday_dt.strftime('%Y-%m-%d')
        except:
            conn.close()
            return None
        
        # دریافت آمار دیروز
        cursor.execute('''
            SELECT * FROM channel_stats 
            WHERE channel_id = ? 
            AND date(recorded_at) = date(?)
            ORDER BY recorded_at DESC 
            LIMIT 1
        ''', (channel_id, yesterday_date))
        
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def get_first_stats(self, channel_id: int) -> Optional[Dict]:
        """دریافت اولین آمار ثبت شده برای یک کانال"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM channel_stats 
            WHERE channel_id = ? 
            ORDER BY recorded_at ASC 
            LIMIT 1
        ''', (channel_id,))
        
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def add_stats(self, channel_id: int, member_count: int = 0, views_count: int = 0, 
                  posts_count: int = 0) -> bool:
        """افزودن آمار جدید برای کانال"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # دریافت آخرین آمار
        last_stats = self.get_last_stats(channel_id)
        
        # محاسبه تغییرات
        member_change = member_count - (last_stats['member_count'] if last_stats else 0)
        views_change = views_count - (last_stats['views_count'] if last_stats else 0)
        posts_change = posts_count - (last_stats['posts_count'] if last_stats else 0)
        positive_change = 1 if member_change > 0 or views_change > 0 else 0
        
        try:
            cursor.execute('''
                INSERT INTO channel_stats 
                (channel_id, member_count, views_count, posts_count, 
                 member_change, views_change, posts_change, positive_change)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (channel_id, member_count, views_count, posts_count,
                  member_change, views_change, posts_change, positive_change))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"خطا در ثبت آمار: {e}")
            conn.close()
            return False
    
    def get_all_stats(self, channel_id: int = None, limit: int = 100) -> List[Dict]:
        """دریافت آمار کانال‌ها"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if channel_id:
            cursor.execute('''
                SELECT 
                    c.id,
                    c.username,
                    c.title,
                    cs.recorded_at,
                    cs.member_count,
                    cs.views_count,
                    cs.member_change,
                    cs.views_change,
                    cs.positive_change
                FROM channel_stats cs
                JOIN channels c ON cs.channel_id = c.id
                WHERE c.id = ? AND c.is_active = 1
                ORDER BY cs.recorded_at DESC
                LIMIT ?
            ''', (channel_id, limit))
        else:
            # آخرین آمار هر کانال
            cursor.execute('''
                SELECT 
                    c.id,
                    c.username,
                    c.title,
                    c.category,
                    c.telegram_id,
                    c.previous_telegram_id,
                    cs.recorded_at,
                    COALESCE(cs.member_count, 0) as member_count,
                    COALESCE(cs.views_count, 0) as views_count,
                    COALESCE(cs.member_change, 0) as member_change,
                    COALESCE(cs.views_change, 0) as views_change,
                    COALESCE(cs.positive_change, 0) as positive_change
                FROM channels c
                LEFT JOIN (
                    SELECT 
                        channel_id,
                        MAX(recorded_at) as max_date
                    FROM channel_stats
                    GROUP BY channel_id
                ) latest ON c.id = latest.channel_id
                LEFT JOIN channel_stats cs ON cs.channel_id = c.id 
                    AND cs.recorded_at = latest.max_date
                WHERE c.is_active = 1
                ORDER BY COALESCE(c.category, ''), COALESCE(cs.recorded_at, c.added_at) DESC
            ''')
        
        stats = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return stats
    
    def add_admin(self, user_id: int, username: str = "") -> bool:
        """افزودن ادمین"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO admins (user_id, username)
                VALUES (?, ?)
            ''', (user_id, username))
            
            conn.commit()
            success = cursor.rowcount > 0
            conn.close()
            return success
        except Exception as e:
            print(f"خطا در افزودن ادمین: {e}")
            conn.close()
            return False
    
    def is_admin(self, user_id: int) -> bool:
        """بررسی ادمین بودن کاربر"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,))
        result = cursor.fetchone() is not None
        conn.close()
        return result

