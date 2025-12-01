"""
ربات Telethon برای رصد کانال‌ها و ثبت آمار
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, UsernameNotOccupiedError, InviteHashExpiredError, InviteHashInvalidError
from telethon.tl.functions.channels import GetFullChannelRequest, JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
from database import Database


class ChannelMonitor:
    def __init__(self):
        self.config_file = 'config.json'
        self.session_file = 'new'
        self.client = None
        self.config = self.load_config()
        self.db = Database()
        # استفاده از دایرکتوری data برای فایل‌های flag (مشترک بین containers)
        self.data_dir = os.path.join(os.getcwd(), 'data')
        os.makedirs(self.data_dir, exist_ok=True)
        self.trigger_flag_file = os.path.join(self.data_dir, 'trigger_check.flag')
        self.notification_file = 'check_notification.json'
        self.join_flag_file = os.path.join(self.data_dir, 'join_channel.flag')
        self.leave_flag_file = os.path.join(self.data_dir, 'leave_channel.flag')
        
    def load_config(self):
        """بارگذاری تنظیمات از فایل"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"خطا در خواندن فایل تنظیمات: {e}")
                return {}
        return {}
    
    async def setup_client(self):
        """تنظیم و اتصال کلاینت تلگرام"""
        # دریافت api_id و api_hash از کاربر اگر وجود نداشته باشد
        if not self.config.get('api_id') or not self.config.get('api_hash'):
            print("=== تنظیمات اولیه ===")
            api_id = input("API ID خود را وارد کنید: ").strip()
            api_hash = input("API Hash خود را وارد کنید: ").strip()
            
            if not api_id or not api_hash:
                print("خطا: API ID و API Hash ضروری هستند!")
                sys.exit(1)
            
            self.config['api_id'] = api_id
            self.config['api_hash'] = api_hash
            self.save_config()
        
        try:
            api_id = int(self.config['api_id'])
            api_hash = self.config['api_hash']
        except (ValueError, KeyError):
            print("خطا: API ID یا API Hash نامعتبر است!")
            sys.exit(1)
        
        # ایجاد کلاینت
        self.client = TelegramClient(self.session_file, api_id, api_hash)
        
        # اتصال
        await self.client.connect()
        
        # بررسی احراز هویت
        if not await self.client.is_user_authorized():
            print("\n=== احراز هویت ===")
            await self.authenticate()
        
        # تست اتصال
        me = await self.client.get_me()
        print(f"\n✅ با موفقیت به حساب '{me.first_name}' متصل شدید!")
        return True
    
    def save_config(self):
        """ذخیره تنظیمات در فایل"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
    
    async def authenticate(self):
        """احراز هویت کاربر"""
        phone = input("شماره تلفن خود را وارد کنید (با کد کشور مثلا +989123456789): ").strip()
        
        try:
            await self.client.send_code_request(phone)
        except Exception as e:
            print(f"خطا در ارسال کد: {e}")
            sys.exit(1)
        
        code = input("کد ارسال شده را وارد کنید: ").strip()
        
        try:
            await self.client.sign_in(phone, code)
        except SessionPasswordNeededError:
            # نیاز به رمز دو مرحله‌ای
            password = input("رمز دو مرحله‌ای خود را وارد کنید: ").strip()
            await self.client.sign_in(password=password)
        except PhoneCodeInvalidError:
            print("کد وارد شده نامعتبر است!")
            sys.exit(1)
        except Exception as e:
            print(f"خطا در احراز هویت: {e}")
            sys.exit(1)
    
    def extract_invite_hash(self, invite_link: str) -> str:
        """استخراج hash از لینک invite"""
        # حذف فاصله‌ها و کاراکترهای اضافی
        original_link = invite_link
        invite_link = invite_link.strip()
        
        # اگر با + شروع می‌شود، + را حذف می‌کنیم
        if invite_link.startswith('+'):
            invite_link = invite_link[1:]
        
        hash_part = None
        
        # اگر با http شروع می‌شود
        if invite_link.startswith('http'):
            # استخراج قسمت بعد از آخرین /
            if '/+' in invite_link:
                # برای https://t.me/+ABC123
                hash_part = invite_link.split('/+')[-1]
            elif invite_link.endswith('/'):
                # اگر با / تمام می‌شود
                hash_part = invite_link.rstrip('/').split('/')[-1]
            else:
                # استخراج قسمت آخر
                hash_part = invite_link.split('/')[-1]
        elif invite_link.startswith('t.me/'):
            # برای t.me/+ABC123 یا t.me/ABC123
            if '/+' in invite_link:
                hash_part = invite_link.split('/+')[-1]
            else:
                hash_part = invite_link.split('/')[-1]
        else:
            # اگر فقط hash است
            hash_part = invite_link
        
        # حذف + از ابتدا (اگر وجود دارد)
        hash_part = hash_part.lstrip('+')
        
        # حذف کاراکترهای اضافی از انتها (مثل ? یا #)
        hash_part = hash_part.split('?')[0].split('#')[0]
        
        print(f"🔍 استخراج hash: '{original_link}' -> '{hash_part}'")
        
        return hash_part
    
    async def ensure_connected(self):
        """اطمینان از اتصال کلاینت - اگر قطع شده باشد، دوباره متصل می‌شود"""
        try:
            if not self.client:
                print("⚠️ کلاینت وجود ندارد، در حال تنظیم...")
                await self.setup_client()
                return
            
            # بررسی اتصال
            if not self.client.is_connected():
                print("⚠️ کلاینت قطع شده است، در حال اتصال مجدد...")
                await self.client.connect()
                
                # بررسی احراز هویت
                if not await self.client.is_user_authorized():
                    print("⚠️ کاربر مجاز نیست، نیاز به احراز هویت مجدد")
                    await self.authenticate()
                else:
                    # تست اتصال با get_me
                    try:
                        me = await self.client.get_me()
                        print(f"✅ کلاینت دوباره متصل شد (کاربر: {me.first_name})")
                    except Exception as e:
                        print(f"⚠️ خطا در تست اتصال: {e}")
                        # اگر تست ناموفق بود، دوباره setup کنیم
                        await self.setup_client()
        except Exception as e:
            print(f"❌ خطا در اتصال مجدد کلاینت: {e}")
            import traceback
            traceback.print_exc()
            # تلاش برای تنظیم مجدد کلاینت
            try:
                print("🔄 تلاش برای تنظیم مجدد کلاینت...")
                await self.setup_client()
            except Exception as e2:
                print(f"❌ خطا در تنظیم مجدد کلاینت: {e2}")
                import traceback
                traceback.print_exc()
    
    async def join_channel(self, username_or_link: str) -> tuple:
        """عضویت در کانال و برگرداندن (success, entity, telegram_id)"""
        try:
            # اطمینان از اتصال قبل از استفاده
            await self.ensure_connected()
            
            entity = None
            telegram_id = None
            
            # بررسی اینکه آیا این یک invite link است
            if username_or_link.startswith('http') or username_or_link.startswith('t.me/+') or username_or_link.startswith('+'):
                # این یک invite link است
                try:
                    # استخراج hash از لینک با استفاده از تابع کمکی
                    hash_part = self.extract_invite_hash(username_or_link)
                    print(f"🔍 Hash استخراج شده از لینک: {hash_part}")
                    
                    # چک کردن invite
                    from telethon.tl.types import ChatInvite, ChatInviteAlready
                    from telethon.errors import InviteHashExpiredError, InviteHashInvalidError
                    
                    try:
                        invite = await self.client(CheckChatInviteRequest(hash_part))
                    except InviteHashExpiredError as e:
                        print(f"⚠️ لینک invite منقضی شده است: {username_or_link}")
                        print(f"   خطا: {e}")
                        return (False, None, None)
                    except InviteHashInvalidError as e:
                        print(f"⚠️ لینک invite نامعتبر است: {username_or_link}")
                        print(f"   خطا: {e}")
                        return (False, None, None)
                    except Exception as e:
                        error_msg = str(e).lower()
                        if 'expired' in error_msg:
                            print(f"⚠️ لینک invite منقضی شده است: {username_or_link}")
                        elif 'invalid' in error_msg or 'not valid' in error_msg:
                            print(f"⚠️ لینک invite نامعتبر است: {username_or_link}")
                        else:
                            print(f"❌ خطا در چک کردن invite: {e}")
                            import traceback
                            traceback.print_exc()
                        return (False, None, None)
                    
                    # اگر نیاز به join دارد
                    if isinstance(invite, ChatInvite):
                        print(f"📥 در حال پیوستن به کانال با invite link...")
                        try:
                            # پیوستن به کانال
                            await self.client(ImportChatInviteRequest(hash_part))
                            # بعد از join، دوباره چک می‌کنیم
                            invite = await self.client(CheckChatInviteRequest(hash_part))
                        except Exception as e:
                            print(f"❌ خطا در پیوستن به کانال: {e}")
                            import traceback
                            traceback.print_exc()
                            return (False, None, None)
                    
                    # دریافت entity
                    if isinstance(invite, ChatInviteAlready):
                        entity = invite.chat
                        telegram_id = entity.id if hasattr(entity, 'id') else None
                        print(f"✅ با موفقیت به کانال پیوستیم (از قبل عضو بودیم)")
                    elif isinstance(invite, ChatInvite):
                        # اگر هنوز ChatInvite است، یعنی join موفق نبود
                        print(f"⚠️ نتوانستیم به کانال با لینک {username_or_link} بپیوندیم")
                        return (False, None, None)
                    else:
                        print(f"⚠️ نوع invite نامعتبر: {type(invite)}")
                        return (False, None, None)
                except Exception as e:
                    error_msg = str(e).lower()
                    print(f"❌ خطا در پیوستن به کانال با لینک {username_or_link}: {e}")
                    import traceback
                    traceback.print_exc()
                    return (False, None, None)
            else:
                # این یک username است
                username = username_or_link.lstrip('@')
                try:
                    entity = await self.client.get_entity(username)
                    telegram_id = entity.id if hasattr(entity, 'id') else None
                    
                    # پیوستن به کانال (اگر عضو نیستیم)
                    try:
                        await self.client(JoinChannelRequest(entity))
                    except Exception as e:
                        # ممکن است قبلاً عضو باشیم یا خطای دیگری داشته باشیم
                        error_msg = str(e).lower()
                        if 'already' in error_msg or 'participant' in error_msg:
                            # قبلاً عضو هستیم، مشکلی نیست
                            pass
                        else:
                            print(f"⚠️ خطا در پیوستن به کانال @{username}: {e}")
                except Exception as e:
                    print(f"❌ خطا در دریافت کانال @{username}: {e}")
                    return (False, None, None)
            
            if entity:
                return (True, entity, telegram_id)
            else:
                return (False, None, None)
        except Exception as e:
            print(f"❌ خطا در join_channel: {e}")
            import traceback
            traceback.print_exc()
            return (False, None, None)
    
    async def get_channel_stats(self, username_or_link: str, channel_id: int = None) -> dict:
        """دریافت آمار کانال (پشتیبانی از username و invite link)"""
        try:
            # اطمینان از اتصال قبل از استفاده
            await self.ensure_connected()
            
            entity = None
            
            # اگر channel_id داریم، ابتدا سعی می‌کنیم از telegram_id استفاده کنیم
            if channel_id:
                channel_info = self.db.get_channel_by_id(channel_id)
                if channel_info and channel_info.get('telegram_id'):
                    try:
                        entity = await self.client.get_entity(channel_info['telegram_id'])
                    except:
                        pass  # اگر خطا داد، از username استفاده می‌کنیم
            
            # اگر entity پیدا نشد، از username_or_link استفاده می‌کنیم
            if not entity:
                # بررسی اینکه آیا این یک invite link است
                if username_or_link.startswith('http') or username_or_link.startswith('t.me/+') or username_or_link.startswith('+'):
                    # این یک invite link است
                    try:
                        # استخراج hash از لینک با استفاده از تابع کمکی
                        hash_part = self.extract_invite_hash(username_or_link)
                        print(f"🔍 Hash استخراج شده از لینک: {hash_part}")
                        
                        # چک کردن invite
                        from telethon.tl.types import ChatInviteAlready
                        from telethon.errors import InviteHashExpiredError, InviteHashInvalidError
                        
                        try:
                            invite = await self.client(CheckChatInviteRequest(hash_part))
                        except InviteHashExpiredError as e:
                            print(f"⚠️ لینک invite منقضی شده است: {username_or_link}")
                            print(f"   خطا: {e}")
                            return None
                        except InviteHashInvalidError as e:
                            print(f"⚠️ لینک invite نامعتبر است: {username_or_link}")
                            print(f"   خطا: {e}")
                            return None
                        except Exception as e:
                            error_msg = str(e).lower()
                            if 'expired' in error_msg:
                                print(f"⚠️ لینک invite منقضی شده است: {username_or_link}")
                            elif 'invalid' in error_msg or 'not valid' in error_msg:
                                print(f"⚠️ لینک invite نامعتبر است: {username_or_link}")
                            else:
                                print(f"❌ خطا در چک کردن invite: {e}")
                                import traceback
                                traceback.print_exc()
                            return None
                        
                        # دریافت entity
                        if isinstance(invite, ChatInviteAlready):
                            entity = invite.chat
                        else:
                            print(f"⚠️ لینک invite نامعتبر است: {username_or_link}")
                            return None
                    except Exception as e:
                        error_msg = str(e).lower()
                        if 'expired' in error_msg or 'not valid' in error_msg:
                            print(f"⚠️ لینک invite منقضی شده یا نامعتبر است: {username_or_link}")
                        else:
                            print(f"❌ خطا در دریافت کانال با لینک {username_or_link}: {e}")
                        return None
                else:
                    # این یک username است
                    username = username_or_link.lstrip('@')
                    try:
                        entity = await self.client.get_entity(username)
                    except Exception as e:
                        print(f"❌ خطا در دریافت کانال @{username}: {e}")
                        return None
            
            if not entity:
                return None
            
            # بررسی اینکه entity یک کانال است یا نه (نه ربات یا کاربر)
            from telethon.tl.types import Channel, ChannelForbidden, Chat, ChatForbidden
            is_channel = isinstance(entity, (Channel, ChannelForbidden, Chat, ChatForbidden))
            
            if not is_channel:
                # این یک ربات یا کاربر است، نه کانال
                print(f"⚠️ {username_or_link} یک کانال نیست (احتمالاً ربات یا کاربر است)")
                return None
            
            # دریافت اطلاعات کامل کانال
            full_info = await self.client(GetFullChannelRequest(entity))
            
            # دریافت username واقعی (اگر موجود باشد)
            channel_username = ''
            if hasattr(entity, 'username') and entity.username:
                channel_username = entity.username
            elif hasattr(entity, 'id'):
                # برای کانال‌های پرایوت، از ID استفاده می‌کنیم
                channel_username = f"private_{entity.id}"
            
            stats = {
                'title': entity.title,
                'member_count': full_info.full_chat.participants_count or 0,
                'views_count': 0,  # این اطلاعات در API موجود نیست
                'posts_count': 0,  # نیاز به محاسبه جداگانه دارد
                'username': channel_username or username_or_link,
                'telegram_id': entity.id if hasattr(entity, 'id') else None
            }
            
            return stats
        except UsernameNotOccupiedError:
            print(f"❌ کانال {username_or_link} یافت نشد!")
            return None
        except Exception as e:
            print(f"❌ خطا در دریافت آمار کانال {username_or_link}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def monitor_channels(self, triggered_by_user_id=None):
        """رصد کانال‌ها و ثبت آمار"""
        # ابتدا سعی می‌کنیم به کانال‌هایی که عضو نیستیم بپیوندیم
        all_channels = self.db.get_all_active_channels()
        channels_to_join = [ch for ch in all_channels if not ch.get('is_member', 0)]
        
        if channels_to_join:
            print(f"\n➕ تلاش برای پیوستن به {len(channels_to_join)} کانال...")
            for channel in channels_to_join:
                channel_id = channel['id']
                username = channel['username']
                invite_link = channel.get('invite_link')
                channel_identifier = invite_link if invite_link else username
                print(f"🔄 در حال پیوستن به کانال: {channel_identifier}")
                await self.process_join_channel(channel_id, channel_identifier)
                await asyncio.sleep(1)  # تاخیر کوتاه بین join ها
        
        # حالا فقط کانال‌هایی که عضو هستیم را بررسی می‌کنیم
        channels = self.db.get_active_channels()
        start_time = datetime.now()
        
        if not channels:
            print("⚠️ هیچ کانال فعالی یافت نشد (یا هنوز عضو نشده‌ایم)!")
            # ایجاد فایل notification برای اطلاع‌رسانی
            self.create_notification(triggered_by_user_id, start_time, 0, False)
            return
        
        print(f"\n📊 بررسی {len(channels)} کانال...")
        
        successful_checks = 0
        for channel in channels:
            username = channel['username']
            channel_id = channel['id']
            invite_link = channel.get('invite_link')  # ممکن است None باشد
            
            # استفاده از invite_link اگر موجود باشد، در غیر این صورت username
            channel_identifier = invite_link if invite_link else username
            
            display_name = invite_link if invite_link else f"@{username}"
            print(f"\n🔍 بررسی کانال: {display_name}")
            
            stats = await self.get_channel_stats(channel_identifier, channel_id)
            
            if stats:
                # اطمینان از اینکه is_member = 1 است (اگر توانستیم آمار بگیریم یعنی عضو هستیم)
                self.db.set_channel_member_status(channel_id, True)
                
                # به‌روزرسانی عنوان در صورت تغییر
                if stats['title'] and stats['title'] != channel.get('title'):
                    conn = self.db.get_connection()
                    cursor = conn.cursor()
                    cursor.execute('UPDATE channels SET title = ? WHERE id = ?', 
                                 (stats['title'], channel_id))
                    conn.commit()
                    conn.close()
                
                # به‌روزرسانی telegram_id اگر موجود باشد
                if 'telegram_id' in stats and stats['telegram_id']:
                    self.db.update_channel_telegram_id(channel_id, stats['telegram_id'])
                
                # ثبت آمار
                success = self.db.add_stats(
                    channel_id=channel_id,
                    member_count=stats['member_count'],
                    views_count=stats['views_count'],
                    posts_count=stats['posts_count']
                )
                
                if success:
                    successful_checks += 1
                    last_stats = self.db.get_last_stats(channel_id)
                    print(f"✅ آمار ثبت شد:")
                    print(f"   - اعضا: {stats['member_count']:,}")
                    if last_stats and last_stats.get('member_change'):
                        change = last_stats['member_change']
                        sign = "+" if change > 0 else ""
                        print(f"   - تغییر: {sign}{change:,}")
                else:
                    print(f"❌ خطا در ثبت آمار")
            else:
                # اگر نتوانستیم آمار بگیریم، ممکن است عضو نباشیم یا کانال نامعتبر باشد
                print(f"⚠️ نتوانستیم آمار کانال {display_name} را دریافت کنیم")
                # اگر کانال یک ربات است یا نامعتبر است، is_member را 0 می‌کنیم
                # (اما is_active را نگه می‌داریم تا کاربر بتواند آن را ببیند)
                self.db.set_channel_member_status(channel_id, False)
            
            # تاخیر کوتاه بین درخواست‌ها
            await asyncio.sleep(2)
        
        # بررسی کانال‌های غیرفعال برای خروج
        await self.leave_inactive_channels()
        
        # ایجاد فایل notification بعد از اتمام بررسی
        end_time = datetime.now()
        print(f"\n📝 در حال ایجاد notification برای user_id={triggered_by_user_id}...")
        self.create_notification(triggered_by_user_id, start_time, successful_checks, True)
        print(f"✅ Notification ایجاد شد برای user_id={triggered_by_user_id}, channels={successful_checks}")
    
    async def leave_inactive_channels(self):
        """خروج از کانال‌های غیرفعال"""
        # اطمینان از اتصال قبل از استفاده
        await self.ensure_connected()
        
        channels_to_leave = self.db.get_channels_to_leave()
        
        if not channels_to_leave:
            return
        
        print(f"\n🚪 بررسی {len(channels_to_leave)} کانال غیرفعال برای خروج...")
        
        for channel in channels_to_leave:
            telegram_id = channel.get('telegram_id')
            username = channel['username']
            channel_id = channel['id']
            invite_link = channel.get('invite_link')
            
            try:
                entity = None
                
                # تلاش برای دریافت entity
                if telegram_id:
                    try:
                        entity = await self.client.get_entity(telegram_id)
                    except:
                        pass
                
                # اگر با telegram_id نشد، از username یا invite_link استفاده می‌کنیم
                if not entity:
                    if invite_link and (invite_link.startswith('http') or invite_link.startswith('t.me/+') or invite_link.startswith('+')):
                        # این یک invite link است
                        try:
                            # استخراج hash از لینک با استفاده از تابع کمکی
                            hash_part = self.extract_invite_hash(invite_link)
                            print(f"🔍 Hash استخراج شده از لینک: {hash_part}")
                            
                            # چک کردن invite برای دریافت entity
                            from telethon.tl.functions.messages import CheckChatInviteRequest
                            invite = await self.client(CheckChatInviteRequest(hash_part))
                            from telethon.tl.types import ChatInviteAlready
                            if isinstance(invite, ChatInviteAlready):
                                entity = invite.chat
                        except Exception as e:
                            print(f"⚠️ خطا در دریافت entity با invite link {invite_link}: {e}")
                            pass
                    elif username and not username.startswith('http') and not username.startswith('+'):
                        try:
                            entity = await self.client.get_entity(username)
                        except Exception as e:
                            print(f"⚠️ خطا در دریافت entity با username {username}: {e}")
                            pass
                
                if entity:
                    try:
                        await self.client(LeaveChannelRequest(entity))
                        print(f"✅ از کانال {username} (ID: {telegram_id if telegram_id else 'N/A'}) خارج شدیم")
                        # علامت‌گذاری که از کانال خارج شدیم (is_member = 0)
                        self.db.set_channel_member_status(channel_id, False)
                    except Exception as leave_error:
                        print(f"❌ خطا در خروج از کانال {username}: {leave_error}")
                        # حتی در صورت خطا، is_member = 0 می‌کنیم (مثلاً کانال حذف شده)
                        self.db.set_channel_member_status(channel_id, False)
                else:
                    print(f"⚠️ نتوانستیم entity کانال {username} را پیدا کنیم")
                    # اگر entity پیدا نشد، باز هم is_member = 0 می‌کنیم
                    self.db.set_channel_member_status(channel_id, False)
            except Exception as e:
                print(f"❌ خطا در خروج از کانال {username}: {e}")
                # حتی در صورت خطا، is_member = 0 می‌کنیم
                self.db.set_channel_member_status(channel_id, False)
    
    def check_trigger_flag(self) -> tuple:
        """بررسی وجود فایل flag برای بررسی فوری - برمی‌گرداند (exists, user_id)"""
        flag_path = self.trigger_flag_file
        if os.path.exists(flag_path):
            try:
                # خواندن user_id از فایل flag (اگر وجود دارد)
                user_id = None
                try:
                    with open(flag_path, 'r') as f:
                        content = f.read().strip()
                        if content.isdigit():
                            user_id = int(content)
                except:
                    pass
                
                os.remove(flag_path)
                return (True, user_id)
            except Exception as e:
                print(f"⚠️ خطا در حذف فایل flag: {e}")
                return (False, None)
        return (False, None)
    
    def check_join_flag(self) -> dict:
        """بررسی وجود فایل flag برای join کردن کانال - برمی‌گرداند dict یا None"""
        flag_path = self.join_flag_file
        if os.path.exists(flag_path):
            try:
                print(f"📂 فایل join flag پیدا شد: {flag_path}")
                with open(flag_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f"📄 محتوای فایل join flag: {data}")
                
                # حذف فایل flag
                os.remove(flag_path)
                print(f"🗑️ فایل join flag حذف شد")
                return data
            except Exception as e:
                print(f"⚠️ خطا در خواندن فایل join flag: {e}")
                import traceback
                traceback.print_exc()
                # حذف فایل نامعتبر
                try:
                    os.remove(flag_path)
                except:
                    pass
                return None
        return None
    
    def check_leave_flag(self) -> dict:
        """بررسی وجود فایل flag برای leave کردن کانال - برمی‌گرداند dict یا None"""
        flag_path = self.leave_flag_file
        if os.path.exists(flag_path):
            try:
                print(f"📂 فایل leave flag پیدا شد: {flag_path}")
                with open(flag_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f"📄 محتوای فایل leave flag: {data}")
                
                # حذف فایل flag
                os.remove(flag_path)
                print(f"🗑️ فایل leave flag حذف شد")
                return data
            except Exception as e:
                print(f"⚠️ خطا در خواندن فایل leave flag: {e}")
                import traceback
                traceback.print_exc()
                # حذف فایل نامعتبر
                try:
                    os.remove(flag_path)
                except:
                    pass
                return None
        return None
    
    async def process_leave_channel(self, channel_id: int, username: str):
        """خروج از کانال به صورت فوری"""
        try:
            # اطمینان از اتصال قبل از استفاده
            await self.ensure_connected()
            
            # دریافت اطلاعات کانال از دیتابیس
            channel_info = self.db.get_channel_by_id(channel_id)
            if not channel_info:
                print(f"⚠️ کانال با ID {channel_id} پیدا نشد")
                return False
            
            telegram_id = channel_info.get('telegram_id')
            invite_link = channel_info.get('invite_link')
            actual_username = channel_info.get('username')
            
            print(f"🔍 تلاش برای خروج از کانال: username={actual_username}, telegram_id={telegram_id}, invite_link={invite_link}")
            
            entity = None
            
            # روش 1: استفاده از telegram_id (بهترین روش)
            if telegram_id:
                try:
                    # تلاش با ID مستقیم
                    entity = await self.client.get_entity(telegram_id)
                    print(f"✅ Entity کانال با telegram_id {telegram_id} پیدا شد")
                except Exception as e:
                    print(f"⚠️ نتوانستیم entity را با telegram_id {telegram_id} پیدا کنیم: {e}")
                    # تلاش با PeerChannel
                    try:
                        from telethon.tl.types import PeerChannel
                        entity = await self.client.get_entity(PeerChannel(telegram_id))
                        print(f"✅ Entity کانال با PeerChannel {telegram_id} پیدا شد")
                    except Exception as e2:
                        print(f"⚠️ نتوانستیم entity را با PeerChannel {telegram_id} پیدا کنیم: {e2}")
            
            # روش 2: جستجو در dialogs (کانال‌هایی که عضو هستیم)
            if not entity:
                try:
                    print(f"🔍 جستجو در dialogs برای پیدا کردن کانال...")
                    async for dialog in self.client.iter_dialogs():
                        if hasattr(dialog.entity, 'id') and dialog.entity.id == telegram_id:
                            entity = dialog.entity
                            print(f"✅ Entity کانال در dialogs پیدا شد: {dialog.name}")
                            break
                        elif hasattr(dialog.entity, 'username') and dialog.entity.username:
                            if dialog.entity.username == actual_username.lstrip('@'):
                                entity = dialog.entity
                                print(f"✅ Entity کانال در dialogs با username پیدا شد: {dialog.name}")
                                break
                except Exception as e:
                    print(f"⚠️ خطا در جستجوی dialogs: {e}")
            
            # روش 3: استفاده از username
            if not entity and actual_username and not actual_username.startswith('http') and not actual_username.startswith('+'):
                try:
                    entity = await self.client.get_entity(actual_username.lstrip('@'))
                    print(f"✅ Entity کانال با username {actual_username} پیدا شد")
                except Exception as e:
                    print(f"⚠️ خطا در دریافت entity با username {actual_username}: {e}")
            
            # روش 4: استفاده از invite_link (آخرین راه)
            if not entity and invite_link and (invite_link.startswith('http') or invite_link.startswith('t.me/+') or invite_link.startswith('+')):
                try:
                    # استخراج hash از لینک با استفاده از تابع کمکی
                    hash_part = self.extract_invite_hash(invite_link)
                    print(f"🔍 Hash استخراج شده از لینک: {hash_part}")
                    
                    # چک کردن invite برای دریافت entity
                    from telethon.tl.functions.messages import CheckChatInviteRequest
                    invite = await self.client(CheckChatInviteRequest(hash_part))
                    from telethon.tl.types import ChatInviteAlready
                    if isinstance(invite, ChatInviteAlready):
                        entity = invite.chat
                        print(f"✅ Entity کانال با invite link پیدا شد")
                except Exception as e:
                    print(f"⚠️ خطا در دریافت entity با invite link: {e}")
            
            if entity:
                try:
                    await self.client(LeaveChannelRequest(entity))
                    print(f"✅ از کانال {actual_username} (ID: {telegram_id if telegram_id else 'N/A'}) خارج شدیم (خروج فوری)")
                    self.db.set_channel_member_status(channel_id, False)
                    return True
                except Exception as e:
                    print(f"❌ خطا در خروج از کانال {actual_username}: {e}")
                    import traceback
                    traceback.print_exc()
                    # حتی در صورت خطا، is_member = 0 می‌کنیم
                    self.db.set_channel_member_status(channel_id, False)
                    return False
            else:
                print(f"❌ نتوانستیم entity کانال {actual_username} را پیدا کنیم")
                print(f"   telegram_id: {telegram_id}, invite_link: {invite_link}")
                # حتی اگر entity پیدا نشد، is_member = 0 می‌کنیم
                self.db.set_channel_member_status(channel_id, False)
                return False
        except Exception as e:
            print(f"❌ خطا در process_leave_channel: {e}")
            import traceback
            traceback.print_exc()
            # حتی در صورت خطا، is_member = 0 می‌کنیم
            try:
                self.db.set_channel_member_status(channel_id, False)
            except:
                pass
            return False
    
    async def process_join_channel(self, channel_id: int, channel_identifier: str):
        """پیوندن به کانال و تنظیم is_member"""
        try:
            # اطمینان از اتصال قبل از استفاده
            await self.ensure_connected()
            
            success, entity, telegram_id = await self.join_channel(channel_identifier)
            
            if success and entity:
                # به‌روزرسانی دیتابیس
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                # به‌روزرسانی is_member و telegram_id
                cursor.execute('''
                    UPDATE channels 
                    SET is_member = 1, 
                        telegram_id = ?,
                        title = COALESCE(?, title)
                    WHERE id = ?
                ''', (telegram_id, entity.title if hasattr(entity, 'title') else None, channel_id))
                
                conn.commit()
                conn.close()
                
                # به‌روزرسانی telegram_id اگر تغییر کرده
                if telegram_id:
                    self.db.update_channel_telegram_id(channel_id, telegram_id)
                
                print(f"✅ با موفقیت به کانال {channel_identifier} پیوستیم!")
                return True
            else:
                # اگر نتوانستیم بپیوندیم، is_member = 0 می‌ماند
                print(f"❌ نتوانستیم به کانال {channel_identifier} بپیوندیم")
                return False
        except Exception as e:
            print(f"❌ خطا در process_join_channel: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def create_notification(self, user_id, start_time, channels_count, success):
        """ایجاد فایل notification برای اطلاع‌رسانی به کاربر"""
        try:
            notification_data = {
                'user_id': user_id,
                'timestamp': datetime.now().isoformat(),
                'start_time': start_time.isoformat(),
                'channels_count': channels_count,
                'success': success
            }
            notification_path = os.path.join(os.getcwd(), self.notification_file)
            with open(notification_path, 'w', encoding='utf-8') as f:
                json.dump(notification_data, f, ensure_ascii=False, indent=2)
            print(f"📩 فایل notification ایجاد شد در: {notification_path}")
            print(f"   user_id={user_id}, channels={channels_count}, success={success}")
        except Exception as e:
            print(f"⚠️ خطا در ایجاد فایل notification: {e}")
            import traceback
            traceback.print_exc()
    
    async def run(self):
        """اجرای اصلی ربات"""
        try:
            # تنظیم کلاینت
            await self.setup_client()
            
            print("\n=== ربات رصد کانال شروع به کار کرد ===")
            print("هر 30 دقیقه کانال‌ها بررسی خواهند شد")
            print("برای بررسی فوری، فایل trigger_check.flag ایجاد کنید")
            print("برای توقف ربات، Ctrl+C را فشار دهید\n")
            
            # اولین بررسی فوری
            await self.monitor_channels()
            
            # حلقه بررسی دوره‌ای
            check_interval = 10  # چک کردن هر 10 ثانیه
            normal_interval = 1800  # 30 دقیقه = 1800 ثانیه
            time_until_next_check = 0  # زمان باقی‌مانده تا بررسی عادی
            
            while True:
                # چک کردن فایل flag برای leave کردن کانال (اولویت بالاتر)
                leave_flag_data = self.check_leave_flag()
                if leave_flag_data:
                    channel_id = leave_flag_data.get('channel_id')
                    username = leave_flag_data.get('username')
                    if channel_id:
                        print(f"\n🚪 درخواست خروج فوری از کانال: {username} (ID: {channel_id})")
                        result = await self.process_leave_channel(channel_id, username)
                        if result:
                            print(f"✅ خروج از کانال {username} با موفقیت انجام شد")
                        else:
                            print(f"❌ خروج از کانال {username} ناموفق بود")
                    else:
                        print(f"⚠️ فایل leave flag پیدا شد اما channel_id موجود نیست: {leave_flag_data}")
                
                # چک کردن فایل flag برای join کردن کانال
                join_flag_data = self.check_join_flag()
                if join_flag_data:
                    channel_id = join_flag_data.get('channel_id')
                    channel_identifier = join_flag_data.get('channel_identifier')
                    if channel_id and channel_identifier:
                        print(f"\n➕ درخواست پیوستن به کانال: {channel_identifier} (ID: {channel_id})")
                        await self.process_join_channel(channel_id, channel_identifier)
                
                # چک کردن فایل flag برای بررسی فوری
                flag_exists, user_id = self.check_trigger_flag()
                if flag_exists:
                    print(f"\n⚡ بررسی فوری درخواست شده! (user_id: {user_id})")
                    await self.monitor_channels(triggered_by_user_id=user_id)
                    print(f"✅ بررسی تمام شد، notification برای user_id={user_id} ایجاد می‌شود...")
                    time_until_next_check = normal_interval  # ریست کردن تایمر
                    continue
                
                # بررسی اینکه آیا زمان بررسی عادی رسیده است
                if time_until_next_check <= 0:
                    print(f"\n⏰ بررسی دوره‌ای (هر 30 دقیقه)")
                    await self.monitor_channels()
                    time_until_next_check = normal_interval
                else:
                    # چاپ پیام هر 5 دقیقه
                    if time_until_next_check % 300 == 0 or time_until_next_check == normal_interval:
                        minutes_left = time_until_next_check // 60
                        print(f"\n⏳ بررسی بعدی در {minutes_left} دقیقه... (یا بررسی فوری با ایجاد trigger_check.flag)")
                
                # انتظار 10 ثانیه
                await asyncio.sleep(check_interval)
                time_until_next_check -= check_interval
                
        except KeyboardInterrupt:
            print("\n\n🛑 ربات متوقف شد")
        except Exception as e:
            print(f"\n❌ خطای غیرمنتظره: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.client:
                await self.client.disconnect()


async def main():
    monitor = ChannelMonitor()
    await monitor.run()


if __name__ == "__main__":
    asyncio.run(main())

