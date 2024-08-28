import json
import os
import time
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

# Load configuration
with open('config.json') as config_file:
    config = json.load(config_file)

api_id = int(config['api_id'])
api_hash = config['api_hash']
bot_token = config['bot_token']

app = Client("bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

# Directory to save downloaded files
DOWNLOAD_PATH = "downloads"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

def sanitize_filename(filename: str) -> str:
    import re
    return re.sub(r'[<>:"/\\|?*\x00-\x1F]', '_', filename)

async def download_file(message: Message):
    file_id = message.document.file_id if message.document else None
    file_name = message.document.file_name if message.document else f"{message.message_id}.jpg"
    file_name = sanitize_filename(file_name)  # Sanitize the file name
    
    if file_id:
        file_path = os.path.join(DOWNLOAD_PATH, file_name)
        
        # Measure download start time
        start_time = time.time()
        
        # Download the entire file
        await app.download_media(message, file_path, progress=download_progress)
        
        # Measure download end time
        end_time = time.time()
        
        # Print time taken
        print(f"File downloaded in {end_time - start_time:.2f} seconds.")
        
        # Process file in chunks
        await process_file_in_chunks(file_path, chunk_size=25 * 1024 * 1024)  # Increase chunk size
        print(f"File processed in chunks: {file_name}")
    else:
        print("No document found in the message")

async def download_progress(current, total):
    print(f"Download Progress: {current}/{total}")

async def process_file_in_chunks(file_path: str, chunk_size: int = 1 * 1024 * 1024):
    """
    Process a file in chunks concurrently.
    :param file_path: Path to the file to process.
    :param chunk_size: Size of each chunk in bytes (default is 25MB).
    """
    async def write_chunk(start_byte, end_byte, chunk_index):
        with open(file_path, 'rb') as file:
            file.seek(start_byte)
            chunk = file.read(chunk_size)
            chunk_file_path = f"{file_path}.part{chunk_index}"
            with open(chunk_file_path, 'wb') as chunk_file:
                chunk_file.write(chunk)
            print(f"Processed chunk {chunk_index + 1}")
    
    file_size = os.path.getsize(file_path)
    chunk_tasks = []
    chunk_index = 0
    
    for start in range(0, file_size, chunk_size):
        end = min(start + chunk_size, file_size)
        chunk_tasks.append(asyncio.create_task(write_chunk(start, end, chunk_index)))
        chunk_index += 1
    
    await asyncio.gather(*chunk_tasks)

@app.on_message(filters.media)
async def handle_media(client: Client, message: Message):
    await download_file(message)

if __name__ == "__main__":
    app.run()
