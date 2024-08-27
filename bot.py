import os
import requests
import json
from urllib.parse import urlparse, parse_qs, unquote
from pyrogram import Client, filters
from pyrogram.types import Message
from moviepy.config import change_settings
import subprocess
import time
import asyncio
from pyrogram.errors import FloodWait
import sys
import re
import tqdm
import uvloop

change_settings({"IMAGEMAGICK_BINARY": r"/ImageMagick-7.1.1-Q16-HDRI/magick.exe"})

with open('config.json') as config_file:
    config = json.load(config_file)

api_id = int(config['api_id'])
api_hash = config['api_hash']
bot_token = config['bot_token']

uvloop.install()
app = Client(
    "bot",
    api_id=api_id,
    api_hash=api_hash,
    bot_token=bot_token
)

user_video_paths = {}
user_subtitle_paths = {}
user_cover_paths = {}
user_states = {}
ffmpeg_process = None

def restart_bot():
    """Function to restart the bot."""
    python_executable = sys.executable
    script_path = os.path.abspath(__file__)

    restart_command = [python_executable, script_path]

    try:
        subprocess.Popen(restart_command)
    except Exception as e:
        print(f"Error during restart: {str(e)}")
        sys.exit(1)

    sys.exit(0)

@app.on_message(filters.regex("restart_robot"))
async def handle_restart_robot(client: Client, message: Message):
    global ffmpeg_process
    if ffmpeg_process and ffmpeg_process.poll() is None:
        ffmpeg_process.terminate()
        try:
            ffmpeg_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            ffmpeg_process.kill()
        message.reply("FFmpeg process stopped.")
    else:
        message.reply("No FFmpeg process is running.")
    chat_id = message.chat.id
    await message.reply("Restarting the bot...")
    await asyncio.sleep(2)
    restart_bot()

def get_file_extension(url):
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    if 'response-content-type' in query_params:
        content_type = unquote(query_params['response-content-type'][0])
        if content_type == 'video/mp4':
            return '.mp4'
        elif content_type == 'video/x-matroska':
            return '.mkv'
    path = parsed_url.path
    _, ext = os.path.splitext(path)
    return ext if ext else '.mp4'

async def download_video(client, url, file_name, chat_id, downloading_text):
    file_extension = get_file_extension(url)
    video_path = f"downloaded_{file_name}{file_extension}"
    start_time = time.time()
    last_update_time = start_time
    update_interval = 1  # seconds

    try:
        response = requests.get(url, stream=True)
        total_size = int(response.headers.get('content-length', 0))

        with open(video_path, 'wb') as file, tqdm.tqdm(
            desc="Downloading",
            total=total_size,
            unit='B',
            unit_scale=True,
            unit_divisor=1024
        ) as bar:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
                bar.update(len(chunk))

                current_time = time.time()
                if current_time - last_update_time >= update_interval:
                    elapsed_time = current_time - start_time
                    percentage = (bar.n / total_size) * 100
                    speed = bar.n / elapsed_time
                    speed_kb_s = speed / 1024
                    speed_mb_s = speed / (1024 * 1024)
                    status_message = f"Downloading {bar.n / (1024 * 1024):.2f}MB ({percentage:.1f}%) of {total_size / (1024 * 1024):.2f}MB\nSpeed: {speed_kb_s:.2f} KB/s"

                    try:
                        await client.edit_message_text(chat_id, downloading_text.id, status_message)
                    except FloodWait as e:
                        await asyncio.sleep(e.x)

                    last_update_time = current_time

        return video_path
    except Exception as e:
        await client.send_message(chat_id, f"Failed to download video: {str(e)}")
        return None

async def run_ffmpeg_command(client, chat_id, command, status_message):
    try:
        text = await client.send_message(chat_id, status_message)
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        # Regex to extract progress information
        progress_re = re.compile(r'time=(\d{2}:\d{2}:\d{2}\.\d{2})\s+bitrate=\s*(\d+\.\d+)kbits/s\s+speed=\s*(\d+x)')

        # Read stdout line by line
        while True:
            line = process.stdout.readline()
            if not line:
                break

            # Match and extract progress information
            match = progress_re.search(line)
            if match:
                elapsed_time, bitrate, speed = match.groups()
                progress_message = f"Processing: {elapsed_time} | Bitrate: {bitrate} kbits/s | Speed: {speed}"
                # Update the message in Telegram
                await client.edit_message_text(chat_id, text.id, progress_message)

        # Wait for the process to finish
        process.wait()
        if process.returncode == 0:
            await client.edit_message_text(chat_id, text.id, f"{status_message} completed successfully.")
        else:
            await client.edit_message_text(chat_id, text.id, f"Error during FFmpeg command. Return code: {process.returncode}")

    except subprocess.CalledProcessError as e:
        error_message = f"Error during FFmpeg command: {str(e)}\nFFmpeg stderr: {e.stderr}"
        print(error_message)
        await client.send_message(chat_id, error_message)

async def add_watermark(client, chat_id, video_path, output_path, watermark_duration=20):
    watermark_text = "بزرگترین کانال دانلود سریال کره ای\n@RiRiKdrama |  ریری کیدراما"
    font_path = 'Sahel-Bold.ttf'
        
    watermarked_segment_path = 'watermarked_segment.mkv'
    watermark_cmd = [
        'ffmpeg',
        '-i', video_path,
        '-vf', (
            f"drawtext="
            f"text='{watermark_text}':"
            f"fontfile={font_path}:"
            f"fontsize=15:"
            f"fontcolor=white:"
            f"bordercolor=black:"
            f"borderw=2:"
            f"x=20:"
            f"y=60:"
            f"line_spacing=10"
        ),
        '-t', str(watermark_duration),
        '-c:v', 'libx264',
        '-crf', '18',
        '-preset', 'veryfast',
        '-c:a', 'copy',
        '-vsync', '0',
        '-y',
        watermarked_segment_path
    ]
    await run_ffmpeg_command(client, chat_id, watermark_cmd, "Adding watermark...")

    remaining_part_path = 'remaining_part.mkv'
    extract_cmd = [
        'ffmpeg',
        '-i', video_path,
        '-ss', str(watermark_duration),
        '-c:v', 'copy',
        '-c:a', 'copy',
        '-fflags', '+genpts',
        '-vsync', '0',
        '-y',
        remaining_part_path
    ]
    await run_ffmpeg_command(client, chat_id, extract_cmd, "Extracting remaining part...")

    concat_file_path = 'concat_list.txt'
    with open(concat_file_path, 'w') as f:
        f.write(f"file '{watermarked_segment_path}'\n")
        f.write(f"file '{remaining_part_path}'\n")

    concat_cmd = [
        'ffmpeg',
        '-f', 'concat',
        '-safe', '0',
        '-i', concat_file_path,
        '-c:v', 'copy',
        '-c:a', 'copy',
        '-vsync', '0',
        '-y',
        output_path
    ]
    await run_ffmpeg_command(client, chat_id, concat_cmd, "Finalizing video...")

    await client.send_message(chat_id, "Watermarking complete.")
    return output_path

async def add_subtitles(client, chat_id, video_path, subtitles_path, output_path):
    ffmpeg_command = [
        'ffmpeg',
        '-i', video_path,
        '-vf', f"subtitles={subtitles_path}",
        '-c:v', 'libx264',
        '-crf', '28',
        '-preset', 'ultrafast',
        '-c:a', 'copy',
        output_path
    ]
    
    await run_ffmpeg_command(client, chat_id, ffmpeg_command, "Adding HardSub...")
    return output_path

def add_cover_as_first_frame(video_path, cover_image_path, output_path, cover_duration=0.01):
    # Get video frame rate
    probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                            'stream=r_frame_rate', '-of', 'default=noprint_wrappers=1:nokey=1', video_path],
                           stdout=subprocess.PIPE, text=True)
    frame_rate = probe.stdout.strip()
    if '/' in frame_rate:
        numerator, denominator = map(int, frame_rate.split('/'))
        frame_rate = numerator / denominator
    else:
        frame_rate = float(frame_rate)

    ffmpeg_cmd = [
        'ffmpeg',
        '-loop', '1',
        '-i', cover_image_path,
        '-c:v', 'libx264',
        '-t', str(cover_duration),
        '-pix_fmt', 'yuv420p',
        '-vf', f'fps={frame_rate}',
        '-an',
        '-y',
        'cover_temp.mp4'
    ]
    subprocess.run(ffmpeg_cmd, check=True)

    concat_file_path = 'concat_list.txt'
    with open(concat_file_path, 'w') as f:
        f.write(f"file 'cover_temp.mp4'\n")
        f.write(f"file '{video_path}'\n")

    concat_cmd = [
        'ffmpeg',
        '-f', 'concat',
        '-safe', '0',
        '-i', concat_file_path,
        '-c:v', 'libx264',
        '-c:a', 'copy',
        '-y',
        output_path
    ]
    subprocess.run(concat_cmd, check=True)

    os.remove('cover_temp.mp4')
    os.remove(concat_file_path)

async def upload_video_with_progress(client, chat_id, video_path, uploading_text):
    start_time = time.time()
    total_size = os.path.getsize(video_path)

    async def read_in_chunks(file, chunk_size=8192):
        while True:
            data = file.read(chunk_size)
            if not data:
                break
            yield data

    with open(video_path, 'rb') as video_file, tqdm.tqdm(
        desc="Uploading",
        total=total_size,
        unit='B',
        unit_scale=True,
        unit_divisor=1024
    ) as progress_bar:
        try:
            # Pyrogram doesn't support chunked uploads directly, so this part is simulated
            await client.send_video(chat_id, video_path, thumb="cover.jpg")
            for chunk in read_in_chunks(video_file):
                progress_bar.update(len(chunk))
            elapsed_time = time.time() - start_time
            status_message = f"Uploading video completed in {elapsed_time:.2f} seconds."
            await client.edit_message_text(chat_id, uploading_text.id, status_message)
        except Exception as e:
            await client.send_message(chat_id, f"Failed to upload video: {str(e)}")

@app.on_message(filters.command("start"))
async def start(client: Client, message: Message):
    await message.reply("Welcome! Send me a video and I'll process it for you.")

@app.on_message(filters.video)
async def handle_video(client: Client, message: Message):
    user_id = message.from_user.id
    user_video_paths[user_id] = message.video.file_id

    # Requesting download of the video
    download_message = await message.reply("Downloading your video...")
    video_file = await client.download_media(message.video.file_id)
    await download_message.edit("Video downloaded!")

    # Ask for subtitle and cover
    await message.reply("Please send me the subtitle file next.")
    user_states[user_id] = 'waiting_for_subtitle'

@app.on_message(filters.document)
async def handle_document(client: Client, message: Message):
    user_id = message.from_user.id

    if user_id in user_states and user_states[user_id] == 'waiting_for_subtitle':
        user_subtitle_paths[user_id] = message.document.file_id
        subtitle_message = await message.reply("Subtitle received. Please send me the cover image next.")
        user_states[user_id] = 'waiting_for_cover'
    elif user_id in user_states and user_states[user_id] == 'waiting_for_cover':
        user_cover_paths[user_id] = message.document.file_id
        cover_message = await message.reply("Cover image received. Processing video...")
        video_file_path = await client.download_media(user_video_paths[user_id])
        subtitle_file_path = await client.download_media(user_subtitle_paths[user_id])
        cover_file_path = await client.download_media(user_cover_paths[user_id])
        
        # Process video
        final_video_path = f"final_video_{user_id}.mp4"
        watermarked_video_path = f"watermarked_{user_id}.mp4"
        subtitled_video_path = f"subtitled_{user_id}.mp4"
        final_output_path = f"output_{user_id}.mp4"
        
        await add_watermark(client, message.chat.id, video_file_path, watermarked_video_path)
        await add_subtitles(client, message.chat.id, watermarked_video_path, subtitle_file_path, subtitled_video_path)
        add_cover_as_first_frame(subtitled_video_path, cover_file_path, final_output_path)
        
        await upload_video_with_progress(client, message.chat.id, final_output_path, cover_message)
        await message.reply("Your video is ready and uploaded!")
    else:
        await message.reply("Please send the video first.")

app.run()
