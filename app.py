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
import zipfile
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

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
    try:
        text = pytesseract.image_to_string(image)
        return text.strip() if text.strip() else "No text detected in the image."
    except pytesseract.TesseractNotFoundError:
        return "OCR Error: Tesseract is not installed. Please add 'tesseract-ocr' to packages.txt"
    except Exception as e:
        return f"OCR Error: {e}"

def text_to_audio(text: str, lang: str = "en") -> str:
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

# ---------- Media extensions ----------
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".ico", ".tiff", ".tif"}
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".wma", ".opus"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v", ".flv", ".wmv", ".3gp"}
PDF_EXTS  = {".pdf"}

def get_extension(url: str) -> str:
    path = urlparse(url).path.lower()
    return os.path.splitext(path)[1]

def scrape_website(url: str):
    """
    Scrape text + all media file links (images, audio, video, pdf).
    Returns: (title, text, image_urls, audio_urls, video_urls, pdf_urls)
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.title.string.strip() if soup.title else "No Title"

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        clean_text = "\n".join(lines)

        image_urls = []
        audio_urls = []
        video_urls = []
        pdf_urls = []

        # 1. Images from <img> tags
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
            if src:
                full = urljoin(url, src)
                if full.startswith("http") and full not in image_urls:
                    image_urls.append(full)

        # 2. All media from <a href="...">
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            full = urljoin(url, href)
            if not full.startswith("http"):
                continue
            ext = get_extension(full)
            if ext in IMAGE_EXTS and full not in image_urls:
                image_urls.append(full)
            elif ext in AUDIO_EXTS and full not in audio_urls:
                audio_urls.append(full)
            elif ext in VIDEO_EXTS and full not in video_urls:
                video_urls.append(full)
            elif ext in PDF_EXTS and full not in pdf_urls:
                pdf_urls.append(full)

        return title, clean_text, image_urls, audio_urls, video_urls, pdf_urls

    except Exception as e:
        st.error(f"Failed to scrape website: {e}")
        return None, None, [], [], [], []

def download_image(url: str):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=12)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content))
        return response.content, img
    except Exception:
        return None, None

def download_file(url: str, timeout: int = 25):
    """Generic downloader → (content_bytes, filename) or (None, None)"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=timeout, stream=True)
        response.raise_for_status()
        filename = os.path.basename(urlparse(url).path) or "file"
        if "content-disposition" in response.headers:
            cd = response.headers["content-disposition"]
            if "filename=" in cd:
                filename = cd.split("filename=")[-1].strip().strip('"')
        return response.content, filename
    except Exception:
        return None, None

def create_pdf(text: str, title: str = "Document") -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=inch, leftMargin=inch,
                            topMargin=inch, bottomMargin=inch)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    for para in text.split("\n"):
        if para.strip():
            safe = para.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe, styles["Normal"]))
            story.append(Spacer(1, 6))
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

def create_zip(urls: list, prefix: str = "file") -> bytes:
    """Download a list of URLs and pack them into a ZIP."""
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, u in enumerate(urls):
            content, filename = download_file(u)
            if content:
                if not filename or filename == "file":
                    ext = get_extension(u) or ".bin"
                    filename = f"{prefix}_{idx+1}{ext}"
                zf.writestr(filename, content)
    zip_buffer.seek(0)
    return zip_buffer.getvalue()

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
if "scraped_audios" not in st.session_state:
    st.session_state.scraped_audios = []
if "scraped_videos" not in st.session_state:
    st.session_state.scraped_videos = []
if "scraped_pdfs" not in st.session_state:
    st.session_state.scraped_pdfs = []
if "scraped_title" not in st.session_state:
    st.session_state.scraped_title = "Website Content"

# ====================== UI ======================
st.title("🎬 AI Media Tools")
st.markdown("Image → Video • Image → Text • Text → Audio • Website Scraper")

# ==================================================
# STEP 1 - EMAIL VERIFICATION
# ==================================================
if not st.session_state.verified:
    st.subheader("🔐 Step 1: Verify Email")
    email = st.text_input("Email Address", value=st.session_state.email, placeholder="you@example.com")
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
                    if send_otp_email(email, otp):
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
        st.session_state.scraped_audios = []
        st.session_state.scraped_videos = []
        st.session_state.scraped_pdfs = []
        st.session_state.scraped_title = "Website Content"
        st.rerun()
    st.markdown("---")

    tab1, tab2, tab3, tab4 = st.tabs([
        "🎬 Image → Video",
        "📝 Image → Text",
        "🔊 Text → Audio",
        "🌐 Website Scraper"
    ])

    # ==================== TAB 1 ====================
    with tab1:
        st.subheader("Upload Image → Generate Zoom Video")
        uploaded_file = st.file_uploader("Choose an image", type=["jpg", "jpeg", "png", "webp"], key="video_uploader")
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
                        video_path = create_video_from_image(image, duration, zoom)
                    st.session_state.video_path = video_path
                    st.success("Video generated successfully!")
                except Exception as e:
                    st.error(f"Video generation failed: {e}")
        if st.session_state.video_path and os.path.exists(st.session_state.video_path):
            st.markdown("---")
            st.subheader("📥 Download Video")
            st.video(st.session_state.video_path)
            with open(st.session_state.video_path, "rb") as f:
                st.download_button("⬇️ Download MP4", f.read(), "generated_video.mp4", "video/mp4", use_container_width=True)

    # ==================== TAB 2 ====================
    with tab2:
        st.subheader("Upload Image → Extract Text (OCR)")
        ocr_file = st.file_uploader("Choose an image containing text", type=["jpg", "jpeg", "png", "webp"], key="ocr_uploader")
        if ocr_file:
            image = Image.open(ocr_file)
            st.image(image, caption="Uploaded Image", use_container_width=True)
            if st.button("📝 Extract Text", type="primary", use_container_width=True):
                with st.spinner("Extracting text..."):
                    st.session_state.ocr_text = image_to_text(image)
                st.markdown("### Extracted Text:")
                st.text_area("Result", value=st.session_state.ocr_text, height=250, key="ocr_result")
            if "ocr_text" in st.session_state and st.session_state.ocr_text:
                st.markdown("#### Download Options")
                c1, c2 = st.columns(2)
                with c1:
                    st.download_button("⬇️ Download Text (.txt)", st.session_state.ocr_text, "extracted_text.txt", "text/plain", use_container_width=True)
                with c2:
                    st.download_button("⬇️ Download PDF", create_pdf(st.session_state.ocr_text, "OCR Extracted Text"), "extracted_text.pdf", "application/pdf", use_container_width=True)

    # ==================== TAB 3 ====================
    with tab3:
        st.subheader("Convert Text → Speech (Audio)")
        text_input = st.text_area("Enter the text you want to convert to speech", height=150, placeholder="Type or paste your text here...")
        lang = st.selectbox("Language", ["en", "zh-cn", "zh-tw", "ja", "ko", "es", "fr", "de", "hi"],
                            format_func=lambda x: {"en": "English", "zh-cn": "Chinese (Simplified)", "zh-tw": "Chinese (Traditional)",
                                                   "ja": "Japanese", "ko": "Korean", "es": "Spanish", "fr": "French", "de": "German", "hi": "Hindi"}.get(x, x))
        if st.button("🔊 Generate Audio", type="primary", use_container_width=True):
            if not text_input.strip():
                st.warning("Please enter some text.")
            else:
                with st.spinner("Generating audio..."):
                    path = text_to_audio(text_input, lang)
                    if path:
                        st.session_state.audio_path = path
                        st.success("Audio generated successfully!")
        if st.session_state.audio_path and os.path.exists(st.session_state.audio_path):
            st.markdown("---")
            st.subheader("🎧 Listen / Download")
            st.audio(st.session_state.audio_path, format="audio/mp3")
            with open(st.session_state.audio_path, "rb") as f:
                st.download_button("⬇️ Download MP3", f.read(), "speech.mp3", "audio/mp3", use_container_width=True)

    # ==================== TAB 4: Website Scraper ====================
    with tab4:
        st.subheader("🌐 Scrape Text + Media Files from Website")
        url = st.text_input("Enter website URL", placeholder="https://example.com")
        if st.button("🔍 Scrape Website", type="primary", use_container_width=True):
            if not url or not url.startswith("http"):
                st.warning("Please enter a valid URL starting with http:// or https://")
            else:
                with st.spinner("Scraping website..."):
                    title, text, imgs, audios, videos, pdfs = scrape_website(url)
                if text is not None:
                    st.session_state.scraped_text = text
                    st.session_state.scraped_images = imgs
                    st.session_state.scraped_audios = audios
                    st.session_state.scraped_videos = videos
                    st.session_state.scraped_pdfs = pdfs
                    st.session_state.scraped_title = title or "Website Content"
                    st.success(f"Successfully scraped: **{title}**")
                    st.info(f"Images: {len(imgs)} • Audio: {len(audios)} • Video: {len(videos)} • PDFs: {len(pdfs)}")

        # ---- Text ----
        if st.session_state.scraped_text:
            st.markdown("---")
            st.markdown("### 📄 Extracted Text")
            st.text_area("Website Text", value=st.session_state.scraped_text, height=280)
            st.markdown("#### Download Text")
            c1, c2 = st.columns(2)
            with c1:
                st.download_button("⬇️ Download Text (.txt)", st.session_state.scraped_text, "website_text.txt", "text/plain", use_container_width=True)
            with c2:
                st.download_button("⬇️ Download as PDF", create_pdf(st.session_state.scraped_text, st.session_state.scraped_title),
                                   "website_content.pdf", "application/pdf", use_container_width=True)

        # ---- Helper to render a media section ----
        def render_media_section(title: str, urls: list, prefix: str, icon: str, mime_fallback: str, show_preview: bool = False):
            if not urls:
                return
            st.markdown("---")
            st.markdown(f"### {icon} {title} ({len(urls)})")

            selected = []
            display_limit = min(40, len(urls))
            for idx, u in enumerate(urls[:display_limit]):
                cols = st.columns([0.4, 4.2, 1.4])
                with cols[0]:
                    if st.checkbox("", key=f"sel_{prefix}_{idx}"):
                        selected.append(u)
                with cols[1]:
                    name = os.path.basename(urlparse(u).path) or f"{prefix}_{idx+1}"
                    st.markdown(f"**{name}**")
                    st.caption(u)
                with cols[2]:
                    content, filename = download_file(u)
                    if content:
                        if not filename:
                            filename = f"{prefix}_{idx+1}{get_extension(u) or ''}"
                        st.download_button("⬇️", content, filename, mime_fallback, key=f"dl_{prefix}_{idx}")
                        if show_preview and prefix == "img":
                            try:
                                st.image(Image.open(BytesIO(content)), width=90)
                            except Exception:
                                pass
                    else:
                        st.caption("❌")

            st.markdown(f"#### Bulk Download {title}")
            c1, c2 = st.columns(2)
            with c1:
                if selected:
                    st.download_button(
                        f"⬇️ Download Selected ({len(selected)}) as ZIP",
                        create_zip(selected, prefix),
                        f"selected_{prefix}s.zip",
                        "application/zip",
                        use_container_width=True
                    )
                else:
                    st.button(f"⬇️ Download Selected as ZIP", disabled=True, use_container_width=True)
            with c2:
                st.download_button(
                    f"⬇️ Download All ({len(urls)}) as ZIP",
                    create_zip(urls[:60], prefix),   # safety limit
                    f"all_{prefix}s.zip",
                    "application/zip",
                    use_container_width=True
                )

        # Render all media sections
        render_media_section("Found Images", st.session_state.scraped_images, "img", "🖼️", "image/jpeg", show_preview=True)
        render_media_section("Found Audio Files", st.session_state.scraped_audios, "audio", "🎵", "audio/mpeg")
        render_media_section("Found Video Files", st.session_state.scraped_videos, "video", "🎬", "video/mp4")
        render_media_section("Found PDF Files", st.session_state.scraped_pdfs, "pdf", "📑", "application/pdf")

        # Friendly message when nothing media-related was found
        if (st.session_state.scraped_text is not None and
            not st.session_state.scraped_images and
            not st.session_state.scraped_audios and
            not st.session_state.scraped_videos and
            not st.session_state.scraped_pdfs):
            st.info("No direct image / audio / video / PDF files were found on this page.")
