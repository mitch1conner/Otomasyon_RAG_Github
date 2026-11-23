import os
import yaml
import streamlit as st
from google import genai
from google.genai import types

st.set_page_config(page_title="3. Asitleme RCA Ajanı", layout="wide")
st.title("🔧 3. Asitleme Kök Neden Analizi (RCA) Chatbotu")

# 1. YAML Profilini Yükle
@st.cache_data
def load_profile_text(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return yaml.dump(data, allow_unicode=True, sort_keys=False)

system_instruction_text = load_profile_text("3_asitleme_kok_neden_analizi_profili.yml")

# 2. API Anahtarını Önce Secrets'tan Al, Yoksa Yan Menüden İste
api_key = None
try:
    api_key = st.secrets.get("GEMINI_API_KEY")
except Exception:
    api_key = None

if not api_key:
    api_key = st.sidebar.text_input("Google Gemini API Anahtarı", type="password")

if not api_key:
    st.info("Devam etmek için Streamlit Secrets ayarına GEMINI_API_KEY ekleyin veya sol menüden girin.")
    st.stop()

client = genai.Client(api_key=api_key)
model_name = "gemini-3.1-pro-preview"

# 3. Dosya Yükleme (PDF, CSV, TXT)
uploaded_file = st.sidebar.file_uploader(
    "Analiz Edilecek Raporu Yükleyin (PDF, CSV, TXT)",
    type=["pdf", "csv", "txt"]
)

if uploaded_file and st.session_state.get("uploaded_file_name") != uploaded_file.name:
    temp_path = f"temp_{uploaded_file.name}"
    with open(temp_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    with st.spinner("Dosya Gemini'ye aktarılıyor..."):
        try:
            st.session_state.remote_file = client.files.upload(file=temp_path)
            st.session_state.uploaded_file_name = uploaded_file.name
            st.sidebar.success(f"Dosya bağlandı: {uploaded_file.name}")
        except Exception as e:
            st.sidebar.error(f"Dosya yükleme hatası: {e}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

# 4. Sohbet Geçmişi
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 5. Kullanıcı Mesajı ve Yanıt
if prompt := st.chat_input("Sahadaki arızayı yazın veya yüklediğiniz raporu analiz ettirin..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    contents = [prompt]
    if "remote_file" in st.session_state:
        contents.append(st.session_state.remote_file)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_response = ""
        config = types.GenerateContentConfig(
            system_instruction=system_instruction_text,
            temperature=0.2,
        )
        try:
            stream = client.models.generate_content_stream(
                model=model_name,
                contents=contents,
                config=config,
            )
            for chunk in stream:
                if chunk.text:
                    full_response += chunk.text
                    placeholder.markdown(full_response + "▌")
            placeholder.markdown(full_response)
            st.session_state.messages.append({"role": "assistant", "content": full_response})
        except Exception as e:
            st.error(f"Analiz sırasında hata oluştu: {e}")
