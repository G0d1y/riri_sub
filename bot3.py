import time
from moviepy.editor import VideoFileClip
from PIL import Image
# Start the timer
start_time = time.time()

# Load the original video
input_file = "input.mkv"
output_file = "output_video_720p.mp4"

# Load the video file
video = VideoFileClip(input_file)

# Resize the video to 720p
video_resized = video.resize(height=720)

# Write the result to a new file
video_resized.write_videofile(output_file, codec="libx264", preset="ultrafast", bitrate="500k")

# End the timer
end_time = time.time()

# Print the time taken
print(f"Time taken: {end_time - start_time} seconds")