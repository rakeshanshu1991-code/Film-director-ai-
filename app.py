import streamlit as st
import sqlite3
import random
import string
import io
import re
import time
import urllib.parse
from datetime import datetime
import qrcode
from PIL import Image, ImageEnhance
from google import genai
from google.genai import types

# ================= 1. मर्चेंट डिटेल्स & सेटिंग्स =================
MY_UPI_ID = "rakeshkumarsaha03031991-1@okaxis"  # अपना UPI ID यहाँ बदल सकते हैं
BUSINESS_NAME = "Film Director AI"
OWNER_SECRET_PIN = "030391"   # यह आपकी मास्टर चाबी है
ACTIVATION_PRICE = "11.00"    # पहली बार VIP एक्टिवेशन चार्ज
SUBSEQUENT_PRICE = "5.00"     # एक्टिवेशन के बाद हर प्रोजेक्ट का चार्ज

# ================= 2. डेटाबेस सेटअप (सुपरफास्ट WAL मोड) =================
conn = sqlite3.connect("film_director_projects.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("PRAGMA journal_mode=WAL;")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    referral_code TEXT UNIQUE,
    referred_by TEXT,
    video_count INTEGER DEFAULT 0,
    bonus_credits INTEGER DEFAULT 0,
    has_paid_activation INTEGER DEFAULT 0,
    created_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    user_id TEXT,
    script TEXT,
    production_data TEXT,
    is_paid INTEGER DEFAULT 0,
    amount_paid REAL DEFAULT 0,
    utr_number TEXT,
    is_public INTEGER DEFAULT 0,
    created_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS plugins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_name TEXT,
    code_content TEXT,
    is_active INTEGER DEFAULT 1,
    added_on TEXT
)
""")

def add_column_if_not_exists(table, column, definition):
    try: cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    except sqlite3.OperationalError: pass

add_column_if_not_exists("projects", "utr_number", "TEXT")
add_column_if_not_exists("projects", "is_public", "INTEGER DEFAULT 0")
add_column_if_not_exists("users", "customer_id", "TEXT")
conn.commit()

# ================= 3. हेल्पर फंक्शन्स =================
@st.cache_data(show_spinner=False)
def generate_fast_qr(upi_url: str) -> bytes:
    qr = qrcode.make(upi_url)
    buf = io.BytesIO()
    qr.save(buf, format="PNG", optimize=True)
    return buf.getvalue()

def compress_image_for_fast_network(input_file):
    try:
        img = Image.open(input_file).convert("RGB")
        max_dim = 800
        if max(img.size) > max_dim:
            scale = max_dim / max(img.size)
            new_size = (int(img.size[0] * scale), int(img.size[1] * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        img = ImageEnhance.Sharpness(img).enhance(1.2)
        compressed_io = io.BytesIO()
        img.save(compressed_io, format="JPEG", quality=85, optimize=True)
        return img, compressed_io.getvalue()
    except Exception as e:
        return None, None

def generate_unique_12_digit_id():
    return f"{str(int(time.time() * 1000))[-8:]}{''.join(random.choices(string.digits, k=4))}"

def sanitize_user_input(val: str) -> str:
    clean_digits = re.sub(r'\D', '', val.strip().lower())
    if len(clean_digits) == 10: return clean_digits
    if len(clean_digits) == 12 and clean_digits.startswith("91"): return clean_digits[2:]
    return val.strip().lower()

def generate_html_report(director, pid, content):
    html = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <title>Director's Cut - {pid}</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f172a; color: #f8fafc; padding: 40px; line-height: 1.6; }}
            .header {{ border-bottom: 2px solid #fbbf24; padding-bottom: 20px; margin-bottom: 30px; text-align: center; }}
            h1 {{ color: #fbbf24; margin: 0; font-size: 2.5em; text-transform: uppercase; letter-spacing: 2px; }}
            .director {{ color: #38bdf8; font-size: 1.4em; font-weight: bold; margin-top: 10px; }}
            .content {{ background: #1e293b; padding: 35px; border-radius: 12px; white-space: pre-wrap; font-size: 1.1em; border-left: 4px solid #38bdf8; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🎬 Film Director AI Studio</h1>
            <div class="director">Directed by: {director}</div>
            <div style="color: #94a3b8; font-size: 1em; margin-top: 5px;">Production ID: {pid}</div>
        </div>
        <div class="content">{content}</div>
    </body>
    </html>
    """
    return html.encode('utf-8')

# ================= 4. पेज सेटअप & लाइव प्लगइन इंजन =================
st.set_page_config(page_title="Film Director AI", page_icon="🎬", layout="wide")

st.markdown("""
<style>
    .stTextInput>div>div>input { border-radius: 8px !important; }
    .stButton>button { border-radius: 10px !important; font-weight: bold !important; }
</style>
""", unsafe_allow_html=True)

# 🚀 लाइव कोड इंजेक्टर (ओनर डैशबोर्ड से जो कोड आएगा, वो यहाँ रन होगा)
try:
    cursor.execute("SELECT code_content FROM plugins WHERE is_active = 1")
    for plugin in cursor.fetchall():
        exec(plugin[0], globals(), locals())
except Exception as e:
    if st.session_state.get('is_owner'): st.error(f"⚠️ कस्टम कोड में एरर है: {e}")

if "is_authenticated" not in st.session_state: st.session_state.is_authenticated = False
if "is_owner" not in st.session_state: st.session_state.is_owner = False
if "current_user" not in st.session_state: st.session_state.current_user = None
if "payment_verified" not in st.session_state: st.session_state.payment_verified = False

st.markdown("""
<div style="display: flex; align-items: center; gap: 14px; background: linear-gradient(135deg, #090d16 0%, #1e1b4b 100%); border: 1.5px solid #fbbf24; border-radius: 14px; padding: 16px 20px; margin-bottom: 12px;">
    <div style="font-size: 40px;">🎬</div>
    <div>
        <div style="display: flex; align-items: center; gap: 8px;">
            <span style="color: #FBBF24; font-size: 24px; font-weight: 900;">फिल्म डायरेक्टर</span>
            <span style="background: #38BDF8; color: #000; font-size: 11px; font-weight: 800; padding: 2px 6px; border-radius: 4px;">AI STUDIO PRO</span>
        </div>
        <div style="color: #94A3B8; font-size: 12.5px;">Google Deep Thinking AI | हॉलीवुड सिनेमैटिक प्रॉम्प्ट्स | 12-Digit डिजिटल लॉकर</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ================= 5. 🚪 लॉगिन & रेफरल लॉजिक =================
if not st.session_state.is_authenticated:
    st.markdown("<div style='text-align:center; padding: 20px; background:#0f172a; border-radius:12px;'><h3 style='color:#38bdf8;'>✨ स्टूडियो में प्रवेश करें</h3></div><br>", unsafe_allow_html=True)
    with st.form("login_form"):
        user_raw = st.text_input("📱 मोबाइल / ✉️ ईमेल / 👑 ओनर पिन:")
        ref_code = st.text_input("🎁 रेफरल कोड (+1 फ्री प्रोजेक्ट के लिए):", placeholder="FILM9X42A")
        if st.form_submit_button("⚡ सुरक्षित OTP प्राप्त करें", use_container_width=True):
            if user_raw.strip() == OWNER_SECRET_PIN:
                st.session_state.is_authenticated = True
                st.session_state.is_owner = True
                st.session_state.current_user = "OWNER_ADMIN"
                st.rerun()
            clean_user = sanitize_user_input(user_raw)
            if len(clean_user) >= 5:
                st.session_state.sent_otp = ''.join(random.choices(string.digits, k=6))
                st.session_state.pending_user = clean_user
                st.session_state.applied_ref = ref_code.upper()
                st.toast("⚡ OTP भेजा गया!")
            else:
                st.error("सही जानकारी दर्ज करें।")

    if st.session_state.get("sent_otp"):
        st.info(f"सुरक्षा कोड (OTP): **{st.session_state.sent_otp}**")
        with st.form("verify_form"):
            otp_val = st.text_input("6 अंकों का OTP दर्ज करें:", value=st.session_state.sent_otp)
            if st.form_submit_button("🚀 वेरीफाई करें"):
                if otp_val == st.session_state.sent_otp:
                    user_id = st.session_state.pending_user
                    cursor.execute("SELECT video_count FROM users WHERE user_id = ?", (user_id,))
                    if not cursor.fetchone():
                        new_ref = "FILM" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
                        app_ref = st.session_state.get("applied_ref", "")
                        b_init = 1 if app_ref else 0
                        cursor.execute("INSERT INTO users (user_id, referral_code, referred_by, video_count, bonus_credits, has_paid_activation, created_at) VALUES (?, ?, ?, 0, ?, 0, ?)", (user_id, new_ref, app_ref, b_init, datetime.now().strftime("%d-%m-%Y %I:%M %p")))
                        if app_ref: cursor.execute("UPDATE users SET bonus_credits = bonus_credits + 1 WHERE referral_code = ?", (app_ref,))
                        conn.commit()
                    st.session_state.current_user = user_id
                    st.session_state.is_authenticated = True
                    st.session_state.sent_otp = None
                    st.rerun()
                else: st.error("गलत OTP!")
    st.stop()

# ================= 6. 🎬 मुख्य स्टूडियो और नेविगेशन =================
if not st.session_state.is_owner:
    cursor.execute("SELECT video_count, bonus_credits, referral_code, has_paid_activation, customer_id FROM users WHERE user_id = ?", (st.session_state.current_user,))
    u_info = cursor.fetchone()
    current_vcount, current_bonus, my_ref_code, has_paid_activation, my_customer_id = u_info
else:
    current_vcount, current_bonus, my_ref_code, has_paid_activation, my_customer_id = 0, 9999, "OWNER_VIP", 1, "OWNER_VIP_ID"

remaining_free = max(0, (5 + current_bonus) - current_vcount)

col_u1, col_u2 = st.columns([4, 1])
with col_u1:
    if st.session_state.is_owner: st.markdown("👑 `मास्टर ओनर मोड` | ⚡ अनलिमिटेड फ्री")
    else: st.markdown(f"👤 `{st.session_state.current_user}` | 🎁 शेष फ्री प्रोजेक्ट्स: **{remaining_free}**")
with col_u2:
    if st.button("लॉगआउट 🚪"): st.session_state.clear(); st.rerun()

# ओनर और यूज़र के लिए अलग-अलग टैब्स
if st.session_state.is_owner:
    t1, t2, t3, t4 = st.tabs(["🎥 स्टूडियो (नया प्रोजेक्ट)", "🔐 डिजिटल लॉकर", "🚀 रेफर & अर्न", "👑 ओनर पैनल"])
else:
    t1, t2, t3 = st.tabs(["🎥 स्टूडियो (नया प्रोजेक्ट)", "🔐 डिजिटल लॉकर", "🚀 रेफर & अर्न"])

# ----------------- टैब 1: नया प्रोजेक्ट -----------------
with t1:
    st.markdown("### ⚙️ 1. प्रोडक्शन सेटिंग्स")
    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1: director_name = st.text_input("🎬 डायरेक्टर का नाम:", value="Rakesh Kumar Sah")
    with col_s2: camera_movement = st.selectbox("🎥 कैमरा मूवमेंट:", ["Handheld (सस्पेंस/हॉरर)", "Static (ट्राइपॉड)", "Gimbal (स्मूथ)", "Drone (एरियल)"])
    with col_s3: atmosphere = st.selectbox("🌫️ माहौल (Atmosphere):", ["Dark & Foggy (डार्क रूम)", "Rainy Night", "Golden Hour", "Neon Cyberpunk"])
    
    cinema_style = st.selectbox("लाइटिंग टोन:", ["Realistic Dark (थ्रिलर)", "Horror / Suspense", "Cinematic Vintage"])

    with st.expander("🔑 Gemini API Key (अनिवार्य)"):
        gemini_key = st.text_input("API Key दर्ज करें:", type="password")

    st.markdown("### 📸 2. विजुअल संदर्भ")
    uploaded_image = st.file_uploader("कैरेक्टर या लोकेशन की फोटो चुनें (Optional):", type=["jpg", "png"])
    img_bytes = None
    if uploaded_image:
        img, img_bytes = compress_image_for_fast_network(uploaded_image)
        st.image(img, width=120)

    st.markdown("### ✍️ 3. स्क्रिप्ट")
    user_script = st.text_area("सीन का वर्णन करें:", height=100, placeholder="उदाहरण: एक व्यक्ति एक डार्क रूम में बैठकर वीडियो बना रहा है, तभी अचानक पीछे से...")

    if st.button("🎬 हॉलीवुड लेवल प्रोजेक्ट तैयार करें 🚀", type="primary", use_container_width=True):
        if not gemini_key or not user_script.strip():
            st.error("API Key और स्क्रिप्ट आवश्यक है।")
        else:
            # 🚀 सिनेमैटिक 40-सेकंड लोडिंग इफ़ेक्ट
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                status_text.markdown("🎥 **Arri Alexa कैमरा और लेंस कैलिब्रेट हो रहे हैं...**")
                for i in range(1, 26):
                    progress_bar.progress(i)
                    time.sleep(0.3)
                
                status_text.markdown("💡 **8K डार्क रूम लाइटिंग और सस्पेंस शैडो रेंडर हो रही है...**")
                for i in range(26, 56):
                    progress_bar.progress(i)
                    time.sleep(0.4)
                
                status_text.markdown("🤖 **Google Deep Search: AI डायरेक्टर ट्रेंडिंग डेटा निकाल रहा है...**")
                
                client = genai.Client(api_key=gemini_key)
                contents = []
                if img_bytes: contents.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))
                
                deep_thinking_prompt = f"""
                आप एक 'Deep Thinking AI' और मास्टर फिल्म डायरेक्टर हैं। 
                आपको Google Search का उपयोग करके इंटरनेट से सबसे लेटेस्ट और ट्रेंडिंग डेटा 'निचोड़कर' लाना है।

                Director Name: {director_name}
                Script: {user_script}
                Lighting: {cinema_style}
                Camera Movement: {camera_movement}
                Atmosphere: {atmosphere}

                निर्देश (Deep Analysis):
                1. Google Search करें और पता लगाएं कि आज के समय में {cinema_style} से जुड़े कौन से वीडियो सोशल मीडिया पर वायरल हो रहे हैं।
                2. उन वायरल ट्रेंड्स के आधार पर इस स्क्रिप्ट को एक ब्लॉकबस्टर 'डायरेक्टर कट' में बदलें।
                3. कैमरा सेटिंग्स, लाइटिंग, और बैकग्राउंड म्यूजिक का सटीक विवरण दें।
                4. सोशल मीडिया हुक जनरेट करें ताकि ग्राहक को लाखों व्यूज मिलें।
                """
                contents.append(deep_thinking_prompt)
                
                res = client.models.generate_content(
                    model="gemini-2.5-flash", 
                    contents=contents,
                    config=types.GenerateContentConfig(tools=[{"google_search": {}}], temperature=0.7)
                )

                for i in range(56, 86):
                    progress_bar.progress(i)
                    time.sleep(0.4)
                
                status_text.markdown("🎵 **बैकग्राउंड सस्पेंस म्यूजिक और ऑडियो मिक्सिंग हो रही है...**")
                for i in range(86, 101):
                    progress_bar.progress(i)
                    time.sleep(0.3)
                
                status_text.markdown("✅ **सुपरहिट प्रोजेक्ट सफलतापूर्वक तैयार हो गया!**")
                time.sleep(1)

                p_id = generate_unique_12_digit_id()
                now_str = datetime.now().strftime("%d-%m-%Y %I:%M %p")
                
                is_free_project = 1 if (remaining_free > 0 or st.session_state.is_owner) else 0
                
                cursor.execute("INSERT INTO projects (project_id, user_id, script, production_data, is_paid, created_at) VALUES (?, ?, ?, ?, ?, ?)", (p_id, st.session_state.current_user, user_script, res.text, is_free_project, now_str))
                
                if not st.session_state.is_owner:
                    cursor.execute("UPDATE users SET video_count = video_count + 1 WHERE user_id = ?", (st.session_state.current_user,))
                conn.commit()
                
                st.session_state.current_pid = p_id
                st.session_state.current_data = res.text
                st.session_state.current_director = director_name
                st.session_state.payment_verified = bool(is_free_project)
                st.rerun()

            except Exception as e:
                st.error(f"Google Deep Search Error: {e}")

    # ================= डाउनलोड, पेमेंट & सोशल मीडिया शेयरिंग =================
    if st.session_state.get("current_pid"):
        st.markdown("---")
        st.markdown(f"### 🎬 डायरेक्टर कट प्रीव्यू")
        st.code(st.session_state.current_data[:400] + "...\n\n[पूरी रिपोर्ट डाउनलोड करने के लिए नीचे क्लिक करें]", language="markdown")
        
        html_data = generate_html_report(st.session_state.current_director, st.session_state.current_pid, st.session_state.current_data)

        cursor.execute("SELECT is_paid FROM projects WHERE project_id = ?", (st.session_state.current_pid,))
        is_paid_status = cursor.fetchone()
        is_paid = is_paid_status[0] if is_paid_status else 0

        if is_paid == 1 or st.session_state.is_owner:
            st.success("🎉 आपका प्रोजेक्ट अनलॉक हो गया है!")
            
            cursor.execute("SELECT customer_id FROM users WHERE user_id = ?", (st.session_state.current_user,))
            cust_id_row = cursor.fetchone()
            existing_cust_id = cust_id_row[0] if cust_id_row else "OWNER_VIP_ID"
            
            if existing_cust_id and not st.session_state.is_owner:
                st.info(f"💡 आपका परमानेंट 12-अंकों का कस्टमर आईडी है: **{existing_cust_id}** (इसे डिजिटल लॉकर में इस्तेमाल करें)")
                
            st.download_button("📥 सिनेमैटिक HTML रिपोर्ट डाउनलोड करें", data=html_data, file_name=f"CallSheet_{st.session_state.current_pid}.html", use_container_width=True)
            
            # 🚀 सोशल मीडिया शेयरिंग
            st.markdown("---")
            st.markdown("### 🚀 अपने प्रोजेक्ट को दुनिया के साथ शेयर करें")
            viral_text = urllib.parse.quote("🎬 मैंने 'Film Director AI' से एक शानदार हॉलीवुड-लेवल प्रोजेक्ट तैयार किया है! आप भी आएं: https://film-director-ai.streamlit.app")
            
            c_wa, c_fb, c_tw, c_ig, c_tg = st.columns(5)
            with c_wa: st.markdown(f"<a href='https://wa.me/?text={viral_text}' target='_blank'><button style='background-color:#25D366; color:white; width:100%; border:none; padding:8px; border-radius:5px;'>📱 WhatsApp</button></a>", unsafe_allow_html=True)
            with c_fb: st.markdown(f"<a href='https://www.facebook.com/sharer/sharer.php?u=https://film-director-ai.streamlit.app' target='_blank'><button style='background-color:#1877F2; color:white; width:100%; border:none; padding:8px; border-radius:5px;'>📘 Facebook</button></a>", unsafe_allow_html=True)
            with c_tw: st.markdown(f"<a href='https://twitter.com/intent/tweet?text={viral_text}' target='_blank'><button style='background-color:#000000; color:white; width:100%; border:none; padding:8px; border-radius:5px;'>𝕏 Twitter</button></a>", unsafe_allow_html=True)
            with c_ig: st.markdown(f"<a href='https://instagram.com' target='_blank'><button style='background-color:#E1306C; color:white; width:100%; border:none; padding:8px; border-radius:5px;'>📸 Instagram</button></a>", unsafe_allow_html=True)
            with c_tg: st.markdown(f"<a href='https://t.me/share/url?url=https://film-director-ai.streamlit.app&text={viral_text}' target='_blank'><button style='background-color:#0088cc; color:white; width:100%; border:none; padding:8px; border-radius:5px;'>✈️ Telegram</button></a>", unsafe_allow_html=True)

        else:
            c_charge = ACTIVATION_PRICE if not has_paid_activation else SUBSEQUENT_PRICE
            st.warning(f"🔒 फुल स्क्रिप्ट डाउनलोड करने के लिए ₹{c_charge} का भुगतान करें।")
            
            st.markdown("""
            <div style="background-color: #1e293b; padding: 15px; border-radius: 8px; border-left: 4px solid #38bdf8; margin-bottom: 15px;">
                <strong>💡 पेमेंट के बाद क्या होगा?</strong><br>
                पेमेंट सफल होते ही आपको <strong>12-अंकों का एक पर्सनल VIP कस्टमर आईडी</strong> मिलेगा। 
                भविष्य में आप अपना यह कस्टमर आईडी डालकर अपना सारा काम (लॉकर में) कभी भी खोल सकेंगे!
            </div>
            """, unsafe_allow_html=True)
            
            col_p1, col_p2 = st.columns([1, 1])
            with col_p1: 
                upi_link = f"upi://pay?pa={MY_UPI_ID}&pn={BUSINESS_NAME}&am={c_charge}&cu=INR"
                st.image(generate_fast_qr(upi_link), width=180, caption="PhonePe/GPay से स्कैन करें")
            with col_p2:
                if st.button("🔄 पेमेंट ऑटो-वेरीफाई करें", type="primary", use_container_width=True):
                    with st.spinner("बैंक सर्वर से आपका पेमेंट कन्फर्म किया जा रहा है..."):
                        time.sleep(3)
                        
                        cursor.execute("SELECT customer_id FROM users WHERE user_id = ?", (st.session_state.current_user,))
                        cust_id_row = cursor.fetchone()
                        existing_cust_id = cust_id_row[0] if cust_id_row else None
                        
                        if not existing_cust_id:
                            new_customer_id = generate_unique_12_digit_id()
                            cursor.execute("UPDATE users SET has_paid_activation = 1, customer_id = ? WHERE user_id = ?", (new_customer_id, st.session_state.current_user))
                        
                        cursor.execute("UPDATE projects SET is_paid = 1 WHERE project_id = ?", (st.session_state.current_pid,))
                        conn.commit()
                        st.session_state.payment_verified = True
                        
                        st.success("✅ पेमेंट सक्सेसफुल! पेज रीफ्रेश हो रहा है...")
                        time.sleep(2)
                        st.rerun()

# ----------------- टैब 2: 🔐 डिजिटल लॉकर (Customer ID Vault) -----------------
with t2:
    st.markdown("### 🔐 पर्सनल डिजिटल लॉकर")
    st.write("अपना 12-अंकों का VIP कस्टमर आईडी दर्ज करें और अपना सारा पुराना काम (प्रोजेक्ट्स) एक साथ एक्सेस करें।")
    
    entered_cust_id = st.text_input("🔑 12-अंकों का कस्टमर आईडी दर्ज करें:", max_chars=12, placeholder="उदाहरण: 123456789012").strip()
    
    cursor.execute("SELECT customer_id FROM users WHERE user_id = ?", (st.session_state.current_user,))
    real_cust_id_tuple = cursor.fetchone()
    real_cust_id = real_cust_id_tuple[0] if real_cust_id_tuple else None

    if entered_cust_id:
        if st.session_state.is_owner or (real_cust_id and entered_cust_id == real_cust_id):
            st.success("✅ कस्टमर आईडी वेरीफाई हो गया! आपका सारा डेटा नीचे सुरक्षित है:")
            st.markdown("---")
            
            cursor.execute("SELECT project_id, script, production_data, is_paid FROM projects WHERE user_id = ? ORDER BY created_at DESC", (st.session_state.current_user,))
            history = cursor.fetchall()
            
            if not history:
                st.info("आपने अभी तक कोई काम सेव नहीं किया है।")
            else:
                for row in history:
                    with st.expander(f"🎬 प्रोजेक्ट कोड: {row[0]}"):
                        st.write(f"**स्क्रिप्ट:** {row[1]}")
                        if row[3] == 1 or st.session_state.is_owner:
                            html_dl = generate_html_report(st.session_state.current_user, row[0], row[2])
                            st.download_button("📥 डाउनलोड रिपोर्ट", data=html_dl, file_name=f"Project_{row[0]}.html", key=f"dl_{row[0]}")
                        else:
                            st.error("🔴 लॉक (Payment Required)")
        else:
            st.error("❌ यह कस्टमर आईडी अमान्य है या आपके खाते से मेल नहीं खाता।")
    else:
        st.info("लॉकर खोलने के लिए ऊपर अपना 12-अंकों का कस्टमर आईडी डालें। (यह आईडी आपको पहली बार ₹11 पेमेंट करने पर मिलता है)।")

# ----------------- टैब 3: 🚀 रेफर & अर्न -----------------
with t3:
    st.markdown("### 🚀 रेफर करें, फ्री प्रोजेक्ट पाएं")
    st.markdown(f"आपका रेफरल कोड: <b style='color:#38bdf8; font-size:24px;'>{my_ref_code}</b>", unsafe_allow_html=True)
    st.write("अपने दोस्तों को यह कोड शेयर करें। जब वे आपके कोड से लॉगिन करेंगे, तो आपको 1 एक्स्ट्रा फ्री प्रोजेक्ट मिलेगा!")
    viral_msg = f"🎬 Film Director AI Studio पर 1 फोटो और स्क्रिप्ट से हॉलीवुड प्रॉम्प्ट्स तैयार करें! मेरा कोड {my_ref_code} डालें और 1 बोनस फ्री प्रोजेक्ट पाएं: https://film-director-ai.streamlit.app"
    st.markdown(f'<a href="https://api.whatsapp.com/send?text={urllib.parse.quote(viral_msg)}" target="_blank"><div style="background:#25D366; color:white; padding:10px; text-align:center; border-radius:8px;">🟢 WhatsApp पर शेयर करें</div></a>', unsafe_allow_html=True)

# ----------------- टैब 4: 👑 ओनर पैनल (सिर्फ ओनर के लिए) -----------------
if st.session_state.is_owner:
    with t4:
        st.markdown("### 👑 मास्टर ओनर डैशबोर्ड")
        
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM projects")
        total_projects = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(amount_paid) FROM projects WHERE is_paid = 1")
        total_earnings = cursor.fetchone()[0]
        if total_earnings is None: total_earnings = 0.0

        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1: st.markdown(f"<div style='background:#1e293b; padding:20px; border-radius:10px; border-top:4px solid #38bdf8; text-align:center;'><h4>👥 कुल यूज़र्स</h4><h2 style='color:#38bdf8;'>{total_users}</h2></div>", unsafe_allow_html=True)
        with col_m2: st.markdown(f"<div style='background:#1e293b; padding:20px; border-radius:10px; border-top:4px solid #a855f7; text-align:center;'><h4>🎬 जनरेट वीडियो</h4><h2 style='color:#a855f7;'>{total_projects}</h2></div>", unsafe_allow_html=True)
        with col_m3: st.markdown(f"<div style='background:#1e293b; padding:20px; border-radius:10px; border-top:4px solid #22c55e; text-align:center;'><h4>💰 कुल कमाई</h4><h2 style='color:#22c55e;'>₹{total_earnings}</h2></div>", unsafe_allow_html=True)
            
        st.markdown("---")
        st.markdown("### 🛠️ लाइव ऐप अपडेटर (Code Injector)")
        st.warning("⚠️ यहाँ आप Python/Streamlit कोड डालकर ऐप में नए फीचर्स लाइव कर सकते हैं।")

        with st.form("live_code_form"):
            plugin_name = st.text_input("अपडेट / नए फीचर का नाम (जैसे: Diwali_Offer):")
            new_code = st.text_area("यहाँ अपना Python कोड टाइप करें:", height=150, placeholder='st.info("आज का स्पेशल ऑफर: 50% छूट!")')
            
            if st.form_submit_button("🚀 कोड को लाइव करें (Deploy)"):
                if new_code.strip():
                    try:
                        compile(new_code, '<string>', 'exec') # Syntax Check
                        cursor.execute("INSERT INTO plugins (plugin_name, code_content, added_on) VALUES (?, ?, ?)", (plugin_name, new_code, datetime.now().strftime("%d-%m-%Y %I:%M %p")))
                        conn.commit()
                        st.success("✅ नया फीचर सफलतापूर्वक सेव और लाइव हो गया!")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ आपके कोड में कोई गलती है: {e}")
                else: st.error("कृपया बॉक्स में कोई कोड डालें।")
                    
        st.markdown("#### ⚙️ आपके द्वारा लागू किए गए लाइव कोड्स")
        cursor.execute("SELECT id, plugin_name, added_on FROM plugins WHERE is_active = 1")
        active_plugins = cursor.fetchall()
        
        if active_plugins:
            for p in active_plugins:
                col_p1, col_p2 = st.columns([4, 1])
                with col_p1: st.write(f"🔹 **{p[1]}** (लागू: {p[2]})")
                with col_p2:
                    if st.button("❌ हटाएँ", key=f"del_{p[0]}"):
                        cursor.execute("DELETE FROM plugins WHERE id = ?", (p[0],))
                        conn.commit()
                        st.rerun()
        else:
            st.info("अभी तक कोई कस्टम कोड लाइव नहीं किया गया है।")
