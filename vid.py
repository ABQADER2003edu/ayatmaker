import os
import requests
from moviepy.editor import *
import random
import textwrap
from moviepy.video.fx.fadein import fadein
from moviepy.video.fx.fadeout import fadeout
import pandas as pd
from telegram import Bot
import asyncio
import time
import sys
import PIL
PIL.Image.ANTIALIAS = PIL.Image.LANCZOS
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# token,chat_id  --- min and max duration _____ font , font_size

async def send_message(tex="تم النشر"):
    bot = Bot(token="7086155068:AAGq9IPEqr5x98dfgAXiKkq65I7Jku48T9A")
    await bot.send_message(chat_id="859737481", text=tex)

def write_to_file(text): 
    text_aya = f'{text}'
    try:
        with open('StartAya.txt', 'w') as file:
            file.write(text_aya)
    except IOError as e:
        print(f'حدث خطأ أثناء محاولة كتابة الملف: {e}')

def get_verse_text(verse_number):
    retries = 5
    for attempt in range(retries):
        try:
            print(f"جارٍ استرجاع النص للآية رقم {verse_number}... (محاولة {attempt + 1}/{retries})")
            url = f"http://api.alquran.cloud/v1/ayah/{verse_number}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            verse_data = response.json()
            verse_text = verse_data['data']['text']
            print(f"تم استرجاع النص للآية رقم {verse_number}.")
            return verse_text
        except requests.RequestException as e:
            print(f"خطأ أثناء استرجاع النص للآية رقم {verse_number}: {e}")
            if attempt < retries - 1:
                print("إعادة المحاولة بعد 45 ثانية...")
                time.sleep(45)
            else:
                print(f"فشل استرجاع النص للآية رقم {verse_number} بعد {retries} محاولات.")
                raise

def download_audio_file(audio_url, verse_number, audio_folder="temp_audio"):
    """
    تحميل ملف الصوت من URL وحفظه محلياً
    
    Args:
        audio_url (str): رابط ملف الصوت
        verse_number (int): رقم الآية
        audio_folder (str): مجلد حفظ الملفات الصوتية
    
    Returns:
        str: مسار الملف المحلي
    """
    # إنشاء مجلد الصوت إذا لم يكن موجوداً
    if not os.path.exists(audio_folder):
        os.makedirs(audio_folder)
    
    local_filename = os.path.join(audio_folder, f"audio_{verse_number}.mp3")
    
    # تحميل الملف
    retries = 5
    for attempt in range(retries):
        try:
            print(f"جارٍ تحميل ملف الصوت للآية رقم {verse_number}... (محاولة {attempt + 1}/{retries})")
            response = requests.get(audio_url, timeout=30, stream=True)
            response.raise_for_status()
            
            with open(local_filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"تم تحميل ملف الصوت للآية رقم {verse_number}.")
            return local_filename
            
        except requests.RequestException as e:
            print(f"خطأ أثناء تحميل ملف الصوت للآية رقم {verse_number}: {e}")
            if attempt < retries - 1:
                print("إعادة المحاولة بعد 45 ثانية...")
                time.sleep(45)
            else:
                print(f"فشل تحميل ملف الصوت للآية رقم {verse_number} بعد {retries} محاولات.")
                raise

def get_verse_audio(verse_number):
    retries = 5
    for attempt in range(retries):
        try:
            print(f"جارٍ استرجاع رابط ملف الصوت للآية رقم {verse_number}... (محاولة {attempt + 1}/{retries})")
            url = f"http://api.alquran.cloud/v1/ayah/{verse_number}/ar.alafasy"
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            audio_url = response.json()['data']['audio']
            print(f"تم استرجاع رابط ملف الصوت للآية رقم {verse_number}.")
            
            # تحميل الملف الصوتي محلياً
            local_audio_path = download_audio_file(audio_url, verse_number)
            return local_audio_path
            
        except requests.RequestException as e:
            print(f"خطأ أثناء استرجاع ملف الصوت للآية رقم {verse_number}: {e}")
            if attempt < retries - 1:
                print("إعادة المحاولة بعد 45 ثانية...")
                time.sleep(45)
            else:
                print(f"فشل استرجاع ملف الصوت للآية رقم {verse_number} بعد {retries} محاولات.")
                raise

def choose_random_videos(video_folder, num_videos):
    print("جارٍ اختيار مقاطع الفيديو العشوائية...")
    videos = os.listdir(video_folder)
    random_videos = random.sample(videos, num_videos)
    video_paths = [os.path.join(video_folder, video) for video in random_videos]
    print("تم اختيار مقاطع الفيديو العشوائية.")
    return video_paths

def get_video_dimensions(video_path):
    video = VideoFileClip(video_path)
    width = video.size[0]
    height = video.size[1]
    video.close()
    return width, height

# للتعديل علي مدة الانتقال 
def get_video_clips(random_videos, duration, audio_clip, transition_duration=.4):
    video_clips = []
    i = 0
    for video_path in random_videos:
        width, height = get_video_dimensions(video_path)
        video_clip = VideoFileClip(video_path).resize((1080, 1920))
        video_clip = video_clip.set_duration(duration)
        if i > 0:
            video_clip = fadein(video_clip, duration=transition_duration)
        video_clip = fadeout(video_clip, duration=transition_duration)
        video_clips.append(video_clip)
        i += 1 
    total_duration = sum(clip.duration for clip in video_clips)
    if total_duration < audio_clip.duration:
        blank_duration = audio_clip.duration - total_duration
        blank_clip = ColorClip(size=(1080, 1920), color=(0, 0, 0)).set_duration(blank_duration)
        video_clips.append(blank_clip)
    return video_clips

def get_arabic_font(fontsize=100):
    """
    البحث عن خط عربي مناسب في النظام
    """
    # قائمة بالخطوط العربية المحتملة
    arabic_fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/kacst/KacstBook.ttf",
        "/usr/share/fonts/truetype/kacst-one/KacstOne.ttf",
        "/usr/share/fonts/truetype/fonts-arabeyes/ae_Arab.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf"
    ]
    
    # البحث عن أول خط متاح
    for font_path in arabic_fonts:
        try:
            return ImageFont.truetype("Fonts/Amiri-Regular.ttf", fontsize)
        except:
            continue
    
    # إذا لم يتم العثور على أي خط، استخدام الخط الافتراضي
    print("تحذير: لم يتم العثور على خط عربي، استخدام الخط الافتراضي")
    return ImageFont.truetype("Fonts/Amiri-Regular.ttf", fontsize)

def create_text_clip_with_pil(text, duration, fontsize=100, color='white', stroke_color='black', stroke_width=2, size=(1080, 1920)):
    """
    إنشاء مقطع نصي باستخدام PIL بدلاً من TextClip
    """
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

def calculate_text_width(audio_duration):
    """
    حساب العرض المناسب للنص (width) بناءً على مدة الملف الصوتي.

    Args:
        audio_duration (float): مدة الملف الصوتي (بالثواني).

    Returns:
        int: العرض المناسب للنص.
    """
    if audio_duration <= 5:
        return 15
    elif audio_duration <= 15:
        return 30
    elif audio_duration <= 25:
        return 40
    else:
        return 40

def create_final_videos(start_verse, end_verse, video_folder, output_folder, logo_path, num_videos_per_video, num_vid):
    print(f"جارٍ إنشاء الفيديوهات للآيات من {start_verse} إلى {end_verse}...")
    for verse_number in range(start_verse, end_verse + 1):
        try:
            verse_audio_path = get_verse_audio(verse_number)
            audio_clip = AudioFileClip(verse_audio_path)
            audio_duration = audio_clip.duration
            
            if audio_duration <= 15 or audio_duration >= 45:
                print(f"تخطي الآية رقم {verse_number} لأن طول الملف الصوتي غير مناسب.")
                audio_clip.close()
                # حذف الملف الصوتي المؤقت
                if os.path.exists(verse_audio_path):
                    os.remove(verse_audio_path)
                try:
                    asyncio.run(send_message(f"تم تخطي الاية {verse_number}"))
                except:
                    print("no mass")
                continue
            
            elif num_vid == 0:
                write_to_file(verse_number)
                audio_clip.close()
                # حذف الملف الصوتي المؤقت
                if os.path.exists(verse_audio_path):
                    os.remove(verse_audio_path)
                try:
                    asyncio.run(send_message("تم الانتهاء من أنشاء الفيديوهات المطلوبة "))
                except:
                    print("no mass")
                sys.exit()
            
            audio_clip.close()
            
            print(f"جارٍ إنشاء الفيديو للآية رقم {verse_number}...")
            verse_text = get_verse_text(verse_number)
            random_videos = choose_random_videos(video_folder, num_videos_per_video)
            output_filename = os.path.join(output_folder, f"final_video_{verse_number}.mp4")
            
            create_final_video(verse_text, verse_audio_path, random_videos, output_filename, logo_path)
            
            # حذف الملف الصوتي المؤقت بعد الانتهاء
            if os.path.exists(verse_audio_path):
                os.remove(verse_audio_path)
                print(f"تم حذف الملف الصوتي المؤقت: {verse_audio_path}")
            
            try:
                asyncio.run(send_message(f"تم انشاء الفيديو {output_filename} "))
            except:
                print("no")
            
            num_vid = num_vid - 1
            
        except Exception as e:
            print(f"خطأ أثناء معالجة الآية رقم {verse_number}: {e}")
            try:
                asyncio.run(send_message(f"خطأ في الآية {verse_number}: {str(e)}"))
            except:
                print("no mass")
            continue
    
    print("تم إنشاء الفيديوهات بنجاح.")

def create_final_video(verse_text, verse_audio_path, random_videos, output_filename, logo_path, duration_per_video=2):
    print(f"جارٍ إنشاء الفيديو النهائي '{output_filename}'...")
    audio_clip = AudioFileClip(verse_audio_path)
    audio_duration = audio_clip.duration
    text_width = calculate_text_width(audio_duration)
    lines = textwrap.wrap(verse_text, width=text_width)
    num_lines = len(lines)
    
    text_durations = [audio_clip.duration / num_lines] * num_lines
    text_clips = [
        create_text_clip_with_pil(
            line, 
            duration,
            fontsize=100,
            color='white',
            stroke_color='black',
            stroke_width=2,
            size=(1080, 1920)
        )
        .fadein(0.4 if i > 0 else 0)
        .fadeout(0.4)
        for i, (line, duration) in enumerate(zip(lines, text_durations))
    ]
    
    total_duration = len(random_videos) * len(text_clips)
    video_clips = get_video_clips(random_videos, audio_clip.duration / len(random_videos), audio_clip)
    final_clip = concatenate_videoclips(video_clips)
    final_clip = final_clip.set_audio(audio_clip)
    
    # إضافة الطبقة السوداء الشبه شفافة
    black_overlay = ColorClip(size=final_clip.size, color=(0, 0, 0))
    black_overlay = black_overlay.set_duration(final_clip.duration)
    black_overlay = black_overlay.set_opacity(0.55)
    final_clip = CompositeVideoClip([final_clip, black_overlay])
    
    text_durations = [text_clip.duration for text_clip in text_clips]
    text_start_times = [sum(text_durations[:i]) for i in range(len(text_durations))]
    
    for i, text_clip in enumerate(text_clips):
        text_clip = text_clip.set_position(('center', 'center')).set_start(text_start_times[i])
        final_clip = CompositeVideoClip([final_clip, text_clip])
    
    logo = (ImageClip(logo_path).set_duration(final_clip.duration).resize(width=200))
    final_clip = CompositeVideoClip([final_clip.set_position(("left", "top")), logo.set_position((0.1, 20))])
    
    timetoend = 4*24/60*audio_duration
    try:
        asyncio.run(send_message(f"  جاري انشاء الفيديو {output_filename} سيستغرق حوالي {timetoend} دقيقة "))
    except:
        print("no")
    
    final_clip.write_videofile(output_filename, codec='libx264', fps=30)
    print(f"تم إنشاء الفيديو النهائي '{output_filename}' بنجاح.")
    
    new_row = {
        'File': f"{output_filename}",
        'Youtube Title': "F",
        'Youtube Status': "F",
        'Telegram Status': "F",
        'Full Automated Status': "F",
        'TikTok Status': "F",
        'Insta Status': "F",
        'Full Status': "F"
    }
    nr = pd.DataFrame([new_row])
    post_plan = pd.read_csv("post.csv")
    post_plan = pd.concat([post_plan, nr], ignore_index=True)
    post_plan.to_csv("post.csv", index=False)

# استخدام الدوال
if __name__ == "__main__":
    num_videos = int(input("Enter Number of Videos You Want To Create : "))
    with open('StartAya.txt', 'r') as file:
        value = file.read().strip()
        int_value = int(value)
    start_verse = int_value
    end_verse = 6236
    video_folder = "Stock_Videos"
    output_folder = "OutPut"
    logo_path = "logo.png"
    num_videos_per_video = 4
    create_final_videos(start_verse, end_verse, video_folder, output_folder, logo_path, num_videos_per_video, num_videos)