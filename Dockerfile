FROM python:3.11-slim

WORKDIR /app

# نصب dependencies سیستم
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# کپی فایل requirements
COPY requirements.txt .

# نصب Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# کپی فایل‌های پروژه
COPY *.py ./
COPY *.json ./

# ایجاد دایرکتوری برای فایل‌های موقت
RUN mkdir -p /app/data

# تنظیم متغیرهای محیطی
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# دستور پیش‌فرض (می‌تواند در docker-compose override شود)
CMD ["python", "channel_monitor.py"]

