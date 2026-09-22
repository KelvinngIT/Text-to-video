import streamlit as st
import smtplib
import random
import string
import time
import tempfile
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from PIL import Image
import numpy as np
from moviepy.editor import ImageClip
from moviepy.video.fx.all import resize

# ====================== PAGE CONFIG ======================
st.set_page_config(
    page_title="Image → Video Generator",
    page_icon="🎬",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ====================== HELPER FUNCTIONS ======================

def generate_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


def send_otp_email(to_email: str, otp: str) -> bool:
    """Send OTP via SMTP. Credentials come from Streamlit secrets."""
    try:
        smtp_server = st.secrets["smtp"]["server"]
        smtp_port = st.secrets["smtp"]["port"]
        sender_email = st.secrets["smtp"]["email"]
        sender_password = st.secrets["smtp"]["password"]
        sender_name = st.secrets["smtp"].get("name", "Image to Video App")

        msg = MIMEMultipart()
        msg["From"] = f"{sender_name} <{sender_email}>"
        msg["To"] = to_email
        msg["Subject"] = "Your Verification Code - Image to Video"

        body = f"""
        Hello!

        Your verification code is:

        👉  {otp}  👈

        This code will expire in 10 minutes.

        If you did not request this, please ignore this email.
        """
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)

        return True
    except Exception as e:
        st.error(f"Failed to send email: {e}")
        return False


def create_video_from_image(
    image: Image.Image,
    duration: float = 6.0,
    zoom_factor: float = 1.35,
    fps: int = 24
) -> str:
    """Create a Ken Burns style video from a single image."""
    img_array = np.array(image.convert("RGB"))
    clip = ImageClip(img_array).set_duration(duration)
    w, h = clip.size

    def make_frame(t):
        progress = t / duration
        current_zoom = 1.0 + (zoom_factor - 1.0) * progress
        x_offset = int((w * (current_zoom - 1)) * 0.3 * progress)
        y_offset = int((h * (current_zoom - 1)) * 0.2 * progress)

        new_w = int(w * current_zoom)
        new_h = int(h * current_zoom)
        resized = resize(clip, newsize=(new_w, new_h)).get_frame(t)

        x1 = min(max(x_offset, 0), new_w - w)
        y1 = min(max(y_offset, 0), new_h - h)
        return resized[y1:y1 + h, x1:x1 + w]

    animated = clip.fl(lambda gf, t: make_frame(t), apply_to=["mask"])

    temp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    output_path = temp_file.name
    temp_file.close()

    animated.write_videofile(
        output_path,
        fps=fps,
        codec="libx264",
        audio=False,
        preset="medium",
        threads=4,
        logger=None
    )
    return output_path


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


# ====================== UI ======================

st.title("🖼️ → 🎬 Image to Video Generator")
st.markdown("Upload a photo → get a cinematic video. Email verification required.")

# ---------- STEP 1: EMAIL VERIFICATION ----------
if not st.session_state.verified:
    st.subheader("🔐 Step 1: Verify your email")

    email = st.text_input("Enter your email address", value=st.session_state.email, placeholder="you@example.com")

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
                    st.success(f"OTP sent to **{email}**! Check your inbox (and spam).")
                else:
                    st.error("Could not send email. Please check your SMTP settings.")

    with col2:
        if st.button("Clear", use_container_width=True):
            st.session_state.otp = None
            st.session_state.otp_time = None
            st.session_state.email = ""
            st.rerun()

    if st.session_state.otp:
        st.markdown("---")
        user_otp = st.text_input("Enter the 6-digit OTP you received", max_chars=6)

        if st.button("Verify OTP", type="primary", use_container_width=True):
            # Check expiry (10 minutes)
            if time.time() - st.session_state.otp_time > 600:
                st.error("OTP has expired. Please request a new one.")
                st.session_state.otp = None
            elif user_otp.strip() == st.session_state.otp:
                st.session_state.verified = True
                st.success("✅ Email verified successfully!")
                st.balloons()
                time.sleep(1)
                st.rerun()
            else:
                st.error("Incorrect OTP. Please try again.")

# ---------- STEP 2: UPLOAD + GENERATE ----------
else:
    st.success(f"Verified as: **{st.session_state.email}**")
    if st.button("Logout / Change email"):
        st.session_state.verified = False
        st.session_state.otp = None
        st.session_state.video_path = None
        st.rerun()

    st.markdown("---")
    st.subheader("📤 Step 2: Upload image & generate video")

    uploaded_file = st.file_uploader(
        "Choose an image",
        type=["jpg", "jpeg", "png", "webp"],
        help="Best results with high-resolution landscape photos"
    )

    col_a, col_b = st.columns(2)
    with col_a:
        duration = st.slider("Video duration (seconds)", 3.0, 12.0, 6.0, 0.5)
    with col_b:
        zoom = st.slider("Zoom intensity", 1.1, 2.0, 1.35, 0.05)

    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        st.image(image, caption="Preview", use_container_width=True)

        if st.button("🎬 Generate Video", type="primary", use_container_width=True):
            with st.spinner("Generating your video... this may take 10–30 seconds"):
                try:
                    video_path = create_video_from_image(image, duration=duration, zoom_factor=zoom)
                    st.session_state.video_path = video_path
                    st.success("Video generated successfully!")
                except Exception as e:
                    st.error(f"Error generating video: {e}")

    # ---------- STEP 3: DOWNLOAD ----------
    if st.session_state.video_path and os.path.exists(st.session_state.video_path):
        st.markdown("---")
        st.subheader("📥 Your Video is Ready")

        # Show the video
        st.video(st.session_state.video_path)

        # Download button
        with open(st.session_state.video_path, "rb") as f:
            video_bytes = f.read()

        st.download_button(
            label="⬇️ Download Video (MP4)",
            data=video_bytes,
            file_name="generated_video.mp4",
            mime="video/mp4",
            use_container_width=True
        )
