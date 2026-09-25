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
from bs4 import BeautifulSoup
import hashlib
import random
import string
import re
from urllib.parse import urljoin, urlparse

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

# ====================== AUTH HELPERS ======================
USERS_FILE = "users.json"

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def load_users() -> dict:
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_users(users: dict):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def generate_confirmation_code(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))

def register_user(email: str, password: str) -> tuple[bool, str]:
    users = load_users()
    email = email.lower().strip()
    if not email or "@" not in email:
        return False, "Please enter a valid email address."
    if email in users:
        return False, "This email is already registered."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    
    code = generate_confirmation_code()
    users[email] = {
        "password": hash_password(password),
        "confirmed": False,
        "confirmation_code": code,
        "created_at": datetime.now().isoformat()
    }
    save_users(users)
    return True, code

def confirm_email(email: str, code: str) -> tuple[bool, str]:
    users = load_users()
    email = email.lower().strip()
    if email not in users:
        return False, "Email not found."
    if users[email]["confirmed"]:
        return True, "Email already confirmed. You can log in."
    if users[email]["confirmation_code"] == code.strip():
        users[email]["confirmed"] = True
        users[email].pop("confirmation_code", None)
        save_users(users)
        return True, "Email confirmed successfully! You can now log in."
    return False, "Invalid confirmation code."

def login_user(email: str, password: str) -> tuple[bool, str]:
    users = load_users()
    email = email.lower().strip()
    if email not in users:
        return False, "Email not registered."
    if not users[email]["confirmed"]:
        return False, "Please confirm your email first."
    if users[email]["password"] == hash_password(password):
        return True, "Login successful!"
    return False, "Incorrect password."

# ====================== WEBSITE SCRAPER ======================
def scrape_website(url: str) -> dict:
    """
    Scrape text, images, audio and video links from a website.
    Returns a dict with keys: text, images, audio, video, title, error
    """
    result = {
        "title": "",
        "text": "",
        "images": [],
        "audio": [],
        "video": [],
        "error": None
    }
    
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Title
        if soup.title and soup.title.string:
            result["title"] = soup.title.string.strip()
        
        # Clean text (remove scripts/styles)
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            tag.decompose()
        
        text = soup.get_text(separator="\n", strip=True)
        # Remove excessive blank lines
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        result["text"] = "\n".join(lines[:800])  # limit length
        
        base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        
        # Images
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
            if src:
                full_url = urljoin(url, src)
                alt = img.get("alt", "")
                result["images"].append({"url": full_url, "alt": alt})
        
        # Audio
        for audio in soup.find_all("audio"):
            src = audio.get("src")
            if src:
                result["audio"].append(urljoin(url, src))
            for source in audio.find_all("source"):
                s = source.get("src")
                if s:
                    result["audio"].append(urljoin(url, s))
        
        # Video tags
        for video in soup.find_all("video"):
            src = video.get("src")
            if src:
                result["video"].append(urljoin(url, src))
            for source in video.find_all("source"):
                s = source.get("src")
                if s:
                    result["video"].append(urljoin(url, s))
        
        # Common video embeds / direct links (YouTube, Vimeo, mp4, webm, etc.)
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full = urljoin(url, href)
            lower = full.lower()
            if any(ext in lower for ext in [".mp4", ".webm", ".mov", ".m4v", ".mkv"]):
                result["video"].append(full)
            elif any(ext in lower for ext in [".mp3", ".wav", ".ogg", ".m4a", ".aac"]):
                result["audio"].append(full)
            elif "youtube.com" in lower or "youtu.be" in lower or "vimeo.com" in lower:
                result["video"].append(full)
        
        # iframe embeds
        for iframe in soup.find_all("iframe", src=True):
            src = iframe["src"]
            full = urljoin(url, src)
            if any(x in full.lower() for x in ["youtube", "vimeo", "dailymotion", "player"]):
                result["video"].append(full)
        
        # Deduplicate
        result["images"] = list({img["url"]: img for img in result["images"]}.values())
        result["audio"] = list(dict.fromkeys(result["audio"]))
        result["video"] = list(dict.fromkeys(result["video"]))
        
    except Exception as e:
        result["error"] = str(e)
    
    return result

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

# ====================== GRAPH FUNCTIONS ======================
def create_2d_graph(func_type="sine", x_range=(-10, 10), points=500):
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
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_email" not in st.session_state:
    st.session_state.user_email = None
if "video_path" not in st.session_state:
    st.session_state.video_path = None
if "processed_image" not in st.session_state:
    st.session_state.processed_image = None
if "tts_audio_path" not in st.session_state:
    st.session_state.tts_audio_path = None
if "extracted_text" not in st.session_state:
    st.session_state.extracted_text = ""
if "scrape_result" not in st.session_state:
    st.session_state.scrape_result = None
if "pending_confirmation_email" not in st.session_state:
    st.session_state.pending_confirmation_email = None
if "pending_confirmation_code" not in st.session_state:
    st.session_state.pending_confirmation_code = None

# ====================== AUTH UI ======================
def show_auth_page():
    st.title("🔐 Login / Register")
    st.markdown("Please log in or create an account to use the app.")
    
    tab_login, tab_register, tab_confirm = st.tabs(["Login", "Register", "Confirm Email"])
    
    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_pw")
            submit = st.form_submit_button("Login", use_container_width=True)
            if submit:
                ok, msg = login_user(email, password)
                if ok:
                    st.session_state.logged_in = True
                    st.session_state.user_email = email.lower().strip()
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
    
    with tab_register:
        with st.form("register_form"):
            email = st.text_input("Email", key="reg_email")
            password = st.text_input("Password (min 6 chars)", type="password", key="reg_pw")
            password2 = st.text_input("Confirm Password", type="password", key="reg_pw2")
            submit = st.form_submit_button("Register", use_container_width=True)
            if submit:
                if password != password2:
                    st.error("Passwords do not match.")
                else:
                    ok, result = register_user(email, password)
                    if ok:
                        st.session_state.pending_confirmation_email = email.lower().strip()
                        st.session_state.pending_confirmation_code = result
                        st.success("Registration successful! Please confirm your email.")
                        st.info(f"**Demo Confirmation Code:** `{result}`  \n(In production this would be sent by email)")
                        st.rerun()
                    else:
                        st.error(result)
    
    with tab_confirm:
        st.markdown("Enter the confirmation code you received after registration.")
        email = st.text_input(
            "Email",
            value=st.session_state.pending_confirmation_email or "",
            key="confirm_email"
        )
        code = st.text_input("Confirmation Code", key="confirm_code")
        if st.button("Confirm Email", use_container_width=True):
            ok, msg = confirm_email(email, code)
            if ok:
                st.success(msg)
                st.session_state.pending_confirmation_email = None
                st.session_state.pending_confirmation_code = None
            else:
                st.error(msg)
        
        if st.session_state.pending_confirmation_code:
            st.info(f"Last generated code (demo): `{st.session_state.pending_confirmation_code}`")

# ====================== MAIN APP (only if logged in) ======================
if not st.session_state.logged_in:
    show_auth_page()
    st.stop()

# ----- Logged-in UI -----
st.sidebar.success(f"Logged in as: **{st.session_state.user_email}**")
if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.session_state.user_email = None
    st.rerun()

st.title("🖼️ → 🎬 Image to Video Generator Pro")
st.markdown("**Enhance • Watermark • Text-to-Image • OCR • TTS • Cinematic Video • Graphs • Web Scraper**")
st.markdown("---")

# ---------- USER COUNTER (Sidebar) ----------
with st.sidebar:
    st.markdown("### 📊 App Stats")
    user_count = get_users_past_year()
    st.metric("Users (Past Year)", user_count)
    st.caption("Counts unique sessions in the last 365 days")

# ====================== WEBSITE SCRAPER SECTION ======================
st.markdown("---")
st.subheader("🌐 Scrape Website (Text • Images • Audio • Video)")

scrape_url = st.text_input(
    "Enter website URL",
    placeholder="https://example.com or example.com",
    key="scrape_url"
)

if st.button("🔍 Scrape Website", use_container_width=True):
    if not scrape_url.strip():
        st.warning("Please enter a URL.")
    else:
        with st.spinner("Scraping website... Please wait"):
            result = scrape_website(scrape_url.strip())
            st.session_state.scrape_result = result

if st.session_state.scrape_result:
    res = st.session_state.scrape_result
    if res["error"]:
        st.error(f"Scrape failed: {res['error']}")
    else:
        st.success(f"✅ Scraped: **{res['title'] or 'Untitled'}**")
        
        tab_text, tab_img, tab_audio, tab_video = st.tabs(
            ["📝 Text", "🖼️ Images", "🎵 Audio", "🎬 Video"]
        )
        
        with tab_text:
            if res["text"]:
                st.text_area("Extracted Text", res["text"], height=300)
                st.download_button(
                    "⬇️ Download Text",
                    data=res["text"],
                    file_name="scraped_text.txt",
                    mime="text/plain"
                )
            else:
                st.info("No text found.")
        
        with tab_img:
            if res["images"]:
                st.write(f"Found **{len(res['images'])}** images")
                for i, img_info in enumerate(res["images"][:30]):  # limit display
                    cols = st.columns([3, 1])
                    with cols[0]:
                        st.markdown(f"**{i+1}.** [{img_info['url']}]({img_info['url']})")
                        if img_info.get("alt"):
                            st.caption(img_info["alt"])
                    with cols[1]:
                        try:
                            st.image(img_info["url"], width=120)
                        except:
                            st.caption("(preview failed)")
                if len(res["images"]) > 30:
                    st.info(f"... and {len(res['images']) - 30} more images")
            else:
                st.info("No images found.")
        
        with tab_audio:
            if res["audio"]:
                st.write(f"Found **{len(res['audio'])}** audio sources")
                for i, aurl in enumerate(res["audio"]):
                    st.markdown(f"**{i+1}.** [{aurl}]({aurl})")
                    try:
                        st.audio(aurl)
                    except:
                        pass
            else:
                st.info("No audio found.")
        
        with tab_video:
            if res["video"]:
                st.write(f"Found **{len(res['video'])}** video sources")
                for i, vurl in enumerate(res["video"]):
                    st.markdown(f"**{i+1}.** [{vurl}]({vurl})")
                    # Try to embed if it's a direct media file
                    if any(ext in vurl.lower() for ext in [".mp4", ".webm", ".mov"]):
                        try:
                            st.video(vurl)
                        except:
                            pass
            else:
                st.info("No video found.")

# ====================== UPLOAD IMAGE ======================
st.markdown("---")
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

# ====================== GRAPHS SECTION ======================
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
