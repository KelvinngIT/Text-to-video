import streamlit as st
import smtplib
import random
import string
import time
import tempfile
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from PIL import Image
import numpy as np
from moviepy.editor import ImageClip
from gtts import gTTS
import pytesseract
from io import BytesIO

# ====================== PAGE CONFIG ======================
st.set_page_config(
    page_title="AI Media Tools",
    page_icon="🎬",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ====================== HELPER FUNCTIONS ======================
def generate_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))

def send_otp_email(to_email: str, otp: str) -> bool:
    """Send OTP via SMTP using Streamlit secrets."""
    try:
        if "smtp" not in st.secrets:
            st.error("SMTP secrets are missing!")
            return False

        smtp_server = st.secrets["smtp"]["server"]
        smtp_port = int(st.secrets["smtp"]["port"])
        sender_email = st.secrets["smtp"]["email"]
        sender_password = st.secrets["smtp"]["password"]
        sender_name = st.secrets["smtp"].get("name", "AI Media Tools")

        msg = MIMEMultipart()
        msg["From"] = f"{sender_name} <{sender_email}>"
        msg["To"] = to_email
        msg["Subject"] = "Your Verification Code"

        body = f"""
Hello!

Your verification code is:

{otp}

This code expires in 10 minutes.

If you did not request this code, please ignore this email.
"""
        msg.attach(MIMEText(body, "plain"))

        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=30) as server:
                server.login(sender_email, sender_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(sender_email, sender_password)
                server.send_message(msg)

        return True

    except smtplib.SMTPAuthenticationError:
        st.error("Authentication failed. Please use a Google App Password.")
        return False
    except Exception as e:
        st.error(f"Failed to send email: {type(e).__name__}: {e}")
        return False

def create_video_from_image(image: Image.Image, duration: float = 6.0, zoom_factor: float = 1.35, fps: int = 24):
    """Create a simple Ken Burns zoom video."""
    img_array = np.array(image.convert("RGB"))

    clip = (
        ImageClip(img_array)
        .set_duration(duration)
        .resize(lambda t: 1 + (zoom_factor - 1) * (t / duration))
    )

    temp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    output_path = temp_file.name
    temp_file.close()

    clip.write_videofile(
        output_path,
        fps=fps,
        codec="libx264",
        audio=False,
        logger=None
    )
    return output_path

def image_to_text(image: Image.Image) -> str:
    """Extract text from image using OCR (pytesseract)."""
    try:
        text = pytesseract.image_to_string(image)
        return text.strip() if text.strip() else "No text detected in the image."
    except pytesseract.TesseractNotFoundError:
        return "OCR Error: Tesseract is not installed. Please add 'tesseract-ocr' to packages.txt"
    except Exception as e:
        return f"OCR Error: {e}"

def text_to_audio(text: str, lang: str = "en") -> str:
    """Convert text to speech and return the path of the MP3 file."""
    try:
        tts = gTTS(text=text, lang=lang)
        temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        output_path = temp_file.name
        temp_file.close()
        tts.save(output_path)
        return output_path
    except Exception as e:
        st.error(f"Text-to-Speech failed: {e}")
        return None

def scrape_website(url: str):
    """
    Scrape text and images from a website.
    Returns: (title, text_content, list_of_image_urls)
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Get title
        title = soup.title.string.strip() if soup.title else "No Title"

        # Remove script and style elements
        for script in soup(["script", "style", "noscript"]):
            script.decompose()

        # Extract text
        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        clean_text = "\n".join(lines)

        # Extract image URLs
        image_urls = []
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if src:
                full_url = urljoin(url, src)
                if full_url.startswith("http") and full_url not in image_urls:
                    image_urls.append(full_url)

        return title, clean_text, image_urls

    except Exception as e:
        st.error(f"Failed to scrape website: {e}")
        return None, None, []

def download_image(url: str):
    """Download an image and return it as bytes + PIL Image."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content))
        return response.content, img
    except Exception:
        return None, None

# ====================== SESSION STATE ======================
if "verified" not in st.session_state:
    st.session_state.verified = False
if "otp" not in st.session_state:
    st.session_state.otp = None
if "otp_time" not in st.session_state:
    st.session_state.otp_time = None
if "email" not in st.session_state:
    st.session_state.email = ""
if "video_path" not in st.session_state:
    st.session_state.video_path = None
if "audio_path" not in st.session_state:
    st.session_state.audio_path = None
if "scraped_text" not in st.session_state:
    st.session_state.scraped_text = None
if "scraped_images" not in st.session_state:
    st.session_state.scraped_images = []

# ====================== UI ======================
st.title("🎬 AI Media Tools")
st.markdown("Image → Video • Image → Text • Text → Audio • Website Scraper")

# ==================================================
# STEP 1 - EMAIL VERIFICATION
# ==================================================
if not st.session_state.verified:
    st.subheader("🔐 Step 1: Verify Email")

    email = st.text_input(
        "Email Address",
        value=st.session_state.email,
        placeholder="you@example.com"
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Send OTP", use_container_width=True):
            if not email or "@" not in email:
                st.warning("Please enter a valid email address.")
            else:
                otp = generate_otp()
                st.session_state.otp = otp
                st.session_state.otp_time = time.time()
                st.session_state.email = email

                with st.spinner("Sending OTP..."):
                    success = send_otp_email(email, otp)

                if success:
                    st.success(f"OTP sent to {email}")

    with col2:
        if st.button("Clear", use_container_width=True):
            st.session_state.otp = None
            st.session_state.otp_time = None
            st.session_state.email = ""
            st.rerun()

    if st.session_state.otp:
        st.markdown("---")
        entered_otp = st.text_input("Enter OTP", max_chars=6)

        if st.button("Verify OTP", type="primary", use_container_width=True):
            if time.time() - st.session_state.otp_time > 600:
                st.error("OTP expired. Request a new one.")
                st.session_state.otp = None
            elif entered_otp.strip() == st.session_state.otp:
                st.session_state.verified = True
                st.success("Email verified successfully!")
                st.balloons()
                time.sleep(1)
                st.rerun()
            else:
                st.error("Incorrect OTP.")

# ==================================================
# STEP 2 - MAIN TOOLS
# ==================================================
else:
    st.success(f"Verified as: {st.session_state.email}")

    if st.button("Logout / Change Email"):
        st.session_state.verified = False
        st.session_state.otp = None
        st.session_state.video_path = None
        st.session_state.audio_path = None
        st.session_state.scraped_text = None
        st.session_state.scraped_images = []
        st.rerun()

    st.markdown("---")

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "🎬 Image → Video",
        "📝 Image → Text",
        "🔊 Text → Audio",
        "🌐 Website Scraper"
    ])

    # ==================== TAB 1: Image to Video ====================
    with tab1:
        st.subheader("Upload Image → Generate Zoom Video")

        uploaded_file = st.file_uploader(
            "Choose an image",
            type=["jpg", "jpeg", "png", "webp"],
            key="video_uploader"
        )

        col_a, col_b = st.columns(2)
        with col_a:
            duration = st.slider("Duration (seconds)", 3.0, 12.0, 6.0, 0.5)
        with col_b:
            zoom = st.slider("Zoom", 1.1, 2.0, 1.35, 0.05)

        if uploaded_file:
            image = Image.open(uploaded_file)
            st.image(image, caption="Preview", use_container_width=True)

            if st.button("🎬 Generate Video", type="primary", use_container_width=True):
                try:
                    with st.spinner("Generating video..."):
                        video_path = create_video_from_image(
                            image=image,
                            duration=duration,
                            zoom_factor=zoom
                        )
                    st.session_state.video_path = video_path
                    st.success("Video generated successfully!")
                except Exception as e:
                    st.error(f"Video generation failed: {e}")

        if st.session_state.video_path and os.path.exists(st.session_state.video_path):
            st.markdown("---")
            st.subheader("📥 Download Video")
            st.video(st.session_state.video_path)

            with open(st.session_state.video_path, "rb") as f:
                video_data = f.read()

            st.download_button(
                label="⬇️ Download MP4",
                data=video_data,
                file_name="generated_video.mp4",
                mime="video/mp4",
                use_container_width=True
            )

    # ==================== TAB 2: Image to Text ====================
    with tab2:
        st.subheader("Upload Image → Extract Text (OCR)")

        ocr_file = st.file_uploader(
            "Choose an image containing text",
            type=["jpg", "jpeg", "png", "webp"],
            key="ocr_uploader"
        )

        if ocr_file:
            image = Image.open(ocr_file)
            st.image(image, caption="Uploaded Image", use_container_width=True)

            if st.button("📝 Extract Text", type="primary", use_container_width=True):
                with st.spinner("Extracting text..."):
                    extracted_text = image_to_text(image)

                st.markdown("### Extracted Text:")
                st.text_area("Result", value=extracted_text, height=250)

                st.download_button(
                    label="⬇️ Download Text",
                    data=extracted_text,
                    file_name="extracted_text.txt",
                    mime="text/plain",
                    use_container_width=True
                )

    # ==================== TAB 3: Text to Audio ====================
    with tab3:
        st.subheader("Convert Text → Speech (Audio)")

        text_input = st.text_area(
            "Enter the text you want to convert to speech",
            height=150,
            placeholder="Type or paste your text here..."
        )

        lang = st.selectbox(
            "Language",
            options=["en", "zh-cn", "zh-tw", "ja", "ko", "es", "fr", "de", "hi"],
            format_func=lambda x: {
                "en": "English",
                "zh-cn": "Chinese (Simplified)",
                "zh-tw": "Chinese (Traditional)",
                "ja": "Japanese",
                "ko": "Korean",
                "es": "Spanish",
                "fr": "French",
                "de": "German",
                "hi": "Hindi"
            }.get(x, x)
        )

        if st.button("🔊 Generate Audio", type="primary", use_container_width=True):
            if not text_input.strip():
                st.warning("Please enter some text.")
            else:
                with st.spinner("Generating audio..."):
                    audio_path = text_to_audio(text_input, lang=lang)

                if audio_path:
                    st.session_state.audio_path = audio_path
                    st.success("Audio generated successfully!")

        if st.session_state.audio_path and os.path.exists(st.session_state.audio_path):
            st.markdown("---")
            st.subheader("🎧 Listen / Download")

            st.audio(st.session_state.audio_path, format="audio/mp3")

            with open(st.session_state.audio_path, "rb") as f:
                audio_data = f.read()

            st.download_button(
                label="⬇️ Download MP3",
                data=audio_data,
                file_name="speech.mp3",
                mime="audio/mp3",
                use_container_width=True
            )

    # ==================== TAB 4: Website Scraper ====================
    with tab4:
        st.subheader("🌐 Scrape Text & Images from Website")

        url = st.text_input(
            "Enter website URL",
            placeholder="https://example.com"
        )

        if st.button("🔍 Scrape Website", type="primary", use_container_width=True):
            if not url or not url.startswith("http"):
                st.warning("Please enter a valid URL starting with http:// or https://")
            else:
                with st.spinner("Scraping website..."):
                    title, text, image_urls = scrape_website(url)

                if text:
                    st.session_state.scraped_text = text
                    st.session_state.scraped_images = image_urls
                    st.success(f"Successfully scraped: **{title}**")
                    st.info(f"Found {len(image_urls)} images")

        # Show scraped text
        if st.session_state.scraped_text:
            st.markdown("---")
            st.markdown("### 📄 Extracted Text")
            st.text_area("Website Text", value=st.session_state.scraped_text, height=300)

            st.download_button(
                label="⬇️ Download Text (.txt)",
                data=st.session_state.scraped_text,
                file_name="website_text.txt",
                mime="text/plain",
                use_container_width=True
            )

        # Show and download images
        if st.session_state.scraped_images:
            st.markdown("---")
            st.markdown(f"### 🖼️ Found Images ({len(st.session_state.scraped_images)})")

            for idx, img_url in enumerate(st.session_state.scraped_images[:20]):  # limit to 20
                col1, col2 = st.columns([3, 1])

                with col1:
                    st.caption(img_url)

                with col2:
                    img_bytes, img = download_image(img_url)
                    if img_bytes and img:
                        st.image(img, width=120)

                        # Get file extension
                        ext = os.path.splitext(urlparse(img_url).path)[1] or ".jpg"
                        if ext.lower() not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
                            ext = ".jpg"

                        st.download_button(
                            label="⬇️ Download",
                            data=img_bytes,
                            file_name=f"image_{idx+1}{ext}",
                            mime=f"image/{ext[1:]}",
                            key=f"img_download_{idx}"
                        )
