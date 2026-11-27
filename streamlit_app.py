import json
import os
import time
import yaml
import streamlit as st
from google import genai
from google.genai import types

st.set_page_config(page_title="Otomasyon RAG Chatbot", layout="wide")
st.title("🔧 Otomasyon Kök Neden Analizi (RCA) Chatbotu")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FEEDBACK_FILE = os.path.join(BASE_DIR, "feedback_scores.json")


# 1. YAML Profilini Güvenli Yükle
@st.cache_data
def load_profile_text(file_name):
    file_path = os.path.join(BASE_DIR, file_name.strip())
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return yaml.dump(data, allow_unicode=True, sort_keys=False)


system_instruction_text = load_profile_text("3_asitleme_kok_neden_analizi_profili.yml")


# 1.5 Geri Bildirim (+1 / Değişmesin) Yardımcı Fonksiyonları
def load_feedback_data():
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_feedback_data(data):
    with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_positive_feedback(query_text: str, answer_text: str):
    """Kullanıcının işine yarayan çözüme +1 ekler; aksi durumda değişiklik yapmaz."""
    data = load_feedback_data()
    norm_query = query_text.strip().lower()
    summary = answer_text.strip()[:800]

    for item in data:
        if item["query"].strip().lower() == norm_query and item["answer"] == summary:
            item["score"] += 1
            save_feedback_data(data)
            return item["score"]

    data.append({
        "query": query_text.strip(),
        "answer": summary,
        "score": 1
    })
    save_feedback_data(data)
    return 1


def build_feedback_priority_context(top_k: int = 5) -> str:
    """En yüksek +1 skoruna sahip sahada doğrulanmış çözümleri prompta ekler."""
    data = load_feedback_data()
    if not data:
        return ""

    ranked = sorted(data, key=lambda x: x.get("score", 0), reverse=True)[:top_k]
    lines = [
        "SAHADA DOĞRULANMIŞ YÜKSEK ÖNCELİKLİ ÇÖZÜMLER (Geri Bildirim Skoruna Göre):",
        "Kullanıcının sorduğu arıza aşağıdakilerle eşleşiyorsa, en yüksek (+1) skora sahip çözümü en üstte önceliklendir:"
    ]
    for i, item in enumerate(ranked, start=1):
        lines.append(f"\n{i}) [Doğrulama Skoru: +{item['score']}] Arıza: {item['query']}\nOnaylı Çözüm Özeti:\n{item['answer']}")
    return "\n".join(lines)


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
    temp_path = os.path.join(BASE_DIR, f"temp_{uploaded_file.name}")
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

# Yan menüde onaylı çözüm skorlarını göster
feedback_items = load_feedback_data()
if feedback_items:
    with st.sidebar.expander(f"⭐ Doğrulanmış Çözümler ({len(feedback_items)})"):
        for item in sorted(feedback_items, key=lambda x: x["score"], reverse=True)[:5]:
            st.markdown(f"**+{item['score']}** — {item['query'][:60]}")

if st.sidebar.button("🗑️ Sohbeti Temizle"):
    st.session_state.messages = []
    st.rerun()

# 6. Sohbet Geçmişi ve +1 Geri Bildirim Butonu
if "messages" not in st.session_state:
    st.session_state.messages = []

for idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            if msg.get("feedback_given"):
                st.caption(f"✅ Geri bildirim kaydedildi (Güncel skor: +{msg.get('feedback_score', 1)})")
            else:
                if st.button("👍 Bu çözüm işime yaradı (+1)", key=f"fb_btn_{idx}"):
                    related_query = msg.get("related_query", "Genel Sorgu")
                    new_score = add_positive_feedback(related_query, msg["content"])
                    st.session_state.messages[idx]["feedback_given"] = True
                    st.session_state.messages[idx]["feedback_score"] = new_score
                    st.rerun()

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
4. Dokümanda geçmeyen hiçbir tamir önerisini uydurma; her bulgunun altına birebir kaynak alıntısı ekle.
5. Yanıtını SADECE şu 3 başlıkta, net ve sahada uygulanabilir şekilde ver:
  - **1. PDF'te Eşleşen Geçmiş Kayıtlar ve Yapılan Çözümler:** Eşleşen her kayıt için Tarih/Arıza No, arıza detayı, sahada yapılan müdahale, geçici/kalıcı durumu ve PDF'ten kısa birebir alıntı.
  - **2. Sahada Hemen Uygulanacak Çözüm Adımları:** Önce geri bildirim skoru (+1) yüksek doğrulanmış çözümlerden ve geçmişte en sık işe yarayan kayıtlardan başlayarak teknisyenin sahada uygulayacağı somut kontrol/çözüm listesi.
  - **3. Kök Neden Özeti (Sadece Bu Arıza İçin):** [Kayıt Kanıtı], [Varsayım] ve [Saha Doğrulama Sorusu] etiketleriyle kısa 5 Whys ve kalıcı önlem.
"""
        user_payload = f"[AKTİF MOD: SAHA ARIZA ÇÖZÜMÜ — SADECE BU ARIZAYA ODAKLAN]\nKullanıcı Arıza Bildirimi: {prompt}"
    else:
        mod_kurali = "KESİN TALİMAT: Sadece MOD A (Toplu Rapor ve Pareto Analizi) çalıştır."
        user_payload = prompt

    feedback_context = build_feedback_priority_context()
    final_instruction = mod_kurali
    if feedback_context:
        final_instruction += "\n\n---\n" + feedback_context
    final_instruction += "\n\n---\nREFERANS PROFİL:\n" + system_instruction_text
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
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": full_response,
                        "related_query": prompt,
                        "feedback_given": False,
                    })
                    success = True
                    break
                except Exception as e:
                    last_error = e
                    err_str = str(e)
                    if "429" in err_str or "503" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        time.sleep(2)
                    else:
                        break
            if success:
                break

        if success:
            st.rerun()
        else:
            st.error(f"Yanıt oluşturulamadı: {last_error}")
