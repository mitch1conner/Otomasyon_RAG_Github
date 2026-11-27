import os
import time
import yaml
import streamlit as st
from google import genai
from google.genai import types

st.set_page_config(page_title="3. Asitleme RCA Ajanı", layout="wide")
st.title("🔧 Otomasyon Kök Neden Analizi (RCA) Chatbotu")

# 1. YAML 
@st.cache_data
def load_profile_text(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return yaml.dump(data, allow_unicode=True, sort_keys=False)

system_instruction_text = load_profile_text("3_asitleme_kok_neden_analizi_profili.yml ")

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

client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})

# 3. Hesabın Erişebildiği Modelleri Listele
@st.cache_data(ttl=3600)
def get_available_models(_client):
    try:
        models = []
        for m in _client.models.list():
            name = m.name.replace("models/", "")
            actions = getattr(m, "supported_actions", None) or []
            if "gemini" in name.lower() and (not actions or "generateContent" in actions):
                models.append(name)
        if models:
            return models
    except Exception:
        pass
    return ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-3.1-pro-preview"]

available_models = get_available_models(client)
default_idx = 0
if "gemini-2.5-flash" in available_models:
    default_idx = available_models.index("gemini-2.5-flash")
else:
    for i, m in enumerate(available_models):
        if "flash" in m.lower():
            default_idx = i
            break

model_name = st.sidebar.selectbox("Model Seçin", available_models, index=default_idx)

# 4. Dosya Yükleme (PDF, CSV, TXT)
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

# 5. Çalışma Modu Seçici (Varsayılan: Sadece Sorulan Arızanın Çözümü)
calisma_modu = st.sidebar.radio(
    "Çalışma Modu",
    ["🔧 Saha Arıza Çözümü (Varsayılan)", "📊 Genel Rapor / Pareto Analizi"],
    index=0
)

if st.sidebar.button("🗑️ Sohbeti Temizle"):
    st.session_state.messages = []
    st.rerun()

# 6. Sohbet Geçmişi
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 7. Kullanıcı Mesajı ve Yanıt
if prompt := st.chat_input("Sahadaki arızayı yazın (örn. Kalınlık ölçme çalışmıyor)..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    if calisma_modu.startswith("🔧"):
        mod_kurali = """
KESİN TALİMAT — SADECE MOD B (SAHA ARIZA ÇÖZÜM MODU) ÇALIŞTIR:
1. Kullanıcı sahada yaşadığı spesifik bir arızayı soruyor. Genel rapor özeti, veri güvenilirliği, Pareto (80/20) tablosu KESİNLİKLE YAPMA.
2. Kullanıcının sorduğu ekipman/arıza dışındaki alakasız ekipmanlardan (ör. Kalınlık ölçme sorulduysa Absocoder, EPC, Kantar vb.) KESİNLİKLE BAHSETME.
3. Yüklenen PDF içinden SADECE kullanıcının yazdığı arıza ve eş anlamlılarıyla (ör. Kalınlık Ölçme -> X-Ray, open beam, shutter, chiller, HV OFF, JB-3 vb.) ilgili geçmiş kayıtları bul ve filtrele.
4. Yanıtını SADECE şu 3 başlıkta, net ve sahada uygulanabilir şekilde ver:
   - **1. PDF'te Eşleşen Geçmiş Kayıtlar ve Yapılan Çözümler:** Eşleşen her kayıt için Tarih/Arıza No, arıza detayı, sahada yapılan müdahale, geçici/kalıcı durumu ve PDF'ten kısa birebir alıntı.
   - **2. Sahada Hemen Uygulanacak Çözüm Adımları:** Geçmişte bu arızayı en sık çözen işlemlerden başlayarak teknisyenin sahada sırayla kontrol edip uygulayacağı somut 1-2-3 adımlı kontrol/çözüm listesi.
   - **3. Kök Neden Özeti (Sadece Bu Arıza İçin):** [Kayıt Kanıtı] ve [Teknik Hipotez] etiketleriyle kısa 5 Whys ve kalıcı önlem.
"""
        user_payload = f"[AKTİF MOD: SAHA ARIZA ÇÖZÜMÜ — SADECE BU ARIZAYA ODAKLAN]\nKullanıcı Arıza Bildirimi: {prompt}"
    else:
        mod_kurali = "KESİN TALİMAT: Sadece MOD A (Toplu Rapor ve Pareto Analizi) çalıştır."
        user_payload = prompt

    final_instruction = mod_kurali + "\n\n---\nREFERANS PROFİL:\n" + system_instruction_text

    contents = [user_payload]
    if "remote_file" in st.session_state:
        contents.append(st.session_state.remote_file)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        config = types.GenerateContentConfig(
            system_instruction=final_instruction,
            temperature=0.2,
        )

        fallback_models = list(dict.fromkeys([model_name, "gemini-2.5-flash", "gemini-2.0-flash"]))
        last_error = None
        success = False

        for current_model in fallback_models:
            for attempt in range(2):
                try:
                    full_response = ""
                    stream = client.models.generate_content_stream(
                        model=current_model,
                        contents=contents,
                        config=config,
                    )
                    for chunk in stream:
                        if chunk.text:
                            full_response += chunk.text
                            placeholder.markdown(full_response + "▌")
                    placeholder.markdown(full_response)
                    st.session_state.messages.append({"role": "assistant", "content": full_response})
                    success = True
                    break
                except Exception as e:
                    last_error = e
                    err_str = str(e)
