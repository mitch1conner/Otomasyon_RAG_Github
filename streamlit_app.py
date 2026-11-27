import json
import os
import time
import yaml
import streamlit as st
from google import genai
from google.genai import types
# Sayfaya ait özellikler
st.set_page_config(page_title="Otomasyon RAG Chatbot", layout="wide")
st.title("🔧 Otomasyon Kök Neden Analizi (RCA) Chatbotu")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FEEDBACK_FILE = os.path.join(BASE_DIR, "feedback_scores.json")
UPLOAD_DIR = os.path.join(BASE_DIR, "saved_docs")
META_FILE = os.path.join(UPLOAD_DIR, "active_file_meta.json")
os.makedirs(UPLOAD_DIR, exist_ok=True)
# 1. YAML veya MD Profilini Otomatik Bul ve Yükle
@st.cache_data
def load_profile_text(preferred_name):
    files_in_dir = os.listdir(BASE_DIR)

    # 1) Tam eşleşme
    for fname in files_in_dir:
        if fname.strip() == preferred_name.strip():
            target = os.path.join(BASE_DIR, fname)
            with open(target, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return yaml.dump(data, allow_unicode=True, sort_keys=False)

    # 2) Dify dışındaki herhangi bir .yml / .yaml profil dosyasını bul
    for fname in files_in_dir:
        low = fname.lower().strip()
        if low.endswith((".yml", ".yaml")) and "dify" not in low:
            target = os.path.join(BASE_DIR, fname)
            with open(target, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return yaml.dump(data, allow_unicode=True, sort_keys=False)

    # 3) Yedek olarak .md profil dosyasını oku
    for fname in files_in_dir:
        if fname.lower().strip().endswith(".md"):
            target = os.path.join(BASE_DIR, fname)
            with open(target, "r", encoding="utf-8") as f:
                return f.read()

    st.error(f"Profil dosyası bulunamadı. Klasördeki mevcut dosyalar: {files_in_dir}")
    st.stop()


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
        "score": 1,
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
        "Kullanıcının sorduğu arıza aşağıdakilerle eşleşiyorsa, en yüksek (+1) skora sahip çözümü en üstte önceliklendir:",
    ]
    for i, item in enumerate(ranked, start=1):
        lines.append(
            f"\n{i}) [Doğrulama Skoru: +{item['score']}] Arıza: {item['query']}\n"
            f"Onaylı Çözüm Özeti:\n{item['answer']}"
        )
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


# 3. Yalnızca Aktif ve Hizmet Veren Gemini Modellerini Listele
DEPRECATED_OR_NON_CHAT_KEYWORDS = (
    "gemini-1.0",
    "gemini-1.5",
    "gemini-2.0",
    "gemini-pro-vision",
    "gemini-ultra",
    "embedding",
    "aqa",
    "imagen",
    "veo",
    "tts",
    "audio",
    "image",
    "live",
    "robotics",
    "computer-use",
    "deep-research",
    "vision",
    "-exp",
    "-001",
    "-002",
    "tuning",
    "learnlm",
    "gemma",
)

ACTIVE_FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash-lite",
]


@st.cache_data(ttl=3600)
def get_available_models(_client):
    try:
        models = []
        for m in _client.models.list():
            name = m.name.replace("models/", "")
            low = name.lower()
            actions = getattr(m, "supported_actions", None) or []

            if not low.startswith("gemini-"):
                continue
            if actions and "generateContent" not in actions:
                continue
            if low in ("gemini-pro", "gemini-flash"):
                continue
            if any(bad in low for bad in DEPRECATED_OR_NON_CHAT_KEYWORDS):
                continue

            models.append(name)

        if models:
            # Kararlı 2.5 ve güncel sürümleri üstte sırala
            priority = {m: idx for idx, m in enumerate(ACTIVE_FALLBACK_MODELS)}
            models = sorted(
                list(dict.fromkeys(models)),
                key=lambda x: (priority.get(x, 99), "preview" in x.lower(), x),
            )
            return models
    except Exception:
        pass
    return ACTIVE_FALLBACK_MODELS


available_models = get_available_models(client)
default_idx = available_models.index("gemini-2.5-flash") if "gemini-2.5-flash" in available_models else 0
model_name = st.sidebar.selectbox("Model Seçin", available_models, index=default_idx)


# 4. Kalıcı Dosya Yönetimi (Tek Sefer Yükle, İstenince Sil)
def get_saved_file_meta():
    if os.path.exists(META_FILE):
        try:
            with open(META_FILE, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if os.path.exists(meta.get("local_path", "")):
                return meta
        except Exception:
            pass
    return None


def save_file_meta(meta):
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def ensure_gemini_file_ready(_client, meta):
    """Gemini'deki dosya hâlâ aktifse onu döndürür; 48 saat dolmuşsa yerelden yeniden yükler."""
    gemini_name = meta.get("gemini_name")
    if gemini_name:
        try:
            return _client.files.get(name=gemini_name)
        except Exception:
            pass

    remote_obj = _client.files.upload(file=meta["local_path"])
    meta["gemini_name"] = remote_obj.name
    save_file_meta(meta)
    return remote_obj


def delete_active_file(_client):
    meta = get_saved_file_meta()
    if meta:
        if meta.get("gemini_name"):
            try:
                _client.files.delete(name=meta["gemini_name"])
            except Exception:
                pass
        if os.path.exists(meta.get("local_path", "")):
            os.remove(meta["local_path"])
    if os.path.exists(META_FILE):
        os.remove(META_FILE)
    st.session_state.pop("remote_file", None)
    st.session_state.pop("uploaded_file_name", None)


st.sidebar.subheader("📁 Aktif Bakım Raporu")
active_meta = get_saved_file_meta()

if active_meta:
    if "remote_file" not in st.session_state or st.session_state.get("uploaded_file_name") != active_meta["file_name"]:
        with st.spinner("Kayıtlı rapor bağlanıyor..."):
            try:
                st.session_state.remote_file = ensure_gemini_file_ready(client, active_meta)
                st.session_state.uploaded_file_name = active_meta["file_name"]
            except Exception as e:
                st.sidebar.error(f"Kayıtlı dosya bağlanamadı: {e}")

    st.sidebar.success(f"Aktif Dosya: **{active_meta['file_name']}**")
    if st.sidebar.button("🗑️ Aktif Dosyayı Sil", use_container_width=True):
        delete_active_file(client)
        st.rerun()
else:
    uploaded_file = st.sidebar.file_uploader(
        "Analiz Edilecek Raporu Yükleyin (PDF, CSV, TXT)",
        type=["pdf", "csv", "txt"],
    )
    if uploaded_file:
        local_path = os.path.join(UPLOAD_DIR, uploaded_file.name)
        with open(local_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        with st.spinner("Dosya kaydediliyor ve Gemini'ye aktarılıyor..."):
            try:
                remote_obj = client.files.upload(file=local_path)
                meta = {
                    "file_name": uploaded_file.name,
                    "local_path": local_path,
                    "gemini_name": remote_obj.name,
                }
                save_file_meta(meta)
                st.session_state.remote_file = remote_obj
                st.session_state.uploaded_file_name = uploaded_file.name
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Dosya yükleme hatası: {e}")
                if os.path.exists(local_path):
                    os.remove(local_path)
# 5. Çalışma Modu Seçici ve !help Metni
calisma_modu = st.sidebar.radio(
    "Çalışma Modu",
    [
        "🔧 Mod B — Saha Arıza Çözümü (Varsayılan)",
        "📊 Mod A — Toplu Rapor / Pareto Analizi",
    ],
    index=0,
)

if "Mod B" in calisma_modu:
    st.sidebar.caption("Sahadaki tek bir arızayı geçmiş kayıtlarla eşleştirir ve kanıtlı çözüm/kontrol soruları üretir.")
    input_placeholder = "Sahadaki arızayı yazın (örn. Fotoswitch I 1.7 kurmuyor) veya neler yapabildiğimi görmek için !help yazın..."
else:
    st.sidebar.caption("Yüklenen tüm raporu tarar; boş iş emirlerini eler, Pareto (80/20) ve kronik arıza raporu çıkarır.")
    input_placeholder = "Toplu analiz komutu yazın (örn. Pareto analizi çıkar) veya neler yapabildiğimi görmek için !help yazın..."

HELP_TEXT = """### 🤖 Otomasyon RAG Chatbot — Neler Yapabilirim?

Geçmiş bakım ve arıza raporlarını (PDF, CSV, TXT) tarayarak kanıta dayalı arıza teşhisi ve kök neden analizi yaparım:

* **🔧 Mod B — Saha Arıza Çözümü:** Sahada yaşadığınız arızayı (ekipman, semptom veya hata kodu) yazdığınızda yalnızca ilgili geçmiş kayıtları bulur, önceki müdahalelerin geçici/kalıcı durumunu çıkarır ve saha kontrol adımları sunarım.
* **📊 Mod A — Toplu Rapor / Pareto Analizi:** Yüklediğiniz raporun tamamını tarar; boş veya sadece *"yapıldı/tamamlandı"* yazan iş emirlerini ayıklar, duruşların %80'ini oluşturan kritik kümeleri (Pareto) ve kronik arızaları (*Bad Actor*) listelerim.
* **🔍 5 Whys & 6M Fishbone:** Arızaları teknik ve süreçsel olarak iki katmanda derinleştirir, Makine/Metot/Ölçüm/İnsan/Malzeme/Ortam başlıklarında sınıflandırırım.
* **🛡️ Sıfır Halüsinasyon & Zorunlu Kaynak:** Raporda olmayan hiçbir tamir önerisini uydurmam; her bulgunun altına sayfa, arıza no ve birebir alıntı eklerim.
* **⭐ +1 Geri Bildirim Önceliklendirme:** İşinize yarayan çözümlerin altındaki **👍 (+1)** butonuna bastığınızda o çözümü gelecek aramalarda üst sırada önceliklendiririm.

**Örnek kullanım:**
> *"Fotoswitch I 1.7 kurmuyor, geçmişte nasıl çözülmüş?"* veya *"Raporun Pareto ve kronik arıza analizini çıkar."*

Şimdi doğrudan arızanızı veya analiz isteğinizi yazarak devam edebilirsiniz."""

# Yan menüde onaylı çözüm skorlarını göster
feedback_items = load_feedback_data()
if feedback_items:
    with st.sidebar.expander(f"⭐ Doğrulanmış Çözümler ({len(feedback_items)})"):
        for item in sorted(feedback_items, key=lambda x: x["score"], reverse=True)[:5]:
            st.markdown(f"**+{item['score']}** — {item['query'][:60]}")

if st.sidebar.button("🗑️ Sohbeti Temizle", use_container_width=True):
    st.session_state.messages = []
    st.rerun()


# 6. Sohbet Geçmişi ve +1 Geri Bildirim Butonu
if "messages" not in st.session_state:
    st.session_state.messages = []

for idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and not msg.get("is_help"):
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
if prompt := st.chat_input(input_placeholder):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # !help komutu yakalanırsa API'ye gitmeden anında yanıt ver ve normal akışı bozma
    if prompt.strip().lower() == "!help":
        with st.chat_message("assistant"):
            st.markdown(HELP_TEXT)
        st.session_state.messages.append({
            "role": "assistant",
            "content": HELP_TEXT,
            "is_help": True,
        })
    else:
        if "Mod B" in calisma_modu:
            mod_kurali = """
KESİN TALİMAT — SADECE MOD B (SADE VE KANITLI SAHA ÇÖZÜM MODU):
1. Profildeki uzun rapor, 6M Fishbone, Pareto ve çok katmanlı 5 Whys şablonlarını DEVRE DIŞI BIRAK. Sadece bu talimattaki kısa formatı uygula.
2. Giriş/kapanış cümlesi, genel yorum veya sorulmayan ekipmanlardan bahis KESİNLİKLE YASAKTIR.
3. Dokümanda doğrudan geçmeyen hiçbir tamir adımı, parça değişimi veya ayar önerisi UYDURMA.
4. En fazla 5 çözüm adımı yaz; her adım maksimum 1-2 kısa cümle olsun ve tekrar eden kayıtları tek maddede birleştir.
5. Öncelik sırası: (a) +1 geri bildirim skoru olan doğrulanmış çözümler, (b) geçmişte kalıcı çözüm sağlamış kayıtlar, (c) geçici müdahaleler (mutlaka 'Geçici' uyarısıyla).

YANIT FORMATI (SADECE BU 2 BAŞLIĞI KULLAN):

**1. Kanıtlı Çözüm Adımları**
Her adımı şu şablonda ver:
1. **[Kısa ve net işlem]** *(Kalıcı / Geçici / +1 Onaylı)* — Tek cümlelik uygulama detayı.
   > Kaynak: [Sayfa X | Arıza No: Y | Tarih: Z] — "rapordan en fazla 15 kelimelik birebir alıntı"

*(Eğer dokümanda bu arızayla eşleşen kayıt yoksa yalnızca: "Yüklenen raporda bu arızaya ait doğrulanmış kayıt bulunmamaktadır." yaz.)*

**2. Kök Neden & Eksik Kontrol (Sadece Gerekirse)**
* **Muhtemel Kök Neden:** [Kayıt Kanıtı] veya [Varsayım] etiketiyle tek satırlık özet.
* **[Saha Doğrulama Sorusu]:** Rapordaki bilginin yetmediği noktada en fazla 2-3 kısa kontrol sorusu.
"""
            user_payload = f"[AKTİF MOD: MOD B — SADE VE KANITLI ÇÖZÜM]\nArıza: {prompt}"
        else:
            mod_kurali = """
KESİN TALİMAT — SADECE MOD A (TOPLU RAPOR VE PARETO ANALİZİ) ÇALIŞTIR:
1. Profildeki otomatik mod seçimini devre dışı bırak; SADECE Mod A kurallarını uygula.
2. Boş veya yalnızca 'yapıldı/tamamlandı' yazan anlamsız iş emirlerini analizden hariç tut ve Veri Özeti bölümünde sayısını/oranını raporla.
3. Yalnızca İnsan-Okur Türkçe rapor üret (JSON kesinlikle üretme); her bulgunun ve kümenin altına birebir kaynak alıntısı ekle.
4. Raporu şu 5 başlıkta sun: Veri Özeti ve Güvenilirlik, Pareto (80/20) ve Kronik Arıza Tablosu, Öncelikli Kümeler İçin 5 Whys & 6M Fishbone, Geçmiş Aksiyonların Etkinlik Karnesi, Saha Doğrulama Soruları.
"""
            user_payload = f"[AKTİF MOD: MOD A — TOPLU RAPOR ANALİZİ]\nKullanıcı İsteği: {prompt}"

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

            fallback_models = list(dict.fromkeys([model_name] + ACTIVE_FALLBACK_MODELS))
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
