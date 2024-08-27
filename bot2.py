import asyncio
from pyrogram import Client
import json
import os
from tqdm import tqdm

# Load the config file
with open('config.json') as config_file:
    config = json.load(config_file)

# Replace with your own API_ID, API_HASH, and BOT_TOKEN
api_id = int(config['api_id'])
api_hash = config['api_hash']
bot_token = config['bot_token']

app = Client("my_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

@app.on_message()
async def download(client, message):
    if message.document:
        file_size = message.document.file_size
        file_name = message.document.file_name

        # Destination path
        dest_path = os.path.join("./downloads", file_name)
        
        # Create a progress bar with tqdm
        with tqdm(total=file_size, unit='B', unit_scale=True, desc=file_name) as pbar:
            
            # Define a custom progress callback function
            async def progress(current, total):
                pbar.update(current - pbar.n)
            
            # Start downloading with the progress callback
            file_path = await message.download(file_name=dest_path, progress=progress)
            print(f"Downloaded to {file_path}")

if __name__ == "__main__":
    app.run()
