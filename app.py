from flask import Flask, render_template, request, send_file
from diffusers import StableDiffusionPipeline
import torch
from moviepy.editor import ImageSequenceClip
import io, os
from datetime import datetime

app = Flask(__name__)

# Load Stable Diffusion once
pipe = StableDiffusionPipeline.from_pretrained(
    "runwayml/stable-diffusion-v1-5", torch_dtype=torch.float16
).to("cuda")

def generate_images(prompt, num_frames=5):
    images = []
    for i in range(num_frames):
        image = pipe(prompt).images[0]
        filename = f"frame_{i}.png"
        image.save(filename)
        images.append(filename)
    return images

def images_to_video(image_files, output_file="output.mp4", fps=2):
    clip = ImageSequenceClip(image_files, fps=fps)
    clip.write_videofile(output_file, codec="libx264")
    return output_file

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        prompt = request.form.get("prompt")
        num_frames = int(request.form.get("frames", 6))
        fps = int(request.form.get("fps", 2))

        # Generate video
        frames = generate_images(prompt, num_frames=num_frames)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_path = f"static/videos/story_{timestamp}.mp4"
        os.makedirs("static/videos", exist_ok=True)
        images_to_video(frames, output_file=video_path, fps=fps)

        return render_template("index.html", video_path=video_path)

    return render_template("index.html", video_path=None)

@app.route("/download/<path:filename>")
def download(filename):
    return send_file(filename, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
