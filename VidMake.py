"""
برنامج إنشاء فيديوهات القرآن الكريم
يقوم بإنشاء فيديوهات تحتوي على آيات قرآنية مع الصوت والخلفيات المتحركة
"""

import os
import sys
import time
import asyncio
import random
import textwrap
import gc
from typing import List, Tuple, Dict
from datetime import datetime, timedelta
from dataclasses import dataclass, field

import requests
import pandas as pd
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from telegram import Bot
from moviepy.editor import (
    VideoFileClip, AudioFileClip, ImageClip, ColorClip,
    CompositeVideoClip, concatenate_videoclips
)
from moviepy.video.fx.fadein import fadein
from moviepy.video.fx.fadeout import fadeout

# إصلاح مشكلة PIL
import PIL
PIL.Image.ANTIALIAS = PIL.Image.LANCZOS


# ============================================================================
# إعدادات البرنامج - يمكن تعديلها بسهولة
# ============================================================================

class Config:
    """إعدادات البرنامج الرئيسية"""
    
    # إعدادات Telegram
    TELEGRAM_BOT_TOKEN = os.environ.get("BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.environ.get("CHAT_ID")
    
    # إعدادات API
    QURAN_API_BASE_URL = "http://api.alquran.cloud/v1"
    QURAN_COM_API_URL = "https://api.quran.com/api/v4"  # API للمزامنة الصوتية
    QURAN_RECITER = "ar.alafasy"  # القارئ: مشاري العفاسي
    QURAN_RECITER_ID = 7  # معرف القارئ في Quran.com API (7 = العفاسي)
    API_RETRY_COUNT = 5
    API_RETRY_DELAY = 45  # بالثواني
    API_TIMEOUT = 20  # بالثواني
    
    # إعدادات الملفات والمجلدات
    TEMP_AUDIO_FOLDER = "temp_audio"
    VIDEO_STOCK_FOLDER = "Stock_Videos"
    OUTPUT_FOLDER = "OutPut"
    LOGO_PATH = "logo.png"
    FONT_PATH = "Fonts/Amiri-Regular.ttf"
    START_VERSE_FILE = "StartAya.txt"
    
    # إعدادات الفيديو
    VIDEO_WIDTH = 1080
    VIDEO_HEIGHT = 1920
    VIDEO_FPS = 30
    VIDEO_CODEC = 'libx264'
    NUM_VIDEOS_PER_CLIP = 4  # عدد مقاطع الفيديو المستخدمة في كل فيديو نهائي
    
    # إعدادات النص
    FONT_SIZE = 100
    TEXT_COLOR = 'white'
    TEXT_STROKE_COLOR = 'black'
    TEXT_STROKE_WIDTH = 2
    
    # إعدادات المزامنة الصوتية
    USE_WORD_SYNC = True  # تفعيل المزامنة كلمة بكلمة
    MIN_WORDS_PER_SEGMENT = 2  # الحد الأدنى لعدد الكلمات في المقطع
    MIN_CHARS_PER_SEGMENT = 15  # الحد الأدنى لعدد الأحرف في المقطع
    MAX_CHARS_PER_SEGMENT = 20  # الحد الأقصى لعدد الأحرف في المقطع
    
    # إعدادات التأثيرات
    TRANSITION_DURATION = 0.4  # مدة الانتقال بين المقاطع (بالثواني)
    BLACK_OVERLAY_OPACITY = 0.55  # شفافية الطبقة السوداء
    LOGO_WIDTH = 200  # عرض الشعار
    LOGO_POSITION = (0.1, 20)  # موضع الشعار (x, y)
    
    # إعدادات مدة الصوت المقبولة
    MIN_AUDIO_DURATION = 15  # الحد الأدنى لمدة الصوت (بالثواني)
    MAX_AUDIO_DURATION = 45  # الحد الأقصى لمدة الصوت (بالثواني)
    
    # إعدادات عرض النص حسب المدة
    TEXT_WIDTH_MAPPING = {
        5: 15,
        15: 30,
        25: 40,
        'default': 40
    }
    
    # إعدادات التوقف والانتظار
    SLEEP_BETWEEN_VIDEOS = 45  # الانتظار بين الفيديوهات (بالثواني)
    SLEEP_ON_SKIP = 10  # الانتظار عند تخطي آية (بالثواني)
    
    # إعدادات الإنتاج
    TOTAL_VERSES = 6236  # إجمالي عدد الآيات في القرآن
    DEFAULT_NUM_VIDEOS = 2  # عدد الفيديوهات المطلوب إنشاؤها


# ============================================================================
# نظام الإحصائيات
# ============================================================================

@dataclass
class Statistics:
    """فئة لتتبع إحصائيات إنشاء الفيديوهات"""
    
    # معلومات عامة
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime = None
    
    # إحصائيات الفيديوهات
    total_requested: int = 0
    total_created: int = 0
    total_skipped: int = 0
    total_failed: int = 0
    
    # تفاصيل الآيات
    verses_processed: List[int] = field(default_factory=list)
    verses_skipped: List[int] = field(default_factory=list)
    verses_failed: Dict[int, str] = field(default_factory=dict)
    
    # إحصائيات الأخطاء
    api_errors: int = 0
    video_errors: int = 0
    
    # معلومات إضافية
    verse_range: Tuple[int, int] = (0, 0)
    
    def mark_created(self, verse_number: int) -> None:
        """تسجيل فيديو تم إنشاؤه بنجاح"""
        self.total_created += 1
        self.verses_processed.append(verse_number)
    
    def mark_skipped(self, verse_number: int) -> None:
        """تسجيل آية تم تخطيها"""
        self.total_skipped += 1
        self.verses_skipped.append(verse_number)
    
    def mark_failed(self, verse_number: int, error: str) -> None:
        """تسجيل فيديو فشل في الإنشاء"""
        self.total_failed += 1
        self.verses_failed[verse_number] = error
    
    def mark_api_error(self) -> None:
        """تسجيل خطأ في API"""
        self.api_errors += 1
    
    def mark_video_error(self) -> None:
        """تسجيل خطأ في معالجة الفيديو"""
        self.video_errors += 1
    
    def finalize(self) -> None:
        """إنهاء تسجيل الإحصائيات"""
        self.end_time = datetime.now()
    
    def get_duration(self) -> timedelta:
        """الحصول على المدة الإجمالية"""
        end = self.end_time or datetime.now()
        return end - self.start_time
    
    def get_success_rate(self) -> float:
        """حساب نسبة النجاح"""
        total = self.total_created + self.total_failed
        if total == 0:
            return 0.0
        return (self.total_created / total) * 100
    
    def format_duration(self, duration: timedelta) -> str:
        """تنسيق المدة الزمنية"""
        total_seconds = int(duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours} ساعة و {minutes} دقيقة و {seconds} ثانية"
        elif minutes > 0:
            return f"{minutes} دقيقة و {seconds} ثانية"
        else:
            return f"{seconds} ثانية"
    
    def generate_report(self) -> str:
        """إنشاء تقرير مفصل بالإحصائيات"""
        duration = self.get_duration()
        success_rate = self.get_success_rate()
        
        # حساب متوسط الوقت لكل فيديو
        avg_time_per_video = "غير متاح"
        if self.total_created > 0:
            avg_seconds = duration.total_seconds() / self.total_created
            avg_time_per_video = self.format_duration(timedelta(seconds=avg_seconds))
        
        report = "📊 *تقرير إحصائيات إنشاء الفيديوهات* 📊\n"
        report += "═" * 35 + "\n\n"
        
        # معلومات عامة
        report += "⏱ *معلومات التشغيل:*\n"
        report += f"• وقت البدء: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        if self.end_time:
            report += f"• وقت الانتهاء: {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        report += f"• المدة الإجمالية: {self.format_duration(duration)}\n"
        report += f"• نطاق الآيات: من {self.verse_range[0]} إلى {self.verse_range[1]}\n\n"
        
        # إحصائيات الفيديوهات
        report += "🎬 *إحصائيات الفيديوهات:*\n"
        report += f"• المطلوب: {self.total_requested} فيديو\n"
        report += f"• ✅ تم الإنشاء: {self.total_created} فيديو\n"
        report += f"• ⏭ تم التخطي: {self.total_skipped} آية\n"
        report += f"• ❌ فشل: {self.total_failed} فيديو\n"
        report += f"• 📈 نسبة النجاح: {success_rate:.1f}%\n\n"
        
        # معلومات الأداء
        report += "⚡ *معلومات الأداء:*\n"
        report += f"• متوسط الوقت لكل فيديو: {avg_time_per_video}\n"
        if self.total_created > 0:
            report += f"• معدل الإنتاج: {self.total_created / (duration.total_seconds() / 3600):.2f} فيديو/ساعة\n"
        report += "\n"
        
        # إحصائيات الأخطاء
        if self.api_errors > 0 or self.video_errors > 0:
            report += "⚠️ *إحصائيات الأخطاء:*\n"
            if self.api_errors > 0:
                report += f"• أخطاء API: {self.api_errors}\n"
            if self.video_errors > 0:
                report += f"• أخطاء معالجة الفيديو: {self.video_errors}\n"
            report += "\n"
        
        # تفاصيل الآيات المتخطاة
        if self.verses_skipped:
            report += "⏭ *الآيات المتخطاة:*\n"
            if len(self.verses_skipped) <= 10:
                report += f"الأرقام: {', '.join(map(str, self.verses_skipped))}\n"
            else:
                report += f"العدد: {len(self.verses_skipped)} آية\n"
                report += f"أول 5: {', '.join(map(str, self.verses_skipped[:5]))}\n"
                report += f"آخر 5: {', '.join(map(str, self.verses_skipped[-5:]))}\n"
            report += "\n"
        
        # تفاصيل الأخطاء
        if self.verses_failed:
            report += "❌ *الفيديوهات الفاشلة:*\n"
            if len(self.verses_failed) <= 5:
                for verse, error in list(self.verses_failed.items())[:5]:
                    # اختصار رسالة الخطأ
                    short_error = error[:50] + "..." if len(error) > 50 else error
                    report += f"• الآية {verse}: {short_error}\n"
            else:
                report += f"العدد الإجمالي: {len(self.verses_failed)} فيديو\n"
                report += f"الآيات: {', '.join(map(str, list(self.verses_failed.keys())[:5]))}...\n"
            report += "\n"
        
        # الخلاصة
        report += "═" * 35 + "\n"
        if self.total_created == self.total_requested:
            report += "✨ *تم إنشاء جميع الفيديوهات المطلوبة بنجاح!* ✨\n"
        elif self.total_created > 0:
            report += f"✅ *تم إنشاء {self.total_created} من {self.total_requested} فيديو*\n"
        else:
            report += "⚠️ *لم يتم إنشاء أي فيديو*\n"
        
        report += "\n🤲 الحمد لله رب العالمين"
        
        return report


# ============================================================================
# وظائف Telegram
# ============================================================================

async def send_telegram_message(text: str = "تم النشر", parse_mode: str = None) -> None:
    """
    إرسال رسالة عبر Telegram
    
    Args:
        text: نص الرسالة المراد إرسالها
        parse_mode: نمط التنسيق (Markdown أو HTML)
    """
    try:
        bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=Config.TELEGRAM_CHAT_ID,
            text=text,
            parse_mode=parse_mode
        )
    except Exception as e:
        print(f"خطأ في إرسال رسالة Telegram: {e}")


# ============================================================================
# وظائف إدارة الملفات
# ============================================================================

def save_start_verse(verse_number: int) -> None:
    """
    حفظ رقم الآية الحالية في ملف
    
    Args:
        verse_number: رقم الآية المراد حفظها
    """
    try:
        with open(Config.START_VERSE_FILE, 'w', encoding='utf-8') as file:
            file.write(str(verse_number))
        print(f"تم حفظ رقم الآية {verse_number} في الملف")
    except IOError as e:
        print(f'خطأ أثناء كتابة الملف: {e}')


def load_start_verse() -> int:
    """
    قراءة رقم آية البداية من الملف
    
    Returns:
        رقم الآية المحفوظة
    """
    try:
        with open(Config.START_VERSE_FILE, 'r', encoding='utf-8') as file:
            value = file.read().strip()
            return int(value)
    except (IOError, ValueError) as e:
        print(f'خطأ في قراءة ملف البداية: {e}')
        return 1  # البداية من الآية الأولى في حالة الخطأ



# ============================================================================
# وظائف API القرآن الكريم
# ============================================================================

def convert_verse_number_to_key(verse_number: int) -> str:
    """
    تحويل رقم الآية المطلق (1-6236) إلى مفتاح الآية (سورة:آية)
    
    Args:
        verse_number: رقم الآية المطلق
        
    Returns:
        مفتاح الآية بصيغة "سورة:آية" (مثال: "1:1", "2:255")
    """
    # عدد الآيات في كل سورة
    verses_per_surah = [
        7, 286, 200, 176, 120, 165, 206, 75, 129, 109,
        123, 111, 43, 52, 99, 128, 111, 110, 98, 135,
        112, 78, 118, 64, 77, 227, 93, 88, 69, 60,
        34, 30, 73, 54, 45, 83, 182, 88, 75, 85,
        54, 53, 89, 59, 37, 35, 38, 29, 18, 45,
        60, 49, 62, 55, 78, 96, 29, 22, 24, 13,
        14, 11, 11, 18, 12, 12, 30, 52, 52, 44,
        28, 28, 20, 56, 40, 31, 50, 40, 46, 42,
        29, 19, 36, 25, 22, 17, 19, 26, 30, 20,
        15, 21, 11, 8, 8, 19, 5, 8, 8, 11,
        11, 8, 3, 9, 5, 4, 7, 3, 6, 3,
        5, 4, 5, 6
    ]
    
    if verse_number < 1 or verse_number > 6236:
        raise ValueError(f"رقم الآية {verse_number} خارج النطاق المسموح (1-6236)")
    
    current_verse = 0
    for surah_num, ayah_count in enumerate(verses_per_surah, start=1):
        if current_verse + ayah_count >= verse_number:
            ayah_num = verse_number - current_verse
            return f"{surah_num}:{ayah_num}"
        current_verse += ayah_count
    
    # لا يجب الوصول لهذا السطر
    raise ValueError(f"خطأ في تحويل رقم الآية {verse_number}")


def fetch_verse_with_timing(verse_number: int) -> dict:
    """
    استرجاع بيانات الآية مع توقيت الكلمات من Quran.com API
    
    Args:
        verse_number: رقم الآية المطلق (1-6236)
        
    Returns:
        dict: قاموس يحتوي على:
            - verse_text: نص الآية
            - audio_url: رابط الملف الصوتي
            - words: قائمة الكلمات مع بياناتها
            - segments: قائمة توقيتات الكلمات
            
    Raises:
        requests.RequestException: في حالة فشل جميع المحاولات
    """
    # تحويل رقم الآية إلى مفتاح
    verse_key = convert_verse_number_to_key(verse_number)
    
    # بناء رابط API
    url = (
        f"{Config.QURAN_COM_API_URL}/verses/by_key/{verse_key}"
        f"?language=ar&words=true&audio={Config.QURAN_RECITER_ID}"
        f"&word_fields=audio_url,text_uthmani,char_type_name"
        f"&fields=text_uthmani"
    )
    
    for attempt in range(Config.API_RETRY_COUNT):
        try:
            print(f"جارٍ استرجاع بيانات الآية {verse_number} ({verse_key}) مع التوقيت... (محاولة {attempt + 1}/{Config.API_RETRY_COUNT})")
            
            response = requests.get(url, timeout=Config.API_TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            verse_data = data['verse']
            
            # استخراج البيانات المطلوبة
            verse_text = verse_data['text_uthmani']
            audio_url = "https://verses.quran.com/" + verse_data['audio']['url']
            words = verse_data['words']
            segments = verse_data['audio']['segments']
            
            print(f"تم استرجاع بيانات الآية {verse_number} بنجاح ({len(words)} كلمة)")
            
            return {
                'verse_text': verse_text,
                'audio_url': audio_url,
                'words': words,
                'segments': segments
            }
            
        except requests.RequestException as e:
            print(f"خطأ أثناء استرجاع بيانات الآية {verse_number}: {e}")
            
            if attempt < Config.API_RETRY_COUNT - 1:
                print(f"إعادة المحاولة بعد {Config.API_RETRY_DELAY} ثانية...")
                time.sleep(Config.API_RETRY_DELAY)
            else:
                print(f"فشل استرجاع بيانات الآية {verse_number} بعد {Config.API_RETRY_COUNT} محاولات.")
                raise
        except (KeyError, ValueError) as e:
            print(f"خطأ في معالجة بيانات الآية {verse_number}: {e}")
            
            if attempt < Config.API_RETRY_COUNT - 1:
                print(f"إعادة المحاولة بعد {Config.API_RETRY_DELAY} ثانية...")
                time.sleep(Config.API_RETRY_DELAY)
            else:
                print(f"فشل معالجة بيانات الآية {verse_number} بعد {Config.API_RETRY_COUNT} محاولات.")
                raise requests.RequestException(f"خطأ في معالجة البيانات: {e}")



def fetch_verse_text(verse_number: int) -> str:
    """
    استرجاع نص الآية من API
    
    Args:
        verse_number: رقم الآية
        
    Returns:
        نص الآية
        
    Raises:
        requests.RequestException: في حالة فشل جميع المحاولات
    """
    url = f"{Config.QURAN_API_BASE_URL}/ayah/{verse_number}"
    
    for attempt in range(Config.API_RETRY_COUNT):
        try:
            print(f"جارٍ استرجاع النص للآية رقم {verse_number}... (محاولة {attempt + 1}/{Config.API_RETRY_COUNT})")
            
            response = requests.get(url, timeout=Config.API_TIMEOUT)
            response.raise_for_status()
            
            verse_data = response.json()
            verse_text = verse_data['data']['text']
            
            print(f"تم استرجاع النص للآية رقم {verse_number}.")
            return verse_text
            
        except requests.RequestException as e:
            print(f"خطأ أثناء استرجاع النص للآية رقم {verse_number}: {e}")
            
            if attempt < Config.API_RETRY_COUNT - 1:
                print(f"إعادة المحاولة بعد {Config.API_RETRY_DELAY} ثانية...")
                time.sleep(Config.API_RETRY_DELAY)
            else:
                print(f"فشل استرجاع النص للآية رقم {verse_number} بعد {Config.API_RETRY_COUNT} محاولات.")
                raise


def download_audio_file(audio_url: str, verse_number: int) -> str:
    """
    تحميل ملف الصوت من URL وحفظه محلياً
    
    Args:
        audio_url: رابط ملف الصوت
        verse_number: رقم الآية
        
    Returns:
        مسار الملف المحلي
        
    Raises:
        requests.RequestException: في حالة فشل جميع المحاولات
    """
    # إنشاء مجلد الصوت إذا لم يكن موجوداً
    if not os.path.exists(Config.TEMP_AUDIO_FOLDER):
        os.makedirs(Config.TEMP_AUDIO_FOLDER)
    
    local_filename = os.path.join(Config.TEMP_AUDIO_FOLDER, f"audio_{verse_number}.mp3")
    
    for attempt in range(Config.API_RETRY_COUNT):
        try:
            print(f"جارٍ تحميل ملف الصوت للآية رقم {verse_number}... (محاولة {attempt + 1}/{Config.API_RETRY_COUNT})")
            
            response = requests.get(audio_url, timeout=30, stream=True)
            response.raise_for_status()
            
            with open(local_filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"تم تحميل ملف الصوت للآية رقم {verse_number}.")
            return local_filename
            
        except requests.RequestException as e:
            print(f"خطأ أثناء تحميل ملف الصوت للآية رقم {verse_number}: {e}")
            
            if attempt < Config.API_RETRY_COUNT - 1:
                print(f"إعادة المحاولة بعد {Config.API_RETRY_DELAY} ثانية...")
                time.sleep(Config.API_RETRY_DELAY)
            else:
                print(f"فشل تحميل ملف الصوت للآية رقم {verse_number} بعد {Config.API_RETRY_COUNT} محاولات.")
                raise


def fetch_verse_audio(verse_number: int) -> str:
    """
    استرجاع ملف الصوت للآية من API وتحميله محلياً
    
    Args:
        verse_number: رقم الآية
        
    Returns:
        مسار الملف الصوتي المحلي
        
    Raises:
        requests.RequestException: في حالة فشل جميع المحاولات
    """
    url = f"{Config.QURAN_API_BASE_URL}/ayah/{verse_number}/{Config.QURAN_RECITER}"
    
    for attempt in range(Config.API_RETRY_COUNT):
        try:
            print(f"جارٍ استرجاع رابط ملف الصوت للآية رقم {verse_number}... (محاولة {attempt + 1}/{Config.API_RETRY_COUNT})")
            
            response = requests.get(url, timeout=Config.API_TIMEOUT)
            response.raise_for_status()
            
            audio_url = response.json()['data']['audio']
            print(f"تم استرجاع رابط ملف الصوت للآية رقم {verse_number}.")
            
            # تحميل الملف الصوتي محلياً
            local_audio_path = download_audio_file(audio_url, verse_number)
            return local_audio_path
            
        except requests.RequestException as e:
            print(f"خطأ أثناء استرجاع ملف الصوت للآية رقم {verse_number}: {e}")
            
            if attempt < Config.API_RETRY_COUNT - 1:
                print(f"إعادة المحاولة بعد {Config.API_RETRY_DELAY} ثانية...")
                time.sleep(Config.API_RETRY_DELAY)
            else:
                print(f"فشل استرجاع ملف الصوت للآية رقم {verse_number} بعد {Config.API_RETRY_COUNT} محاولات.")
                raise


# ============================================================================
# وظائف معالجة الفيديو
# ============================================================================

def select_random_videos(video_folder: str, num_videos: int) -> List[str]:
    """
    اختيار مقاطع فيديو عشوائية من المجلد
    
    Args:
        video_folder: مسار مجلد الفيديوهات
        num_videos: عدد الفيديوهات المطلوب اختيارها
        
    Returns:
        قائمة بمسارات الفيديوهات المختارة
    """
    print("جارٍ اختيار مقاطع الفيديو العشوائية...")
    
    videos = os.listdir(video_folder)
    random_videos = random.sample(videos, num_videos)
    video_paths = [os.path.join(video_folder, video) for video in random_videos]
    
    print("تم اختيار مقاطع الفيديو العشوائية.")
    return video_paths


def get_video_dimensions(video_path: str) -> Tuple[int, int]:
    """
    الحصول على أبعاد الفيديو
    
    Args:
        video_path: مسار الفيديو
        
    Returns:
        tuple: (العرض, الارتفاع)
    """
    video = VideoFileClip(video_path)
    width, height = video.size
    video.close()
    return width, height


def create_video_clips(video_paths: List[str], total_duration: float, audio_clip) -> List[VideoFileClip]:
    """
    إنشاء مقاطع الفيديو مع التأثيرات
    
    Args:
        video_paths: قائمة مسارات الفيديوهات
        total_duration: المدة الإجمالية المطلوبة
        audio_clip: مقطع الصوت
        
    Returns:
        قائمة بمقاطع الفيديو المعدلة
    """
    video_clips = []
    duration_per_clip = total_duration / len(video_paths)
    
    for i, video_path in enumerate(video_paths):
        # تحميل وتغيير حجم الفيديو
        video_clip = VideoFileClip(video_path).resize((Config.VIDEO_WIDTH, Config.VIDEO_HEIGHT))
        video_clip = video_clip.set_duration(duration_per_clip)
        
        # إضافة تأثيرات الظهور والاختفاء
        if i > 0:
            video_clip = fadein(video_clip, duration=Config.TRANSITION_DURATION)
        video_clip = fadeout(video_clip, duration=Config.TRANSITION_DURATION)
        
        video_clips.append(video_clip)
    
    # إضافة مقطع فارغ إذا كانت المدة أقل من مدة الصوت
    clips_total_duration = sum(clip.duration for clip in video_clips)
    if clips_total_duration < audio_clip.duration:
        blank_duration = audio_clip.duration - clips_total_duration
        blank_clip = ColorClip(
            size=(Config.VIDEO_WIDTH, Config.VIDEO_HEIGHT),
            color=(0, 0, 0)
        ).set_duration(blank_duration)
        video_clips.append(blank_clip)
    
    return video_clips


# ============================================================================
# وظائف معالجة النص
# ============================================================================

def get_arabic_font(fontsize: int = 100) -> ImageFont.FreeTypeFont:
    """
    الحصول على الخط العربي
    
    Args:
        fontsize: حجم الخط
        
    Returns:
        كائن الخط
    """
    try:
        return ImageFont.truetype(Config.FONT_PATH, fontsize)
    except Exception as e:
        print(f"تحذير: خطأ في تحميل الخط من {Config.FONT_PATH}: {e}")
        print("استخدام الخط الافتراضي")
        return ImageFont.load_default()


def calculate_text_width(audio_duration: float) -> int:
    """
    حساب العرض المناسب للنص بناءً على مدة الصوت
    
    Args:
        audio_duration: مدة الملف الصوتي (بالثواني)
        
    Returns:
        العرض المناسب للنص
    """
    # ترتيب المفاتيح الرقمية فقط
    numeric_keys = sorted([k for k in Config.TEXT_WIDTH_MAPPING.keys() if isinstance(k, (int, float))])
    
    for max_duration in numeric_keys:
        if audio_duration <= max_duration:
            return Config.TEXT_WIDTH_MAPPING[max_duration]
    
    return Config.TEXT_WIDTH_MAPPING['default']


def create_text_clip_with_pil(
    text: str,
    duration: float,
    fontsize: int = None,
    color: str = None,
    stroke_color: str = None,
    stroke_width: int = None,
    size: Tuple[int, int] = None
) -> ImageClip:
    """
    إنشاء مقطع نصي باستخدام PIL
    
    Args:
        text: النص المراد عرضه
        duration: مدة عرض النص
        fontsize: حجم الخط (افتراضي من Config)
        color: لون النص (افتراضي من Config)
        stroke_color: لون حدود النص (افتراضي من Config)
        stroke_width: عرض حدود النص (افتراضي من Config)
        size: حجم الصورة (افتراضي من Config)
        
    Returns:
        مقطع الصورة النصية
    """
    # استخدام القيم الافتراضية من Config
    fontsize = fontsize or Config.FONT_SIZE
    color = color or Config.TEXT_COLOR
    stroke_color = stroke_color or Config.TEXT_STROKE_COLOR
    stroke_width = stroke_width or Config.TEXT_STROKE_WIDTH
    size = size or (Config.VIDEO_WIDTH, Config.VIDEO_HEIGHT)
    
    # إنشاء صورة فارغة شفافة
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # الحصول على الخط العربي
    font = get_arabic_font(fontsize)
    
    # حساب حجم النص
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # حساب موضع النص (في المنتصف)
    x = (size[0] - text_width) / 2
    y = (size[1] - text_height) / 2
    
    # رسم الحدود (stroke)
    if stroke_width > 0:
        for adj_x in range(-stroke_width, stroke_width + 1):
            for adj_y in range(-stroke_width, stroke_width + 1):
                draw.text((x + adj_x, y + adj_y), text, font=font, fill=stroke_color)
    
    # رسم النص الأساسي
    draw.text((x, y), text, font=font, fill=color)
    
    # تحويل الصورة إلى numpy array
    img_array = np.array(img)
    
    # إنشاء ImageClip من الصورة
    clip = ImageClip(img_array).set_duration(duration)
    
    return clip


def create_text_clips(verse_text: str, audio_duration: float) -> List[ImageClip]:
    """
    إنشاء مقاطع النص من الآية
    
    Args:
        verse_text: نص الآية
        audio_duration: مدة الصوت
        
    Returns:
        قائمة بمقاطع النص
    """
    # تقسيم النص إلى أسطر
    text_width = calculate_text_width(audio_duration)
    lines = textwrap.wrap(verse_text, width=text_width)
    num_lines = len(lines)
    
    # حساب مدة كل سطر
    duration_per_line = audio_duration / num_lines
    
    # إنشاء مقاطع النص
    text_clips = []
    for i, line in enumerate(lines):
        clip = create_text_clip_with_pil(line, duration_per_line)
        
        # إضافة تأثيرات الظهور والاختفاء
        if i > 0:
            clip = clip.fadein(Config.TRANSITION_DURATION)
        clip = clip.fadeout(Config.TRANSITION_DURATION)
        
        text_clips.append(clip)
    
    return text_clips


def group_words_into_segments(words: List[dict], segments: List[list]) -> List[dict]:
    """
    تجميع الكلمات في مقاطع نصية بناءً على عدد الكلمات والأحرف
    
    Args:
        words: قائمة الكلمات مع بياناتها من API
        segments: قائمة توقيتات الكلمات
        
    Returns:
        قائمة من المقاطع، كل مقطع يحتوي على:
            - text: النص المجمع
            - start: وقت البداية (بالثواني)
            - end: وقت النهاية (بالثواني)
            - duration: المدة (بالثواني)
    """
    grouped_segments = []
    current_group = []
    current_text = ""
    word_index = 0
    
    for i, word in enumerate(words):
        # تخطي الأحرف غير الكلمات (مثل علامات الترقيم)
        if word.get("char_type_name") != "word":
            continue
        
        # التأكد من وجود segment مقابل
        if word_index >= len(segments):
            break
        
        word_text = word.get("text_uthmani", "")
        segment = segments[word_index]
        
        # إضافة الكلمة للمجموعة الحالية
        current_group.append({
            "text": word_text,
            "start": segment[2] / 1000,  # تحويل من ميلي ثانية إلى ثواني
            "end": segment[3] / 1000
        })
        current_text += word_text + " "
        word_index += 1
        
        # التحقق من ضرورة إنهاء المقطع الحالي
        text_length = len(current_text.strip())
        word_count = len(current_group)
        
        should_finalize = (
            # حالة 1: وصلنا للحد الأدنى من الكلمات والأحرف
            (word_count >= Config.MIN_WORDS_PER_SEGMENT and 
             text_length >= Config.MIN_CHARS_PER_SEGMENT) or
            # حالة 2: تجاوزنا الحد الأقصى للأحرف
            text_length >= Config.MAX_CHARS_PER_SEGMENT
        )
        
        if should_finalize:
            grouped_segments.append({
                "text": current_text.strip(),
                "start": current_group[0]["start"],
                "end": current_group[-1]["end"],
                "duration": current_group[-1]["end"] - current_group[0]["start"]
            })
            current_group = []
            current_text = ""
    
    # إضافة الكلمات المتبقية
    if current_group:
        grouped_segments.append({
            "text": current_text.strip(),
            "start": current_group[0]["start"],
            "end": current_group[-1]["end"],
            "duration": current_group[-1]["end"] - current_group[0]["start"]
        })
    
    print(f"تم تجميع {len(words)} كلمة في {len(grouped_segments)} مقطع نصي")
    # تعديل المقطع الأول ليبدأ من 0 (للصورة المصغرة)
    if grouped_segments:
        first_segment = grouped_segments[0]
        original_start = first_segment['start']
        first_segment['start'] = 0.0
        first_segment['duration'] = first_segment['end'] - 0.0
        print(f"تم تعديل المقطع الأول ليبدأ من 0s بدلاً من {original_start:.2f}s (للصورة المصغرة)")
    
    return grouped_segments


def create_synchronized_text_clips(grouped_segments: List[dict]) -> List[ImageClip]:
    """
    إنشاء مقاطع نصية متزامنة مع الصوت
    
    Args:
        grouped_segments: قائمة المقاطع المجمعة من group_words_into_segments
        
    Returns:
        قائمة بمقاطع النص مع التوقيت المحدد
    """
    text_clips = []
    
    for i, segment in enumerate(grouped_segments):
        # إنشاء مقطع نصي
        clip = create_text_clip_with_pil(
            text=segment["text"],
            duration=segment["duration"]
        )
        
        # تعيين وقت البداية
        clip = clip.set_start(segment["start"])
        
        # إضافة تأثيرات الظهور والاختفاء
        fade_duration = min(0.1, segment["duration"] / 3)  # تأثير سريع
        if i == 0:
            clip = clip.fadein(0).fadeout(fade_duration)
        else :
            clip = clip.fadein(fade_duration).fadeout(fade_duration)


        text_clips.append(clip)
        
        print(f"مقطع {i+1}/{len(grouped_segments)}: '{segment['text'][:30]}...' "
              f"({segment['start']:.2f}s - {segment['end']:.2f}s)")
    
    return text_clips



# ============================================================================
# وظائف إنشاء الفيديو النهائي
# ============================================================================

def create_final_video(
    verse_text: str,
    verse_audio_path: str,
    video_paths: List[str],
    output_filename: str,
    logo_path: str,
    timing_data: dict = None
) -> None:
    """
    إنشاء الفيديو النهائي
    
    Args:
        verse_text: نص الآية
        verse_audio_path: مسار ملف الصوت
        video_paths: قائمة مسارات الفيديوهات
        output_filename: اسم ملف الإخراج
        logo_path: مسار الشعار
        timing_data: بيانات توقيت الكلمات (اختياري) - يحتوي على words و segments
    """
    print(f"جارٍ إنشاء الفيديو النهائي '{output_filename}'...")
    
    # تحميل الصوت
    audio_clip = AudioFileClip(verse_audio_path)
    audio_duration = audio_clip.duration
    
    # إنشاء مقاطع الفيديو
    video_clips = create_video_clips(video_paths, audio_duration, audio_clip)
    final_clip = concatenate_videoclips(video_clips)
    final_clip = final_clip.set_audio(audio_clip)
    
    # إضافة الطبقة السوداء الشبه شفافة
    black_overlay = ColorClip(size=final_clip.size, color=(0, 0, 0))
    black_overlay = black_overlay.set_duration(final_clip.duration)
    black_overlay = black_overlay.set_opacity(Config.BLACK_OVERLAY_OPACITY)
    final_clip = CompositeVideoClip([final_clip, black_overlay])
    
    # إنشاء وإضافة مقاطع النص
    if Config.USE_WORD_SYNC and timing_data:
        # استخدام المزامنة الصوتية كلمة بكلمة
        print("استخدام المزامنة الصوتية كلمة بكلمة...")
        grouped_segments = group_words_into_segments(
            timing_data['words'],
            timing_data['segments']
        )
        text_clips = create_synchronized_text_clips(grouped_segments)
        
        # إضافة النصوص إلى الفيديو (التوقيت محدد مسبقاً)
        for text_clip in text_clips:
            text_clip = text_clip.set_position(('center', 'center'))
            final_clip = CompositeVideoClip([final_clip, text_clip])
    else:
        # استخدام الطريقة التقليدية
        print("استخدام الطريقة التقليدية لعرض النص...")
        text_clips = create_text_clips(verse_text, audio_duration)
        
        # حساب أوقات بداية كل مقطع نصي
        text_durations = [clip.duration for clip in text_clips]
        text_start_times = [sum(text_durations[:i]) for i in range(len(text_durations))]
        
        # إضافة النصوص إلى الفيديو
        for i, text_clip in enumerate(text_clips):
            text_clip = text_clip.set_position(('center', 'center')).set_start(text_start_times[i])
            final_clip = CompositeVideoClip([final_clip, text_clip])

    
    # إضافة الشعار
    logo = ImageClip(logo_path).set_duration(final_clip.duration).resize(width=Config.LOGO_WIDTH)
    final_clip = CompositeVideoClip([
        final_clip.set_position(("left", "top")),
        logo.set_position(Config.LOGO_POSITION)
    ])
    
    # حساب الوقت المتوقع للإنشاء وإرسال رسالة
    estimated_time = 4 * 24 / 60 * audio_duration
    try:
        asyncio.run(send_telegram_message(
            f"جاري إنشاء الفيديو {output_filename}\nسيستغرق حوالي {estimated_time:.1f} دقيقة"
        ))
    except Exception as e:
        print(f"خطأ في إرسال رسالة التقدير: {e}")
    
    # كتابة الفيديو النهائي
    final_clip.write_videofile(
        output_filename,
        codec=Config.VIDEO_CODEC,
        fps=Config.VIDEO_FPS
    )
    
    print(f"تم إنشاء الفيديو النهائي '{output_filename}' بنجاح.")


def is_audio_duration_valid(duration: float) -> bool:
    """
    التحقق من أن مدة الصوت ضمن النطاق المقبول
    
    Args:
        duration: مدة الصوت بالثواني
        
    Returns:
        True إذا كانت المدة مقبولة، False خلاف ذلك
    """
    return Config.MIN_AUDIO_DURATION <= duration <= Config.MAX_AUDIO_DURATION


def cleanup_audio_file(audio_path: str) -> None:
    """
    حذف ملف الصوت المؤقت
    
    Args:
        audio_path: مسار ملف الصوت
    """
    try:
        if os.path.exists(audio_path):
            # انتظار قصير للتأكد من إغلاق الملف
            time.sleep(0.5)
            os.remove(audio_path)
            print(f"تم حذف الملف الصوتي المؤقت: {audio_path}")
    except Exception as e:
        print(f"خطأ في حذف الملف الصوتي: {e}")
        # محاولة ثانية بعد انتظار أطول
        try:
            time.sleep(2)
            if os.path.exists(audio_path):
                os.remove(audio_path)
                print(f"تم حذف الملف في المحاولة الثانية")
        except:
            print(f"فشل حذف الملف: {audio_path}. سيتم تجاهله.")


def process_verse(
    verse_number: int,
    video_folder: str,
    output_folder: str,
    logo_path: str,
    remaining_videos: int,
    stats: Statistics = None
) -> Tuple[bool, int]:
    """
    معالجة آية واحدة وإنشاء الفيديو الخاص بها
    
    Args:
        verse_number: رقم الآية
        video_folder: مجلد الفيديوهات
        output_folder: مجلد الإخراج
        logo_path: مسار الشعار
        remaining_videos: عدد الفيديوهات المتبقية
        stats: كائن الإحصائيات
        
    Returns:
        tuple: (نجحت العملية، عدد الفيديوهات المتبقية المحدث)
    """
    audio_path = None
    timing_data = None
    verse_text = None
    
    try:
        # محاولة استرجاع البيانات مع التوقيت (إذا كانت المزامنة مفعلة)
        if Config.USE_WORD_SYNC:
            try:
                print(f"محاولة استرجاع بيانات الآية {verse_number} مع التوقيت...")
                verse_data = fetch_verse_with_timing(verse_number)
                
                # تحميل الملف الصوتي
                audio_path = download_audio_file(verse_data['audio_url'], verse_number)
                verse_text = verse_data['verse_text']
                timing_data = {
                    'words': verse_data['words'],
                    'segments': verse_data['segments']
                }
                
                print(f"تم استرجاع بيانات الآية {verse_number} مع التوقيت بنجاح")
                
            except Exception as e:
                print(f"فشل استرجاع البيانات مع التوقيت: {e}")
                print("التراجع إلى API التقليدي...")
                # التراجع إلى الطريقة التقليدية
                audio_path = fetch_verse_audio(verse_number)
                verse_text = fetch_verse_text(verse_number)
                timing_data = None
        else:
            # استخدام API التقليدي
            audio_path = fetch_verse_audio(verse_number)
            verse_text = fetch_verse_text(verse_number)
        
        audio_clip = AudioFileClip(audio_path)
        audio_duration = audio_clip.duration
        
        # إغلاق الملف بشكل صحيح
        audio_clip.close()
        del audio_clip
        gc.collect()
        time.sleep(0.3)  # انتظار قصير للتأكد من إغلاق الملف
        
        # التحقق من مدة الصوت
        if not is_audio_duration_valid(audio_duration):
            print(f"تخطي الآية رقم {verse_number} لأن طول الملف الصوتي ({audio_duration:.1f}s) غير مناسب.")
            cleanup_audio_file(audio_path)
            
            # تسجيل في الإحصائيات
            if stats:
                stats.mark_skipped(verse_number)
            
            try:
                asyncio.run(send_telegram_message(f"⏭ تم تخطي الآية {verse_number}"))
            except:
                pass
            
            time.sleep(Config.SLEEP_ON_SKIP)
            return False, remaining_videos
        
        # التحقق من عدد الفيديوهات المتبقية
        if remaining_videos == 0:
            save_start_verse(verse_number)
            cleanup_audio_file(audio_path)
            
            try:
                asyncio.run(send_telegram_message("تم الانتهاء من إنشاء الفيديوهات المطلوبة"))
            except:
                pass
            
            sys.exit()
        
        # إنشاء الفيديو
        print(f"جارٍ إنشاء الفيديو للآية رقم {verse_number}...")
        random_videos = select_random_videos(video_folder, Config.NUM_VIDEOS_PER_CLIP)
        output_filename = os.path.join(output_folder, f"final_video_{verse_number}.mp4")
        
        create_final_video(
            verse_text, 
            audio_path, 
            random_videos, 
            output_filename, 
            logo_path,
            timing_data=timing_data
        )

        
        # حذف الملف الصوتي المؤقت
        cleanup_audio_file(audio_path)
        
        # تسجيل في الإحصائيات
        if stats:
            stats.mark_created(verse_number)
        
        # إرسال رسالة النجاح
        try:
            asyncio.run(send_telegram_message(
                f"✅ تم إنشاء الفيديو {output_filename}\nتم إنهاء الفيديو {remaining_videos}."
            ))
        except:
            pass
        
        # تحرير الذاكرة
        gc.collect()
        
        # استراحة قبل الفيديو التالي
        print(f"تم إنهاء الفيديو {remaining_videos}. استراحة {Config.SLEEP_BETWEEN_VIDEOS} ثانية لتحرير الموارد...")
        time.sleep(Config.SLEEP_BETWEEN_VIDEOS)
        
        return True, remaining_videos - 1
        
    except Exception as e:
        print(f"خطأ أثناء معالجة الآية رقم {verse_number}: {e}")
        
        # حذف الملف الصوتي في حالة الخطأ
        if audio_path:
            cleanup_audio_file(audio_path)
        
        # تسجيل في الإحصائيات
        if stats:
            stats.mark_failed(verse_number, str(e))
            if "api" in str(e).lower() or "request" in str(e).lower():
                stats.mark_api_error()
            else:
                stats.mark_video_error()
        
        try:
            asyncio.run(send_telegram_message(f"❌ خطأ في الآية {verse_number}: {str(e)}"))
        except:
            pass
        
        return False, remaining_videos


def create_videos_batch(
    start_verse: int,
    end_verse: int,
    video_folder: str,
    output_folder: str,
    logo_path: str,
    num_videos: int
) -> Statistics:
    """
    إنشاء مجموعة من الفيديوهات للآيات
    
    Args:
        start_verse: رقم آية البداية
        end_verse: رقم آية النهاية
        video_folder: مجلد الفيديوهات
        output_folder: مجلد الإخراج
        logo_path: مسار الشعار
        num_videos: عدد الفيديوهات المطلوب إنشاؤها
        
    Returns:
        كائن الإحصائيات
    """
    print(f"جارٍ إنشاء الفيديوهات للآيات من {start_verse} إلى {end_verse}...")
    
    # إنشاء كائن الإحصائيات
    stats = Statistics(
        total_requested=num_videos,
        verse_range=(start_verse, end_verse)
    )
    
    remaining_videos = num_videos
    
    # إرسال رسالة البداية
    try:
        asyncio.run(send_telegram_message(
            f"🚀 *بدء إنشاء الفيديوهات*\n\n"
            f"📊 العدد المطلوب: {num_videos} فيديو\n"
            f"📖 نطاق الآيات: من {start_verse} إلى {end_verse}\n"
            f"⏰ الوقت: {stats.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode="Markdown"
        ))
    except:
        pass
    
    for verse_number in range(start_verse, end_verse + 1):
        success, remaining_videos = process_verse(
            verse_number,
            video_folder,
            output_folder,
            logo_path,
            remaining_videos,
            stats
        )
        
        # إذا انتهى العدد المطلوب، التوقف
        if remaining_videos == 0:
            break
    
    # إنهاء الإحصائيات
    stats.finalize()
    
    print("تم إنشاء الفيديوهات بنجاح.")
    
    # إرسال التقرير النهائي
    try:
        report = stats.generate_report()
        asyncio.run(send_telegram_message(report, parse_mode="Markdown"))
    except Exception as e:
        print(f"خطأ في إرسال التقرير النهائي: {e}")
    
    return stats


# ============================================================================
# البرنامج الرئيسي
# ============================================================================

def main():
    """الدالة الرئيسية للبرنامج"""
    
    # قراءة إعدادات التشغيل
    num_videos = Config.DEFAULT_NUM_VIDEOS
    start_verse = load_start_verse()
    end_verse = Config.TOTAL_VERSES
    
    print("=" * 60)
    print("برنامج إنشاء فيديوهات القرآن الكريم")
    print("=" * 60)
    print(f"عدد الفيديوهات المطلوبة: {num_videos}")
    print(f"نطاق الآيات: من {start_verse} إلى {end_verse}")
    print(f"مجلد الفيديوهات: {Config.VIDEO_STOCK_FOLDER}")
    print(f"مجلد الإخراج: {Config.OUTPUT_FOLDER}")
    print("=" * 60)
    
    # إنشاء الفيديوهات
    stats = create_videos_batch(
        start_verse=start_verse,
        end_verse=end_verse,
        video_folder=Config.VIDEO_STOCK_FOLDER,
        output_folder=Config.OUTPUT_FOLDER,
        logo_path=Config.LOGO_PATH,
        num_videos=num_videos
    )
    
    # طباعة الإحصائيات في الكونسول
    print("\n" + "=" * 60)
    print("تقرير الإحصائيات النهائي:")
    print("=" * 60)
    print(f"الفيديوهات المنشأة: {stats.total_created}/{stats.total_requested}")
    print(f"الآيات المتخطاة: {stats.total_skipped}")
    print(f"الفيديوهات الفاشلة: {stats.total_failed}")
    print(f"نسبة النجاح: {stats.get_success_rate():.1f}%")
    print(f"المدة الإجمالية: {stats.format_duration(stats.get_duration())}")
    print("=" * 60)


if __name__ == "__main__":
    main()
