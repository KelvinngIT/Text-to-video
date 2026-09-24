import streamlit as st
import tempfile
import os
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw, ImageFont
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, TextClip
from moviepy.video.fx.all import resize
from gtts import gTTS
import easyocr
import requests
from io import BytesIO
import json
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

# ===== FIX for Pillow 10+ =====
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

# ====================== PAGE CONFIG ======================
st.set_page_config(
    page_title="Image → Video Generator Pro",
    page_icon="🎬",
    layout="centered",
    initial_sidebar_state="expanded"
)

# ====================== HELPER FUNCTIONS ======================
def enhance_image(image: Image.Image, sharpness=1.5, contrast=1.2, brightness=1.1, color=1.1) -> Image.Image:
    img = image.convert("RGB")
    img = ImageEnhance.Sharpness(img).enhance(sharpness)
    img = ImageEnhance.Contrast(img).enhance(contrast)
    img = ImageEnhance.Brightness(img).enhance(brightness)
    img = ImageEnhance.Color(img).enhance(color)
    img = img.filter(ImageFilter.MedianFilter(size=3))
    return img

def add_watermark(image: Image.Image, watermark_img=None, text=None, 
                  position="bottom-right", opacity=0.4, scale=0.2) -> Image.Image:
    base = image.convert("RGBA")
    width, height = base.size
    watermark = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(watermark)
    
    if watermark_img:
        wm = watermark_img.convert("RGBA")
        wm_width = int(width * scale)
        wm_height = int(wm_width * wm.size[1] / wm.size[0])
        wm = wm.resize((wm_width, wm_height), Image.Resampling.LANCZOS)
        alpha = wm.split()[3]
        alpha = ImageEnhance.Brightness(alpha).enhance(opacity)
        wm.putalpha(alpha)
        positions = {
            "top-left": (20, 20),
            "top-right": (width - wm_width - 20, 20),
            "bottom-left": (20, height - wm_height - 20),
            "center": ((width - wm_width)//2, (height - wm_height)//2),
            "bottom-right": (width - wm_width - 20, height - wm_height - 20)
        }
        pos = positions.get(position, positions["bottom-right"])
        watermark.paste(wm, pos, wm)
    elif text:
        try:
            font = ImageFont.truetype("arial.ttf", size=int(height * 0.05))
        except:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        positions = {
            "top-left": (20, 20),
            "top-right": (width - text_width - 20, 20),
            "bottom-left": (20, height - text_height - 20),
            "center": ((width - text_width)//2, (height - text_height)//2),
            "bottom-right": (width - text_width - 20, height - text_height - 20)
        }
        pos = positions.get(position, positions["bottom-right"])
        draw.text(pos, text, font=font, fill=(255, 255, 255, int(255 * opacity)))
    
    result = Image.alpha_composite(base, watermark)
    return result.convert("RGB")

def text_to_audio(text: str, lang: str = "en", slow: bool = False) -> str:
    tts = gTTS(text=text, lang=lang, slow=slow)
    fd, path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    tts.save(path)
    return path

@st.cache_resource
def load_ocr_reader():
    return easyocr.Reader(['en', 'id'], gpu=False)

def extract_text_from_image(image: Image.Image) -> str:
    reader = load_ocr_reader()
    img_array = np.array(image)
    results = reader.readtext(img_array)
    text = "\n".join([item[1] for item in results])
    return text.strip()

def text_to_image(prompt: str, width: int = 768, height: int = 768) -> Image.Image:
    prompt_encoded = requests.utils.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width={width}&height={height}&nologo=true"
    response = requests.get(url, timeout=90)
    response.raise_for_status()
    img = Image.open(BytesIO(response.content)).convert("RGB")
    return img

def create_video_from_image(
    image: Image.Image,
    duration: float = 6.0,
    zoom_factor: float = 1.35,
    fps: int = 24,
    pan_x: float = 0.3,
    pan_y: float = 0.2,
    zoom_in: bool = True,
    title: str = None,
    title_position: str = "top",
    audio_path: str = None
) -> str:
    img_array = np.array(image.convert("RGB"))
    clip = ImageClip(img_array).set_duration(duration)
    w, h = clip.size

    def make_frame(t):
        progress = min(t / duration, 1.0)
        if zoom_in:
            current_zoom = 1.0 + (zoom_factor - 1.0) * progress
        else:
            current_zoom = zoom_factor - (zoom_factor - 1.0) * progress
        new_w = int(w * current_zoom)
        new_h = int(h * current_zoom)
        x_offset = int((new_w - w) * (0.5 + pan_x * 0.5) * progress)
        y_offset = int((new_h - h) * (0.5 + pan_y * 0.5) * progress)
        x_offset = max(0, min(x_offset, new_w - w))
        y_offset = max(0, min(y_offset, new_h - h))
        resized = resize(clip, newsize=(new_w, new_h))
        frame = resized.get_frame(t)
        return frame[y_offset:y_offset + h, x_offset:x_offset + w]

    animated = clip.fl(lambda gf, t: make_frame(t))

    if title and title.strip():
        try:
            txt_clip = TextClip(
                title,
                fontsize=int(h * 0.07),
                color="white",
                font="Arial-Bold",
                stroke_color="black",
                stroke_width=2
            ).set_duration(duration)
            if title_position == "top":
                txt_clip = txt_clip.set_position(("center", 40))
            elif title_position == "center":
                txt_clip = txt_clip.set_position("center")
            else:
                txt_clip = txt_clip.set_position(("center", h - 100))
            animated = CompositeVideoClip([animated, txt_clip])
        except Exception as e:
            st.warning(f"Could not add title: {e}")

    if audio_path and os.path.exists(audio_path):
        try:
            audio = AudioFileClip(audio_path)
            if audio.duration < duration:
                audio = audio.fx(lambda c: c.loop(duration=duration))
            else:
                audio = audio.subclip(0, duration)
            audio = audio.volumex(0.7)
            animated = animated.set_audio(audio)
        except Exception as e:
            st.warning(f"Could not add audio: {e}")

    fd, output_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    animated.write_videofile(
        output_path,
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=2,
        logger=None
    )
    return output_path

def get_users_past_year() -> int:
    """Tracks and returns the number of app visits in the past 365 days."""
    COUNTER_FILE = "user_visits.json"
    now = datetime.now()
    one_year_ago = now - timedelta(days=365)

    visits = []
    if os.path.exists(COUNTER_FILE):
        try:
            with open(COUNTER_FILE, "r") as f:
                visits = json.load(f)
        except Exception:
            visits = []

    visits = [v for v in visits if datetime.fromisoformat(v) > one_year_ago]

    if "counted_this_session" not in st.session_state:
        visits.append(now.isoformat())
        st.session_state.counted_this_session = True
        with open(COUNTER_FILE, "w") as f:
            json.dump(visits, f)

    return len(visits)

# ====================== NEW GRAPH FUNCTIONS ======================
def create_2d_graph(func_type="sine", x_range=(-10, 10), points=500):
    """
    Create a 2D matplotlib graph.
    func_type: "sine", "cosine", "quadratic", "exponential"
    """
    x = np.linspace(x_range[0], x_range[1], points)

    if func_type == "sine":
        y = np.sin(x)
        title = "2D Graph: y = sin(x)"
    elif func_type == "cosine":
        y = np.cos(x)
        title = "2D Graph: y = cos(x)"
    elif func_type == "quadratic":
        y = x**2
        title = "2D Graph: y = x²"
    elif func_type == "exponential":
        y = np.exp(x / 5)
        title = "2D Graph: y = e^(x/5)"
    else:
        y = np.sin(x)
        title = "2D Graph: y = sin(x)"

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(x, y, color="#1f77b4", linewidth=2.5)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel("X-axis")
    ax.set_ylabel("Y-axis")
    ax.grid(True, alpha=0.3)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.axvline(0, color="black", linewidth=0.8)
    fig.tight_layout()
    return fig

def create_3d_graph(func_type="surface", resolution=50):
    """
    Create a 3D matplotlib graph.
    func_type: "surface", "wave", "saddle", "ripple"
    """
    x = np.linspace(-5, 5, resolution)
    y = np.linspace(-5, 5, resolution)
    X, Y = np.meshgrid(x, y)

    if func_type == "surface":
        Z = np.sin(np.sqrt(X**2 + Y**2))
        title = "3D Graph: z = sin(√(x² + y²))"
    elif func_type == "wave":
        Z = np.sin(X) * np.cos(Y)
        title = "3D Graph: z = sin(x) · cos(y)"
    elif func_type == "saddle":
        Z = X**2 - Y**2
        title = "3D Graph: z = x² - y² (Saddle)"
    elif func_type == "ripple":
        Z = np.sin(X**2 + Y**2)
        title = "3D Graph: z = sin(x² + y²)"
    else:
        Z = np.sin(np.sqrt(X**2 + Y**2))
        title = "3D Graph: z = sin(√(x² + y²))"

    fig = plt.figure(figsize=(9, 7))
    ax = fig.add_subplot(111, projection="3d")
    surf = ax.plot_surface(X, Y, Z, cmap="viridis", edgecolor="none", alpha=0.9)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel("X-axis")
    ax.set_ylabel("Y-axis")
    ax.set_zlabel("Z-axis")
    fig.colorbar(surf, ax=ax, shrink=0.5, aspect=10)
    fig.tight_layout()
    return fig

# ====================== SESSION STATE ======================
if "video_path" not in st.session_state:
    st.session_state.video_path = None
if "processed_image" not in st.session_state:
    st.session_state.processed_image = None
if "tts_audio_path" not in st.session_state:
    st.session_state.tts_audio_path = None
if "extracted_text" not in st.session_state:
    st.session_state.extracted_text = ""

# ====================== UI ======================
st.title("🖼️ → 🎬 Image to Video Generator Pro")
st.markdown("**Enhance • Watermark • Text-to-Image • OCR • TTS • Cinematic Video • Graphs**")
st.markdown("---")

# ---------- USER COUNTER (Sidebar) ----------
with st.sidebar:
    st.markdown("### 📊 App Stats")
    user_count = get_users_past_year()
    st.metric("Users (Past Year)", user_count)
    st.caption("Counts unique sessions in the last 365 days")

# ---------- UPLOAD IMAGE ----------
uploaded_file = st.file_uploader("Upload an image", type=["jpg", "jpeg", "png", "webp"])
if uploaded_file:
    original_image = Image.open(uploaded_file).convert("RGB")
    st.image(original_image, caption="Original Image", use_container_width=True)
else:
    original_image = None

# ====================== TEXT TO IMAGE ======================
st.markdown("---")
st.subheader("🎨 Text to Image (AI Generate)")
prompt = st.text_area(
    "Describe the image you want to create",
    placeholder="A beautiful sunset over the ocean, cinematic lighting, highly detailed, 8k",
    height=100
)
col_a, col_b = st.columns(2)
with col_a:
    img_width = st.selectbox("Width", [512, 768, 1024], index=1)
with col_b:
    img_height = st.selectbox("Height", [512, 768, 1024], index=1)

if st.button("✨ Generate Image from Text", type="primary", use_container_width=True):
    if prompt.strip():
        with st.spinner("Generating image... (this may take 15-40 seconds)"):
            try:
                generated_img = text_to_image(prompt, width=img_width, height=img_height)
                st.session_state.processed_image = generated_img
                st.success("✅ Image generated successfully!")
                st.image(generated_img, caption="Generated Image", use_container_width=True)
            except Exception as e:
                st.error(f"Failed to generate image: {e}")
    else:
        st.warning("Please enter a description first.")

# ====================== IMAGE TOOLS ======================
if original_image or st.session_state.processed_image:
    st.markdown("---")
    st.subheader("🛠️ Image Tools")
    current_img = st.session_state.processed_image or original_image

    with st.expander("✨ Enhance Image Quality", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        with c1: sharpness = st.slider("Sharpness", 0.5, 3.0, 1.5, 0.1)
        with c2: contrast = st.slider("Contrast", 0.5, 2.0, 1.2, 0.1)
        with c3: brightness = st.slider("Brightness", 0.5, 2.0, 1.1, 0.1)
        with c4: color = st.slider("Color", 0.5, 2.0, 1.1, 0.1)
        if st.button("Apply Enhancement"):
            enhanced = enhance_image(current_img, sharpness, contrast, brightness, color)
            st.session_state.processed_image = enhanced
            st.success("Enhanced!")
            st.image(enhanced, use_container_width=True)

    with st.expander("💧 Add Watermark"):
        wm_type = st.radio("Type", ["Text", "Logo"], horizontal=True)
        position = st.selectbox("Position", ["bottom-right", "bottom-left", "top-right", "top-left", "center"])
        opacity = st.slider("Opacity", 0.1, 1.0, 0.45, 0.05)
        if wm_type == "Text":
            wm_text = st.text_input("Watermark Text", "© My Brand")
            if st.button("Add Text Watermark"):
                result = add_watermark(current_img, text=wm_text, position=position, opacity=opacity)
                st.session_state.processed_image = result
                st.image(result, use_container_width=True)
        else:
            wm_file = st.file_uploader("Upload Logo", type=["png", "jpg", "jpeg"], key="logo")
            scale = st.slider("Logo Size", 0.05, 0.35, 0.15)
            if wm_file and st.button("Add Logo Watermark"):
                wm_img = Image.open(wm_file)
                result = add_watermark(current_img, watermark_img=wm_img, position=position, opacity=opacity, scale=scale)
                st.session_state.processed_image = result
                st.image(result, use_container_width=True)

    if st.session_state.processed_image:
        st.markdown("**Current Working Image:**")
        st.image(st.session_state.processed_image, use_container_width=True)
        if st.button("Reset Image"):
            st.session_state.processed_image = None
            st.rerun()

# ====================== IMAGE TO TEXT (OCR) ======================
st.markdown("---")
st.subheader("📝 Image to Text (OCR)")
if st.button("🔍 Extract Text from Image", use_container_width=True):
    img_for_ocr = st.session_state.processed_image or original_image
    if img_for_ocr is None:
        st.warning("Please upload or generate an image first.")
    else:
        with st.spinner("Reading text from image... (first time may take longer)"):
            try:
                extracted = extract_text_from_image(img_for_ocr)
                if extracted:
                    st.session_state.extracted_text = extracted
                    st.success("✅ Text extracted successfully!")
                else:
                    st.warning("No text found in the image.")
                    st.session_state.extracted_text = ""
            except Exception as e:
                st.error(f"OCR Error: {e}")

if st.session_state.extracted_text:
    st.text_area("Extracted Text", st.session_state.extracted_text, height=150)

# ====================== VIDEO SETTINGS ======================
st.markdown("---")
st.subheader("🎬 Video Settings")
col1, col2 = st.columns(2)
with col1:
    duration = st.slider("Duration (seconds)", 3.0, 15.0, 6.0, 0.5)
    zoom = st.slider("Zoom Intensity", 1.1, 2.0, 1.35, 0.05)
with col2:
    motion = st.selectbox("Motion Style", [
        "Zoom In (Center)",
        "Zoom Out",
        "Pan Left to Right",
        "Pan Right to Left",
        "Pan Up",
        "Pan Down"
    ])

st.markdown("##### 📝 Title / Text Overlay")
title_text = st.text_input(
    "Video Title",
    value=st.session_state.get("extracted_text", "")[:80] if st.session_state.get("extracted_text") else "",
    placeholder="My Beautiful Memory"
)
title_position = st.selectbox("Title Position", ["top", "center", "bottom"], index=0)

st.markdown("##### 🎵 Background Music / Narration")
audio_source = st.radio(
    "Audio Source",
    ["Upload Music", "Text-to-Speech (Narration)", "No Audio"],
    horizontal=True
)

audio_path = None
if audio_source == "Upload Music":
    audio_file = st.file_uploader("Upload MP3 / WAV music", type=["mp3", "wav", "m4a"])
    if audio_file:
        tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tfile.write(audio_file.read())
        audio_path = tfile.name
        tfile.close()
elif audio_source == "Text-to-Speech (Narration)":
    tts_text = st.text_area(
        "Text to convert to speech",
        value=st.session_state.get("extracted_text", ""),
        placeholder="Once upon a time, in a beautiful place...",
        height=120
    )
    col_x, col_y = st.columns(2)
    with col_x:
        tts_lang = st.selectbox(
            "Language",
            options=[
                ("English", "en"),
                ("Indonesian", "id"),
                ("Spanish", "es"),
                ("French", "fr"),
                ("German", "de"),
                ("Japanese", "ja"),
                ("Korean", "ko"),
                ("Chinese", "zh-CN"),
                ("Arabic", "ar"),
                ("Hindi", "hi"),
            ],
            format_func=lambda x: x[0]
        )
        tts_lang_code = tts_lang[1]
    with col_y:
        tts_slow = st.checkbox("Slow speech", value=False)

    if st.button("🔊 Generate Speech"):
        if tts_text.strip():
            with st.spinner("Generating speech..."):
                if st.session_state.tts_audio_path and os.path.exists(st.session_state.tts_audio_path):
                    try:
                        os.unlink(st.session_state.tts_audio_path)
                    except:
                        pass
                path = text_to_audio(tts_text, lang=tts_lang_code, slow=tts_slow)
                st.session_state.tts_audio_path = path
                st.success("✅ Speech generated!")
                st.audio(path)
        else:
            st.warning("Please enter some text first.")

    if st.session_state.tts_audio_path and os.path.exists(st.session_state.tts_audio_path):
        audio_path = st.session_state.tts_audio_path
        st.caption("Using generated speech as video audio")

if st.button("🎬 Generate Video", type="primary", use_container_width=True):
    final_image = st.session_state.processed_image or original_image
    if final_image is None:
        st.error("Please upload an image or generate one from text first.")
    else:
        zoom_in = True
        pan_x, pan_y = 0.0, 0.0
        if motion == "Zoom Out":
            zoom_in = False
        elif motion == "Pan Left to Right":
            pan_x = 0.6
        elif motion == "Pan Right to Left":
            pan_x = -0.6
        elif motion == "Pan Up":
            pan_y = -0.5
        elif motion == "Pan Down":
            pan_y = 0.5

        with st.spinner("Generating video... Please wait"):
            try:
                if st.session_state.video_path and os.path.exists(st.session_state.video_path):
                    try:
                        os.unlink(st.session_state.video_path)
                    except:
                        pass
                video_path = create_video_from_image(
                    final_image,
                    duration=duration,
                    zoom_factor=zoom,
                    pan_x=pan_x,
                    pan_y=pan_y,
                    zoom_in=zoom_in,
                    title=title_text,
                    title_position=title_position,
                    audio_path=audio_path
                )
                st.session_state.video_path = video_path
                st.success("✅ Video generated successfully!")
            except Exception as e:
                st.error(f"Error: {e}")

if st.session_state.video_path and os.path.exists(st.session_state.video_path):
    st.markdown("---")
    st.subheader("📥 Your Video is Ready")
    st.video(st.session_state.video_path)
    with open(st.session_state.video_path, "rb") as f:
        video_bytes = f.read()
    st.download_button(
        label="⬇️ Download Video (MP4)",
        data=video_bytes,
        file_name="my_video.mp4",
        mime="video/mp4",
        use_container_width=True
    )

# ====================== NEW GRAPHS SECTION ======================
st.markdown("---")
st.subheader("📈 2D & 3D Graphs")

tab1, tab2 = st.tabs(["📊 2D Graph", "🧊 3D Graph"])

with tab1:
    st.markdown("### Create 2D Graph")
    col_2d1, col_2d2 = st.columns(2)
    with col_2d1:
        func_2d = st.selectbox(
            "Function Type",
            ["sine", "cosine", "quadratic", "exponential"],
            key="func_2d"
        )
    with col_2d2:
        points_2d = st.slider("Number of Points", 100, 1000, 500, 50, key="points_2d")

    x_min, x_max = st.slider("X Range", -20.0, 20.0, (-10.0, 10.0), key="x_range")

    if st.button("Generate 2D Graph", use_container_width=True, key="btn_2d"):
        with st.spinner("Creating 2D graph..."):
            fig_2d = create_2d_graph(func_type=func_2d, x_range=(x_min, x_max), points=points_2d)
            st.pyplot(fig_2d)
            plt.close(fig_2d)

with tab2:
    st.markdown("### Create 3D Graph")
    col_3d1, col_3d2 = st.columns(2)
    with col_3d1:
        func_3d = st.selectbox(
            "3D Function Type",
            ["surface", "wave", "saddle", "ripple"],
            key="func_3d"
        )
    with col_3d2:
        resolution_3d = st.slider("Resolution", 20, 100, 50, 5, key="res_3d")

    if st.button("Generate 3D Graph", use_container_width=True, key="btn_3d"):
        with st.spinner("Creating 3D graph..."):
            fig_3d = create_3d_graph(func_type=func_3d, resolution=resolution_3d)
            st.pyplot(fig_3d)
            plt.close(fig_3d)
