import asyncio
import uvloop
from pyrogram import Client
import json
import os
from tqdm import tqdm

# Install uvloop before creating the Client instance
uvloop.install()

# Load the config file
with open('config.json') as config_file:
    config = json.load(config_file)

# Replace with your own API_ID, API_HASH, and BOT_TOKEN
api_id = int(config['api_id'])
api_hash = config['api_hash']
bot_token = config['bot_token']

app = Client("my_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

@app.on_message()
async def handle_message(client, message):
    if message.document:
        # Download the file
        await download_file(message)

        # Upload the file
        await upload_file(message.document.file_name)

async def download_file(message):
    file_size = message.document.file_size
    file_name = message.document.file_name
    dest_path = os.path.join("./downloads", file_name)

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    
    # Create a progress bar with tqdm
    with tqdm(total=file_size, unit='B', unit_scale=True, desc=f"Downloading {file_name}") as pbar:
        async def progress(current, total):
            pbar.update(current - pbar.n)
        
        # Start downloading with the progress callback
        await message.download(file_name=dest_path, progress=progress)
        print(f"Downloaded to {dest_path}")

        
async def upload_file(file_name):
    file_path = os.path.join("./downloads", file_name)
    
    # Check if the file exists before attempting to upload
    if not os.path.isfile(file_path):
        print(f"File {file_path} does not exist.")
        return

    file_size = os.path.getsize(file_path)
    
    # Create a progress bar with tqdm
    with tqdm(total=file_size, unit='B', unit_scale=True, desc=f"Uploading {file_name}") as pbar:
        async def progress(current, total):
            pbar.update(current - pbar.n)
        
        # Upload the file (for example, to a specific chat or user)
        # Replace 'YOUR_CHAT_ID' with the appropriate chat ID
        chat_id = 6459990242
        await app.send_document(
            chat_id,
            file_path,
            progress=progress
        )
        print(f"Uploaded to chat {chat_id}")

if __name__ == "__main__":
    app.run()
