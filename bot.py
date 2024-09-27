import os
import requests
import subprocess
import json
import threading
import time
from pysrt import SubRipTime , SubRipItem
import pysrt
from pyrogram import Client, filters
with open('config.json') as config_file:
    config = json.load(config_file)

api_id = int(config['api_id'])
api_hash = config['api_hash']
bot_token = config['bot_token']

app = Client(
    "bot",
    api_id=api_id,
    api_hash=api_hash,
    bot_token=bot_token
)

video_tasks = []

def download_file(url, filename, chat_id, message_id):
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    downloaded = 0
    start_time = time.time()
    
    with open(filename, 'wb') as f:
        last_update_time = time.time() 
        previous_message = "" 
        for data in response.iter_content(chunk_size=1024):
            f.write(data)
            downloaded += len(data)
            current_time = time.time()
            elapsed_time = current_time - start_time
            
            if elapsed_time > 0:
                speed = (downloaded / (1024 * 1024)) / elapsed_time
                remaining_time = (total_size - downloaded) / (speed * 1024 * 1024)  # seconds
            else:
                speed = 0
                remaining_time = float('inf')
            
            if current_time - last_update_time >= 1:
                message_content = (
                    f"دانلود: {downloaded / (1024 * 1024):.2f} MB از {total_size / (1024 * 1024):.2f} MB\n"
                    f"سرعت: {speed:.2f} MB/s\n"
                    f"زمان باقی‌مانده: {remaining_time:.2f} ثانیه"
                )
                
                if message_content != previous_message:
                    app.edit_message_text(chat_id, message_id, message_content)
                    previous_message = message_content
                last_update_time = current_time

def add_watermark(video_path, output_path, watermark_duration=20):
    #watermark_text = "بزرگترین کانال دانلود سریال کره ای\n@RiRiKdrama |  ریری کیدراما"
    #font_path = 'Sahel-Bold.ttf'
    watermarked_segment_path = 'watermarked_segment.mkv'
    remaining_part_path = 'remaining_part.mkv'
    concat_file_path = 'concat_list.txt'

    watermark_cmd = [
    'ffmpeg',
    '-i', video_path,
    '-i', 'Watermark.png',
    '-filter_complex', (
        f"[1]scale=iw*1:-1[wm];[0][wm]overlay=x=10:y=10"
    ),
    '-t', str(watermark_duration),
    '-c:v', 'libx264',
    '-crf', '23',
    '-preset', 'veryslow',
    '-c:a', 'copy',
    '-y',
    watermarked_segment_path 
    ]
    subprocess.run(watermark_cmd)

    extract_cmd = [
        'ffmpeg',
        '-i', video_path,
        '-ss', str(watermark_duration),
        '-c:v', 'copy',
        '-c:a', 'copy',
        '-y',
        remaining_part_path
    ]
    subprocess.run(extract_cmd)

    print(watermarked_segment_path, remaining_part_path, output_path)
    
    with open(concat_file_path, 'w') as f:
        f.write(f"file '{watermarked_segment_path}'\n")
        f.write(f"file '{remaining_part_path}'\n")

    concat_cmd = [
        'ffmpeg',
        '-f', 'concat',
        '-safe', '0',
        '-i', concat_file_path,
        '-c', 'copy',
        '-y',
        output_path
    ]
    subprocess.run(concat_cmd)


    for file_path in [watermarked_segment_path, remaining_part_path, concat_file_path]:
        if os.path.exists(file_path):
            os.remove(file_path)
    return output_path

def seconds_to_subrip_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds - int(seconds)) * 1000)
    return SubRipTime(hours=hours, minutes=minutes, seconds=secs, milliseconds=milliseconds)

def add_custom_subtitles(subtitle_file, custom_subtitle_path):
    subs = pysrt.open(subtitle_file)

    # Define custom subtitles
    custom_subtitles = [
        {
            "start": SubRipTime(0, 0, 1, 0),
            "end": SubRipTime(0, 0, 8, 0),
            "text": '<font color="#ef6d80">꧁ بزرگترین کانال دانلود سریال کره ای ꧂\n@RiRiKdrama ┊ ریری کیدراما</font>'
        },
        {
            "start": SubRipTime(0, 0, 0, 0),  # Placeholder, will be updated
            "end": SubRipTime(0, 0, 5, 0),
            "text": '<font color="#62ffd7">:) لطفا برای حمایت عضو کانال تلگرامی ما بشید\n《 @RiRiKdrama 》</font>'
        }
    ]

    # Add the first custom subtitle at the start
    subs.append(
        SubRipItem(
            index=len(subs) + 1,
            start=custom_subtitles[0]["start"],
            end=custom_subtitles[0]["end"],
            text=custom_subtitles[0]["text"]
        )
    )

    # Find a place to add the second custom subtitle
    empty_location_found = False
    current_time = 0
    duration = 60  # Assume the video is 60 seconds long
    subtitle_duration = 5  # Duration of the custom subtitle

    while current_time < duration - subtitle_duration:
        # Check if there's a 5-second gap without existing subtitles
        is_empty = True
        for sub in subs:
            start_time = seconds_to_subrip_time(current_time)
            end_time = seconds_to_subrip_time(current_time + subtitle_duration)
            if sub.start <= end_time and sub.end >= start_time:
                is_empty = False
                break
        
        if is_empty:
            # If an empty spot is found, add the second custom subtitle
            custom_subtitles[1]["start"] = seconds_to_subrip_time(current_time)
            custom_subtitles[1]["end"] = seconds_to_subrip_time(current_time + subtitle_duration)

            subs.append(
                SubRipItem(
                    index=len(subs) + 1,
                    start=custom_subtitles[1]["start"],
                    end=custom_subtitles[1]["end"],
                    text=custom_subtitles[1]["text"]
                )
            )
            empty_location_found = True
            break
        
        current_time += 1  # Check each second

    if not empty_location_found:
        print("Could not find an empty location for the second custom subtitle.")

    # Sort subtitles by start time to ensure they are in the correct order
    subs.sort()

    # Write the modified subtitles back to a new file
    subs.save(custom_subtitle_path, encoding='utf-8')
    
def add_soft_subtitle(video_file, subtitle_file, output_file):
    custom_subtitle_file = 'custom_subtitle.srt'
    add_custom_subtitles(subtitle_file, custom_subtitle_file)

    subprocess.run([
        'ffmpeg', '-i', video_file, '-i', custom_subtitle_file, '-c', 'copy', '-c:s', 'srt', 
        '-metadata:s:s:0', 'title=@RiRiMovies', '-disposition:s:0', 'default', output_file
    ])

def trim_video(input_file, output_file, duration=60):
    subprocess.run([
        'ffmpeg', '-i', input_file, '-t', str(duration), '-c', 'copy', output_file
    ])

def process_video_with_links(video_link, subtitle_link, client, chat_id, output_name):
    output_path = output_name + '.mkv'
    message = client.send_message(chat_id, f"در حال پردازش: {output_path}...")
    message_id = message.id

    downloaded = f'downloaded_{output_path}'
    download_file(video_link, downloaded, chat_id, message_id)
    download_file(subtitle_link, output_name + '_subtitle.srt', chat_id, message_id)

    processing_start_time = time.time()
    
    watermarked_video_path = f'watermarked_{output_name}.mkv'
    add_watermark(downloaded, watermarked_video_path , 20)

    final_output_path = f'{output_name}.mkv'
    add_soft_subtitle(watermarked_video_path, output_name + '_subtitle.srt', final_output_path)

    processing_end_time = time.time()
    processing_time = processing_end_time - processing_start_time
    client.send_message(chat_id, f"زمان پردازش: {processing_time:.2f} ثانیه")

    trimmed_output_path = output_name + '_trimmed.mkv'
    trim_video(final_output_path, trimmed_output_path, duration=60)
    client.send_document(chat_id, trimmed_output_path , thumb="cover.jpg")
    client.send_document(chat_id, final_output_path, thumb="cover.jpg")
    client.send_message(chat_id, f"پردازش {output_name} کامل شد!")

    os.remove(downloaded)
    os.remove(output_name + '_subtitle.srt')
    os.remove(watermarked_video_path)
    os.remove(final_output_path)
    os.remove(trimmed_output_path)

@app.on_message(filters.command("start"))
def start_processing(client, message):
    global video_tasks
    video_tasks = []
    client.send_message(message.chat.id, "لطفاً لینک‌های ویدیو و زیرنویس و نام فایل خروجی را ارسال کنید.\nبه صورت زیر:\nvideo_link | subtitle_link | output_name")
    directory2 = './'
    extensions_to_delete = ['.srt', '.mkv', '.mp4']
    for filename in os.listdir(directory2):
        if any(filename.endswith(ext) for ext in extensions_to_delete):
            file_path = os.path.join(directory2, filename)
            if os.path.isfile(file_path):
                    os.remove(file_path)

@app.on_message(filters.text)
def collect_links(client, message):
    tasks = message.text.splitlines()
    
    for task in tasks:
        if task.strip():
            video_link, subtitle_link, output_name = task.split(" | ")
            video_tasks.append((video_link.strip(), subtitle_link.strip(), output_name.strip()))
    
    if video_tasks:
        client.send_message(message.chat.id, "لینک‌ها دریافت شد. در حال پردازش...")
        for video_link, subtitle_link, output_name in video_tasks:
            threading.Thread(target=process_video_with_links, args=(video_link, subtitle_link, client, message.chat.id, output_name)).start()

        video_tasks.clear()

@app.on_message(filters.photo & filters.private)
async def handle_cover(client, message):
    try:
        cover_image_path = 'cover.jpg'
        
        if os.path.exists(cover_image_path):
            os.remove(cover_image_path)
        
        downloaded_file_path = await message.download()
        os.rename(downloaded_file_path, cover_image_path)
        
        await message.reply("عکس کاور دریافت شد...")
    except Exception as e:
        await message.reply(f"Error handling cover image: {str(e)}")

app.run()
