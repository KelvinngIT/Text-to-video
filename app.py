import os
from diffusers import StableDiffusionPipeline
import torch
from moviepy.editor import ImageSequenceClip

# ======================
# Text-to-Image Function
# ======================
def generate_images(prompt, num_frames=5):
    model_id = "runwayml/stable-diffusion-v1-5"
    pipe = StableDiffusionPipeline.from_pretrained(model_id, torch_dtype=torch.float16)
    pipe = pipe.to("cuda")

    images = []
    for i in range(num_frames):
        image = pipe(prompt).images[0]
        filename = f"frame_{i}.png"
        image.save(filename)
        images.append(filename)
    return images

# ======================
# Images to Video
# ======================
def images_to_video(image_files, output_file="output.mp4", fps=2):
    clip = ImageSequenceClip(image_files, fps=fps)
    clip.write_videofile(output_file, codec="libx264")
    print(f"Video saved as {output_file}")

# ======================
# Main
# ======================
if __name__ == "__main__":
    text_prompt = "A father telling his son about life struggles in a warm living room"
    frames = generate_images(text_prompt, num_frames=8)
    images_to_video(frames, output_file="story_video.mp4", fps=2)
