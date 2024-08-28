import os
import requests
import json
from urllib.parse import urlparse, parse_qs, unquote
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton , ReplyKeyboardMarkup
from moviepy.config import change_settings
import subprocess
import time
import asyncio
from pyrogram.errors import FloodWait
import sys
import ffmpeg
import re
change_settings({"IMAGEMAGICK_BINARY": r"/ImageMagick-7.1.1-Q16-HDRI/magick.exe"})

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
    print("test")
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

async def download_video(client, url, file_name, chat_id , downloading_text):
    file_extension = get_file_extension(url)
    video_path = f"downloaded_{file_name}{file_extension}"
    start_time = time.time()  
    last_update_time = start_time
    update_interval = 1  
    try:
        response = requests.get(url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        
        downloaded_size = 0
        with open(video_path, 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
                downloaded_size += len(chunk)
                
                current_time = time.time()
                if current_time - last_update_time >= update_interval:
                    elapsed_time = current_time - start_time
                    percentage = (downloaded_size / total_size) * 100
                    speed = downloaded_size / elapsed_time
                    speed_kb_s = speed / 1024
                    speed_mb_s = speed / (1024 * 1024)
                    status_message = f"Downloading {downloaded_size / 1024 / 1024:.2f}MB ({percentage:.1f}%) of {total_size / 1024 / 1024:.2f}MB\n"

                    try:
                        await client.edit_message_text(chat_id, downloading_text.id , status_message)
                    except FloodWait as e:
                        await asyncio.sleep(e.x) 
                    
                    last_update_time = current_time

        return video_path
    except Exception as e:
        await client.send_message(chat_id, f"Failed to download video: {str(e)}")
        return None

async def run_ffmpeg_command(client, chat_id, command, status_message):
    try:
        # Send initial status message
        text = await client.send_message(chat_id, status_message)
        print("Running command:", " ".join(command))

        # Run FFmpeg command and stream the output
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

def get_video_properties(video_path):
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,r_frame_rate',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_path
    ]
    output = subprocess.check_output(cmd, text=True).splitlines()
    width, height = output[0], output[1]
    frame_rate = eval(output[2])  # Converts frame rate from a string like "30000/1001" to a float
    return width, height, frame_rate
     
async def add_watermark(client, chat_id, video_path, output_path, watermark_duration=20, audio_delay_correction=0.0):
    watermark_text = "بزرگترین کانال دانلود سریال کره ای\n@RiRiKdrama |  ریری کیدراما"
    font_path = 'Sahel-Bold.ttf'
    watermarked_segment_path = 'watermarked_segment.mkv'
    remaining_part_path = 'remaining_part.mkv'
    reencoded_watermarked_path = 'watermarked_segment_reencoded.mkv'
    concat_file_path = 'concat_list.txt'

    # Get video properties
    width, height, frame_rate = get_video_properties(video_path)

    # Step 1: Add Watermark
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
        '-copyts', '-start_at_zero',
        '-c:v', 'libx264',
        '-crf', '18',
        '-preset', 'ultrafast',
        '-c:a', 'copy',
        '-vsync', '0',
        '-y',
        watermarked_segment_path
    ]
    await run_ffmpeg_command(client, chat_id, watermark_cmd, "Adding watermark...")

    # Step 2: Re-encode Watermarked Segment to Match the Main Video
    reencode_cmd = [
        'ffmpeg',
        '-i', watermarked_segment_path,
        '-filter_complex', (
            f"pad={width}:{height}:-1:-1,fps={frame_rate}[v];"
            f"aresample=async=1:min_hard_comp=0.1:first_pts=0[a]"
        ),
        '-map', '[v]', '-map', '[a]',
        '-c:v', 'libx264',
        '-c:a', 'aac',
        '-copyts', '-start_at_zero',
        '-y',
        reencoded_watermarked_path
    ]
    await run_ffmpeg_command(client, chat_id, reencode_cmd, "Re-encoding watermarked segment...")

    # Step 3: Extract the Remaining Part of the Video
    extract_cmd = [
        'ffmpeg',
        '-i', video_path,
        '-ss', str(watermark_duration),
        '-c:v', 'copy',
        '-c:a', 'copy',
        '-copyts', '-start_at_zero',
        '-vsync', '0',
        '-y',
        remaining_part_path
    ]
    await run_ffmpeg_command(client, chat_id, extract_cmd, "Extracting remaining part...")

    # Step 4: Concatenate the Segments Using concat Demuxer
    with open(concat_file_path, 'w') as f:
        f.write(f"file '{reencoded_watermarked_path}'\n")
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

    # Step 5: Clean Up Temporary Files
    for file_path in [watermarked_segment_path, remaining_part_path, reencoded_watermarked_path, concat_file_path]:
        if os.path.exists(file_path):
            os.remove(file_path)

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
    
    # Start FFmpeg command with progress updates
    await run_ffmpeg_command(client, chat_id, ffmpeg_command, "Adding HardSub...")

    return output_path

def add_cover_as_first_frame(video_path, cover_image_path, output_path, cover_duration=0.01):
    # Get video frame rate
    probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                            'stream=r_frame_rate', '-of', 'default=noprint_wrappers=1', video_path],
                            stdout=subprocess.PIPE, text=True).stdout
    frame_rate_str = probe.split('r_frame_rate=')[1].strip()
    num, denom = map(int, frame_rate_str.split('/'))
    frame_rate = num / denom

    # Create cover video
    cover_video_path = 'cover_video.mp4'
    cover_cmd = [
        'ffmpeg',
        '-loop', '1',
        '-i', cover_image_path,
        '-t', str(cover_duration),
        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p',
        '-r', str(frame_rate),
        '-y', cover_video_path,
        '-f', 'lavfi',
        '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
        '-shortest'
    ]

    try:
        subprocess.run(cover_cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error creating cover video: {str(e)}")
        return None

    # Concatenate cover video and main video
    concat_file_path = 'concat_list.txt'
    with open(concat_file_path, 'w') as f:
        f.write(f"file '{cover_video_path}'\n")
        f.write(f"file '{video_path}'\n")

    concat_cmd = [
        'ffmpeg',
        '-f', 'concat',
        '-safe', '0',
        '-i', concat_file_path,
        '-c:v', 'copy',
        '-c:a', 'copy',
        '-y', output_path
    ]

    try:
        subprocess.run(concat_cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error concatenating cover video and main video: {str(e)}")
        return None

    # Clean up temporary files
    if os.path.exists(cover_video_path):
        os.remove(cover_video_path)
    if os.path.exists(concat_file_path):
        os.remove(concat_file_path)

    return output_path

async def process_video(client, chat_id, video_path, subtitles_path, cover_image_path, user_name):
    if not os.path.exists(video_path) or not os.path.exists(subtitles_path):
        print("Video or subtitles file does not exist.")
        return None

    watermarked_video_path = f"watermarked_{user_name}.mkv"
    video_with_subtitles_path = f"with_subtitles_{user_name}.mkv"
    video_with_cover_as_frame_path = f"cover_as_frame_{user_name}.mkv"
    final_output_path = f"{user_name}.mp4"

    watermarked_video_path = await add_watermark(client, chat_id, video_path, watermarked_video_path, watermark_duration=20)
    if not watermarked_video_path:
        print("Failed to add watermark.")
        return None

    final_output_path = await add_subtitles(client, chat_id,watermarked_video_path, subtitles_path, video_with_subtitles_path)
    if not video_with_subtitles_path:
        print("Failed to add subtitles.")
        return None

    print(f"Processing complete. Final output file: {final_output_path}")
    return final_output_path

async def add_soft_subtitles(client, chat_id, video_path, subtitle_path, cover_image_path, user_name):
    if not os.path.exists(video_path) or not os.path.exists(subtitle_path):
        print("Video or subtitles file does not exist.")
        return None

    # Paths for intermediate and final files
    watermarked_video_path = f"watermarked_{user_name}.mp4"
    subtitle_movtext_path = f"{user_name}_subtitles.mp4"
    output_path_manually = f"Subbed_{user_name}.mp4"
    final_output_path = f"{user_name}.mp4"

    # Add watermark to the video
    watermarked_video_path = await add_watermark(client, chat_id, video_path, watermarked_video_path)
    if not watermarked_video_path:
        print("Failed to add watermark.")
        return None

    # Convert subtitles to MOV_TEXT format
    ffmpeg_convert_subtitles_command = [
        'ffmpeg',
        '-i', subtitle_path,
        '-c:s', 'mov_text',
        subtitle_movtext_path
    ]
    try:
        subprocess.run(ffmpeg_convert_subtitles_command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error during subtitle conversion: {str(e)}")
        return None

    # Embed the converted subtitles into the watermarked video
    ffmpeg_command = [
        'ffmpeg',
        '-i', watermarked_video_path,
        '-i', subtitle_movtext_path,
        '-map', '0:v',
        '-map', '0:a',
        '-map', '1:s',
        '-c:v', 'copy',
        '-c:a', 'copy',
        '-c:s', 'mov_text',
        '-metadata:s:s:0', 'title=@RiRiMovies',
        final_output_path
    ]
    await run_ffmpeg_command(client, chat_id, ffmpeg_command, "Adding SoftSub...")

    return final_output_path

@app.on_message(filters.command("start"))
async def send_welcome(client, message: Message):
    keyboard = ReplyKeyboardMarkup([
        ["restart_robot"]
    ] , resize_keyboard=True)
    await message.reply("Send me a link to a video", reply_markup=keyboard)
    user_states[message.chat.id] = 'awaiting_video_link'

@app.on_message(filters.regex("fh"))
async def handle_hard_sub(client, message: Message):
    chat_id = message.from_user.id
    if chat_id not in user_video_paths:
        await message.reply("Please send a video link first.")
        return

    try:
        video_path = user_video_paths[chat_id].get('path')
        subtitle_path = user_subtitle_paths.get(chat_id)
        cover_image_path = 'cover.jpg'
        video_name = user_video_paths[chat_id].get('name')

        if not video_path or not subtitle_path or not video_name:
            await message.reply("Video, subtitle file, or video name not found.")
            return

        await message.reply("Adding hard subtitles, watermark, and cover image to the video...")
        output_video_path = await process_video(client, chat_id, video_path, subtitle_path, cover_image_path, video_name)

        if output_video_path:
            uploading_text = await message.reply("Uploading video with hard subtitles, watermark, and cover image...")
            try:
                await upload_video_with_progress(client , chat_id, output_video_path, uploading_text)
                user_states[chat_id] = 'awaiting_video_link'
            except Exception as e:
                await message.reply(f"Error uploading video: {str(e)}")
        else:
            await message.reply("Failed to create video with hard subtitles, watermark, and cover image.")
    except Exception as e:
        await message.reply(f"Error handling subtitle: {str(e)}")

@app.on_message(filters.regex("fs"))
async def handle_soft_subtitles(client: Client,  message: Message):
    chat_id = message.from_user.id
    if chat_id not in user_video_paths:
        await message.reply("Please send a video link first.")
        return

    try:
        video_path = user_video_paths[chat_id].get('path')
        subtitle_path = user_subtitle_paths.get(chat_id)
        cover_image_path = 'cover.jpg'
        user_name = user_video_paths[chat_id].get('name')

        if not video_path or not subtitle_path or not user_name:
            await message.reply("Video, subtitle file, or user name not found.")
            return

        await message.reply("Adding soft subtitles, watermark, and cover image to the video...")
        output_video_path = await add_soft_subtitles(client, chat_id, video_path, subtitle_path, cover_image_path, user_name)

        if output_video_path:
            uploading_text = await message.reply("Uploading video with soft subtitles, watermark, and cover image...")
            try:
                await upload_document_with_progress(client, chat_id, output_video_path, uploading_text)
                user_states[chat_id] = 'awaiting_video_link'
            except Exception as e:
                await message.reply(f"Error uploading video: {str(e)}")
        else:
            await message.reply("Failed to create video with soft subtitles, watermark, and cover image.")
    except Exception as e:
        await message.reply(f"Error handling subtitles: {str(e)}")

@app.on_message(filters.text & filters.private)
async def handle_text_message(client, message: Message):
    chat_id = message.chat.id
    state = user_states.get(chat_id, 'awaiting_video_link')

    if state == 'awaiting_video_link':
        directory = './downloads'
        directory2 = './'
        extensions_to_delete = ['.srt', '.mkv', '.mp4']
        for filename in os.listdir(directory):
            if any(filename.endswith(ext) for ext in extensions_to_delete):
                file_path = os.path.join(directory, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)

        for filename in os.listdir(directory2):
            if any(filename.endswith(ext) for ext in extensions_to_delete):
                file_path = os.path.join(directory2, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                
        video_url = message.text
        if video_url.startswith('http'):  # Assuming URL starts with 'http'
            # Handle URL case
            user_video_paths[chat_id] = {'url': video_url}
            await message.reply("لطفا نام مورد نظر را بفرستید.")
            user_states[chat_id] = 'awaiting_video_name'
        else:
            await message.reply("Please send a valid URL.")

    elif state == 'awaiting_video_name':
        video_name = message.text
        user_video_paths[chat_id]['name'] = video_name
        video_url = user_video_paths[chat_id]['url']

        downloading_text = await message.reply("Downloading video...")
        try:
            video_path = await download_video(client, video_url, video_name, chat_id, downloading_text)
            if video_path:
                user_video_paths[chat_id]['path'] = video_path
                await message.reply("فایل زیرنویس رو بفرست")
                user_states[chat_id] = 'awaiting_subtitle_file'
            else:
                await message.reply("Failed to download video.")
        except Exception as e:
            await message.reply(f"Error downloading video: {str(e)}")
    elif state == 'awaiting_video_name_file':
        video_name = message.text
        user_video_paths[chat_id]['name'] = video_name
        video_path = user_video_paths[chat_id]['path']

        await message.reply("فایل زیرنویس رو بفرست")
        user_states[chat_id] = 'awaiting_subtitle_file'

def sanitize_filename(filename):
    # Replace any invalid characters with an underscore
    return re.sub(r'[<>:"/\\|?*\x00-\x1F]', '_', filename)

@app.on_message(filters.document & filters.private)
async def handle_video_file(client, message: Message):
    chat_id = message.chat.id
    state = user_states.get(chat_id, 'awaiting_video_link')

    if state == 'awaiting_video_link':
        directory = './downloads'
        directory2 = './'
        extensions_to_delete = ['.srt', '.mkv', '.mp4']
        for filename in os.listdir(directory):
            if any(filename.endswith(ext) for ext in extensions_to_delete):
                file_path = os.path.join(directory, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)

        for filename in os.listdir(directory2):
            if any(filename.endswith(ext) for ext in extensions_to_delete):
                file_path = os.path.join(directory2, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)

        # Save the video file
        file_id = message.document.file_id
        file_name = message.document.file_name
        sanitized_file_name = sanitize_filename(file_name)

        await message.reply("Downloading video...")
        file_path = await message.download(file_name=sanitized_file_name)
        user_video_paths[chat_id] = {'path': file_path, 'name': sanitized_file_name}
        await message.reply("Please send the name you want for the video file.")
        user_states[chat_id] = 'awaiting_video_name_file'

    elif state != "awaiting_video_link":
        try:
            subtitle_file_path = 'subtitle.srt'

            if os.path.exists(subtitle_file_path):
                os.remove(subtitle_file_path)

            downloaded_file_path = await message.download()
            os.rename(downloaded_file_path, subtitle_file_path)

            user_subtitle_paths[chat_id] = subtitle_file_path
            video_path = user_video_paths.get(chat_id).get('path')

            if not video_path:
                await message.reply("Video path not found.")
                return

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Done", callback_data="done")]
            ])
            await message.reply("Choose subtitle mode or press Done to start over:", reply_markup=keyboard)
        except Exception as e:
            await message.reply(f"Error handling subtitle: {str(e)}")

@app.on_message(filters.photo & filters.private)
async def handle_cover(client, message: Message):
    chat_id = message.chat.id
    try:
        cover_image_path = 'cover.jpg'
        
        if os.path.exists(cover_image_path):
            os.remove(cover_image_path)
        
        downloaded_file_path = await message.download()
        os.rename(downloaded_file_path, cover_image_path)
        
        await message.reply("Cover image received")
    except Exception as e:
        await message.reply(f"Error handling cover image: {str(e)}")

@app.on_callback_query(filters.regex("done"))
async def handle_done(client, callback_query: CallbackQuery):
    await callback_query.message.reply("Reset")
    user_states[callback_query.message.chat.id] = 'awaiting_video_link'

@app.on_callback_query(filters.regex("watermark"))
async def handle_watermark(client: Client, callback_query: CallbackQuery):
    chat_id = callback_query.from_user.id
    if chat_id not in user_video_paths:
        await callback_query.message.reply("Please send a video link first.")
        return

    try:
        video_path = user_video_paths[chat_id].get('path')
        cover_image_path = 'cover.jpg'
        video_name = user_video_paths[chat_id].get('name')

        if not video_path or not video_name:
            await callback_query.message.reply("Video path or video name not found.")
            return

        await callback_query.message.reply("Adding watermark to the video...")
        output_video_path = add_watermark(client, chat_id, video_path, f"{video_name} Kidramir.mp4", watermark_duration=20)

        if output_video_path:
            uploading_text = await callback_query.message.reply("Uploading video with watermark...")
            try:
                await upload_document_with_progress(client, chat_id, output_video_path, uploading_text)
                user_states[chat_id] = 'awaiting_video_link'
            except Exception as e:
                await callback_query.message.reply(f"Error uploading video: {str(e)}")
        else:
            await callback_query.message.reply("Failed to create video with watermark.")
    except Exception as e:
        await callback_query.message.reply(f"Error handling watermark: {str(e)}")

async def upload_video_with_progress(client, chat_id, video_path, uploading_text):
    start_time = time.time()
    total_size = os.path.getsize(video_path)
    last_update_time = start_time

    try:
        with open(video_path, 'rb') as video_file:
            response = await client.send_video(
                chat_id=chat_id,
                video=video_file,
                thumb="cover.jpg"
            )

        elapsed_time = time.time() - start_time
        status_message = f"Uploading video completed in {elapsed_time:.2f} seconds."

        await client.edit_message_text(chat_id, uploading_text.id, status_message)

    except Exception as e:
        await client.send_message(chat_id, f"Failed to upload video: {str(e)}")

async def upload_document_with_progress(client, chat_id, document_path, uploading_text):
    start_time = time.time()
    total_size = os.path.getsize(document_path)
    try:
        with open(document_path, 'rb') as doc_file:
            response = await client.send_document(
                chat_id=chat_id,
                document=doc_file,
                thumb="cover.jpg"
            )
        
        elapsed_time = time.time() - start_time
        status_message = f"Uploading document completed in {elapsed_time:.2f} seconds."

        await client.edit_message_text(chat_id, uploading_text.id, status_message)

    except Exception as e:
        await client.send_message(chat_id, f"Failed to upload document: {str(e)}")

app.run()