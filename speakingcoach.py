import streamlit as st
import requests
import json
import base64
import random
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# ================= CẤU HÌNH GIAO DIỆN =================
st.set_page_config(page_title="Speaking Flow Coach", page_icon="🌱", layout="centered")

st.markdown("""
    <style>
    /* Tùy chỉnh giao diện gọn gàng */
    .main-header { font-size: 32px; font-weight: 800; color: #2c3e50; text-align: center; margin-bottom: 20px; }
    
    /* Box hiển thị Topic */
    .topic-card {
        background: linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%);
        border-radius: 15px;
        padding: 30px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 25px;
        border: 1px solid #e1e4e8;
    }
    .topic-text { font-size: 28px; font-weight: 700; color: #2E86C1; }
    
    /* Các thẻ feedback */
    .feedback-card {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #ccc;
        margin-bottom: 15px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .logic-border { border-left-color: #3498db; }  /* Xanh dương cho Logic */
    .natural-border { border-left-color: #27ae60; } /* Xanh lá cho Tự nhiên */
    .vocab-border { border-left-color: #e67e22; }   /* Cam cho Từ vựng */
    
    .stButton button { width: 100%; border-radius: 8px; font-weight: 600; padding: 10px; }
    </style>
""", unsafe_allow_html=True)

# ================= 1. HÀM KẾT NỐI API & GEMINI =================

def generate_random_topic_ai():
    """Gọi Gemini để tạo một Topic ngẫu nhiên thú vị"""
    if "GOOGLE_API_KEY" not in st.secrets:
        return "Technology & Future (Công nghệ & Tương lai)"

    api_key = st.secrets["GOOGLE_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    
    # Prompt để lấy topic ngẫu nhiên
    prompt = """
    Generate ONE random, engaging, and thought-provoking keyword or short topic for IELTS Speaking (Part 2 style or abstract concept).
    It should be diverse (lifestyle, philosophy, technology, society, memories, etc.).
    Output strictly in this format: English Topic (Vietnamese Translation).
    Example: Digital Minimalism (Lối sống tối giản kỹ thuật số)
    Do not output anything else.
    """
    
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        resp = requests.post(url, headers=headers, data=json.dumps(data))
        if resp.status_code == 200:
            return resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        pass
    return "Childhood Memory (Ký ức tuổi thơ)" # Fallback nếu lỗi

def call_ai_coach(audio_bytes, topic):
    """
    Prompt tập trung vào Logic, Flow và Naturalness (Không chấm điểm)
    """
    if "GOOGLE_API_KEY" not in st.secrets:
        st.error("Thiếu GOOGLE_API_KEY")
        return None

    api_key = st.secrets["GOOGLE_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')

    # PROMPT QUAN TRỌNG: Đóng vai Coach thay vì Examiner
    prompt = f"""
    ROLE: Personal Communication Coach (Vietnamese speaking).
    TASK: Analyze the user's speech on the keyword: "{topic}".
    GOAL: Help the user speak more logically and sound more natural (like a native speaker). Do NOT give a band score.

    INSTRUCTIONS:
    1. **TRANSCRIPT**: Write down exactly what they said (Verbatim).
    2. **LOGIC & FLOW CHECK**: 
       - Did the ideas connect smoothly? 
       - Did they jump between ideas abruptly?
       - Suggest a better structure if theirs was confusing.
       - **LANGUAGE**: VIETNAMESE.
    3. **NATURALNESS UPGRADE**: 
       - Find phrases that sound "textbook" or "translated from Vietnamese" (Viet-glish).
       - Provide the "Native Speaker Version" for those specific phrases.
       - Explain the reason in VIETNAMESE.
    4. **REPETITION**: List words repeated > 3 times that make the speech boring.

    OUTPUT FORMAT: JSON STRICTLY (No markdown blocks).
    {{
        "transcript": "...",
        "logic_analysis": {{
            "status": "Tốt / Rối rắm / Lan man",
            "comment": "Analysis of the flow in Vietnamese...",
            "better_structure_suggestion": "Suggestion in Vietnamese..."
        }},
        "natural_fixes": [
            {{"original": "phrase user said", "better": "native idiom/phrase", "reason": "Explanation in Vietnamese"}}
        ],
        "repetition": ["word1", "word2"]
    }}
    """

    data = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "audio/wav", "data": audio_b64}}]}]}

    try:
        resp = requests.post(url, headers=headers, data=json.dumps(data))
        if resp.status_code == 200:
            txt = resp.json()['candidates'][0]['content']['parts'][0]['text']
            # Clean JSON
            txt = txt.replace("```json", "").replace("```", "").strip()
            return json.loads(txt)
        return None
    except Exception as e:
        return None

# ================= 2. HÀM HỖ TRỢ GOOGLE SHEETS =================
def connect_gsheet():
    """Kết nối Google Sheets"""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
        else:
            return None

        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # Mở Spreadsheet theo tên mới User cung cấp
        sheet = client.open("SPEAKING_JOURNAL") 
        return sheet
    except Exception as e:
        return None

def save_to_journal(topic, transcript, logic_fb, natural_fb):
    """Lưu nhật ký vào Sheet Speaking_Journal"""
    try:
        sheet = connect_gsheet()
        if sheet:
            try:
                ws = sheet.worksheet("Speaking_Journal")
            except:
                # Tạo sheet mới nếu chưa có
                ws = sheet.add_worksheet(title="Speaking_Journal", rows="1000", cols="6")
                ws.append_row(["Thời gian", "Chủ đề (Keyword)", "Transcript (Bạn nói)", "Góp ý Logic", "Góp ý Tự nhiên", "Từ lặp lại"])
            
            # Format dữ liệu để lưu
            timestamp = datetime.now().strftime("%d/%m/%Y %H:%M")
            
            # Xử lý Logic feedback thành text
            logic_text = f"Đánh giá: {logic_fb.get('status', '')}\nNhận xét: {logic_fb.get('comment', '')}\nGợi ý: {logic_fb.get('better_structure_suggestion', '')}"
            
            # Xử lý Natural feedback thành text list
            nat_list = "\n".join([f"- '{x['original']}' -> '{x['better']}' ({x['reason']})" for x in natural_fb.get('phrasing', [])])
            
            ws.append_row([
                timestamp, 
                topic, 
                transcript, 
                logic_text, 
                nat_list,
                ", ".join(natural_fb.get('repetition', []))
            ])
            return True
    except Exception as e:
        print(f"Lỗi lưu sheet: {e}")
        return False

def get_journal_history():
    try:
        sheet = connect_gsheet()
        if sheet:
            ws = sheet.worksheet("Speaking_Journal")
            return pd.DataFrame(ws.get_all_records())
    except:
        return pd.DataFrame()
    return pd.DataFrame()

# ================= 4. GIAO DIỆN CHÍNH =================

st.markdown("<div class='main-header'>🌱 Speaking Flow Coach</div>", unsafe_allow_html=True)

# Quản lý trạng thái Session: Nếu chưa có topic thì gọi AI tạo ngay lập tức
if 'topic' not in st.session_state: 
    with st.spinner("Đang tìm chủ đề thú vị cho bạn..."):
        st.session_state['topic'] = generate_random_topic_ai()

# TABS
tab_practice, tab_journal = st.tabs(["🎙️ Luyện Tập", "📓 Nhật Ký Đã Lưu"])

# --- TAB 1: LUYỆN TẬP ---
with tab_practice:
    # 1. Random Keyword từ AI
    st.markdown(f"""
        <div class='topic-card'>
            <div style='font-size: 16px; color: #7f8c8d; margin-bottom: 5px;'>KEYWORD CỦA BẠN</div>
            <div class='topic-text'>{st.session_state['topic']}</div>
        </div>
    """, unsafe_allow_html=True)

    col_btn1, col_btn2 = st.columns([1, 4])
    with col_btn1:
        if st.button("🎲 Đổi từ khóa"):
            with st.spinner("Đang nghĩ chủ đề mới..."):
                st.session_state['topic'] = generate_random_topic_ai()
            st.rerun()
    with col_btn2:
        st.info("💡 Mẹo: AI đã chọn ngẫu nhiên chủ đề này. Hãy nói về trải nghiệm cá nhân hoặc quan điểm của bạn trong 1-2 phút.")

    # 2. Audio Input
    audio = st.audio_input("Bấm để bắt đầu nói:", key=f"audio_{st.session_state['topic']}")

    # 3. Xử lý & Phản hồi
    if audio:
        st.write("---")
        with st.spinner("🎧 Coach đang nghe và phân tích (Feedback tiếng Việt)..."):
            audio_bytes = audio.read()
            result = call_ai_coach(audio_bytes, st.session_state['topic'])
        
        if result:
            # === HIỂN THỊ TRANSCRIPT ===
            with st.expander("📝 Xem Transcript (Những gì bạn vừa nói)", expanded=False):
                st.write(result.get("transcript", ""))

            # === PHẦN 1: LOGIC & MẠCH LẠC (QUAN TRỌNG) ===
            st.subheader("1. Tư Duy & Mạch Lạc (Logic Flow)")
            logic = result.get("logic_analysis", {})
            st.markdown(f"""
            <div class='feedback-card logic-border'>
                <b>Đánh giá:</b> {logic.get('status', '')}<br><br>
                💬 <b>Nhận xét:</b> {logic.get('comment', '')}<br>
                <hr>
                🚀 <b>Gợi ý cấu trúc tốt hơn:</b><br>
                <i>{logic.get('better_structure_suggestion', '')}</i>
            </div>
            """, unsafe_allow_html=True)

            # === PHẦN 2: DIỄN ĐẠT TỰ NHIÊN (NATURALNESS) ===
            st.subheader("2. Nâng Cấp Diễn Đạt (Native Phrasing)")
            fixes = result.get("natural_fixes", [])
            
            if fixes:
                for fix in fixes:
                    st.markdown(f"""
                    <div class='feedback-card natural-border'>
                        ❌ <b>Bạn nói:</b> "{fix['original']}"<br>
                        ✅ <b>Người bản xứ nói:</b> <span style='color:#27ae60; font-weight:bold; font-size:18px;'>"{fix['better']}"</span><br>
                        💡 <i>Tại sao? {fix['reason']}</i>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.success("Tuyệt vời! Cách diễn đạt của bạn rất tự nhiên, không bị 'sượng'.")

            # === PHẦN 3: TỪ VỰNG LẶP (VOCABULARY) ===
            reps = result.get("repetition", [])
            if reps:
                st.warning(f"⚠️ **Lặp từ:** Bạn dùng các từ sau quá nhiều lần, hãy tìm từ đồng nghĩa thay thế: **{', '.join(reps)}**")

            # === LƯU NHẬT KÝ ===
            # Dùng key hash để tránh lưu trùng khi rerun
            save_key = f"saved_{len(result.get('transcript', ''))}"
            if save_key not in st.session_state:
                with st.spinner("Đang lưu vào Sheet SPEAKING_JOURNAL..."):
                    saved = save_to_journal(
                        st.session_state['topic'],
                        result.get("transcript"),
                        result.get("logic_analysis"),
                        {"phrasing": fixes, "repetition": reps}
                    )
                    if saved:
                        st.toast("✅ Đã lưu bài nói vào Nhật Ký!", icon="📓")
                        st.session_state[save_key] = True

# --- TAB 2: NHẬT KÝ ---
with tab_journal:
    st.subheader("📓 Lịch sử luyện tập (Từ Sheet SPEAKING_JOURNAL)")
    if st.button("🔄 Cập nhật danh sách"):
        st.rerun()
    
    df = get_journal_history()
    if not df.empty:
        # Đảo ngược để hiện mới nhất lên đầu
        df = df.iloc[::-1]
        
        for index, row in df.iterrows():
            with st.expander(f"📅 {row['Thời gian']} - {row['Chủ đề (Keyword)']}"):
                st.markdown(f"**Transcript:**\n> {row['Transcript (Bạn nói)']}")
                st.divider()
                c1, c2 = st.columns(2)
                with c1:
                    st.info(f"**🧠 Góp ý Logic:**\n\n{row['Góp ý Logic']}")
                with c2:
                    st.success(f"**🗣️ Góp ý Tự nhiên:**\n\n{row['Góp ý Tự nhiên']}")
    else:
        st.info("Chưa có nhật ký nào. Hãy bắt đầu luyện tập bên tab kia nhé!")