# راهنمای استفاده از Docker

## پیش‌نیازها

- Docker
- Docker Compose

## راه‌اندازی

### 1. ساخت و اجرای کانتینرها

```bash
docker-compose up -d
```

### 2. مشاهده لاگ‌ها

```bash
# لاگ همه سرویس‌ها
docker-compose logs -f

# لاگ فقط ربات رصد
docker-compose logs -f channel_monitor

# لاگ فقط ربات ادمین
docker-compose logs -f admin_bot
```

### 3. توقف سرویس‌ها

```bash
docker-compose stop
```

### 4. راه‌اندازی مجدد

```bash
docker-compose restart
```

### 5. توقف و حذف کانتینرها

```bash
docker-compose down
```

### 6. ساخت مجدد (بعد از تغییرات کد)

```bash
docker-compose up -d --build
```

## ساختار Volume ها

فایل‌های زیر به صورت volume mount شده‌اند و در هاست persist می‌شوند:

- `new.session` - فایل session Telethon
- `theleton.db` - دیتابیس SQLite
- `config.json` - تنظیمات Telethon
- `admin_config.json` - تنظیمات ربات Admin
- `data/` - دایرکتوری برای فایل‌های موقت (flag files)

## نکات مهم

1. **فایل‌های config**: قبل از اجرا، مطمئن شوید که `config.json` و `admin_config.json` را تنظیم کرده‌اید.

2. **فایل session**: فایل `new.session` باید در هاست موجود باشد یا بعد از اولین اجرا ایجاد می‌شود.

3. **دیتابیس**: دیتابیس `theleton.db` به صورت مشترک بین دو سرویس استفاده می‌شود.

4. **فایل‌های flag**: فایل‌های `*.flag` و `check_notification.json` در دایرکتوری `data/` ذخیره می‌شوند.

## عیب‌یابی

### بررسی وضعیت سرویس‌ها

```bash
docker-compose ps
```

### ورود به کانتینر

```bash
# ورود به کانتینر ربات رصد
docker-compose exec channel_monitor bash

# ورود به کانتینر ربات ادمین
docker-compose exec admin_bot bash
```

### مشاهده لاگ‌های خطا

```bash
docker-compose logs --tail=100 channel_monitor
docker-compose logs --tail=100 admin_bot
```

