import json
import os
import re
import time
from pathlib import Path

import streamlit as st
import yaml
from google import genai
from google.genai import types

# ==============================================================================
# 1. TEMEL YAPILANDIRMA VE SABİTLER (CARBON & COBALT PULSE)
# ==============================================================================
st.set_page_config(
    page_title="Otomasyon RAG — Saha & Kök Neden Asistanı",
    page_icon="⚡",
    layout="wide",
)

UPLOAD_DIR = "saved_docs"
META_FILE = os.path.join(UPLOAD_DIR, "active_files_meta.json")
FEEDBACK_FILE = os.path.join(UPLOAD_DIR, "feedback_scores.json")
PROFILE_CANDIDATES = [
    "core_rca_profile.yml",
    "otomasyon_rag_profili.yml",
    "3_asitleme_kok_neden_analizi_profili.yml",
]

os.makedirs(UPLOAD_DIR, exist_ok=True)

CARBON_COBALT_CSS = """
<style>
    .stApp {
        background: radial-gradient(circle at top right, rgba(59, 130, 246, 0.08), transparent 42%), #0B1120;
        color: #E2E8F0;
    }
    [data-testid="stSidebar"] {
        background-color: #162032;
        border-right: 1px solid rgba(148, 163, 184, 0.16);
    }
    .cobalt-banner {
        background: linear-gradient(135deg, #162032 0%, #0F172A 100%);
        border: 1px solid rgba(59, 130, 246, 0.35);
        border-left: 4px solid #3B82F6;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 18px;
    }
    .cobalt-title {
        font-size: 1.45rem;
        font-weight: 700;
        color: #F8FAFC;
        margin: 0 0 4px 0;
        letter-spacing: -0.01em;
    }
    .cobalt-sub {
        font-size: 0.9rem;
        color: #94A3B8;
        margin: 0;
    }
    .cobalt-kpi {
        background-color: #162032;
        border: 1px solid rgba(148, 163, 184, 0.16);
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 14px;
    }
    .cobalt-kpi-label {
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #94A3B8;
        display: block;
    }
    .cobalt-kpi-val {
        font-size: 1.05rem;
        font-weight: 700;
        color: #60A5FA;
    }
    [data-testid="stChatMessage"] {
        background-color: rgba(22, 32, 50, 0.72);
        border: 1px solid rgba(148, 163, 184, 0.14);
        border-radius: 10px;
        padding: 10px 14px;
        margin-bottom: 10px;
    }
    [data-testid="stChatMessage"] blockquote {
        border-left: 3px solid #3B82F6;
        background-color: rgba(59, 130, 246, 0.08);
        padding: 6px 12px;
        border-radius: 0 6px 6px 0;
        color: #CBD5E1;
        margin: 6px 0;
    }
    .stButton > button {
        border-radius: 7px;
        border: 1px solid rgba(59, 130, 246, 0.35);
        transition: all 0.15s ease;
    }
    .stButton > button:hover {
        border-color: #60A5FA;
    }
</style>
"""

HELP_TEXT = """### ⚡ Otomasyon RAG Asistanı — Neler Yapabilirim?

Bakım ve arıza kayıtlarını (PDF, CSV, TXT, XLSX) tarayarak kanıta dayalı arıza teşhisi ve kök neden analizi üretirim:

* **🔧 Mod B — Sade ve Kanıtlı Saha Çözümü (Varsayılan):** Sahadaki tek bir arızayı (ekipman, semptom veya hata kodu) geçmiş kayıtlarla eşleştirir; en fazla 5 kısa çözüm adımı ve altında birebir kaynak alıntısı verir.
* **📊 Mod A — Toplu Rapor / Pareto Analizi:** Yüklenen dokümanları tarar; boş veya *"yapıldı / ok / tamamlandı"* gibi anlamsız iş emirlerini ayıklar, Pareto (80/20) ve kronik arıza (Bad Actor) önceliklendirmesi yapar.
* **🔍 5 Neden (5 Whys) & 6M Fishbone:** Arızaları teknik ve sistemik katmanlarda derinleştirir; kanıt bitince tahmin yerine `[Saha Doğrulama Sorusu]` üretir.
* **👍 +1 Geri Bildirim:** İşe yarayan çözümleri `+1` ile işaretleyerek sonraki aramalarda üste taşırsınız (diğer kayıtların puanı düşürülmez).
* **🛡️ Sıfır Halüsinasyon:** Raporda olmayan tamir önerisi uydurmam; her bulguyu kaynak ve birebir alıntıyla desteklerim.

**Örnek Kullanım:**
* `Fotoswitch I 1.7 kurmuyor`
* `VFD aşırı sıcaklık hatası veriyor`
* `Duruş sürelerine göre Pareto ve kronik arıza analizi çıkar`
"""


# ==============================================================================
# 2. YARDIMCI FONKSİYONLAR (DOSYA, PROFİL, GERİ BİLDİRİM)
# ==============================================================================
def _safe_filename(name: str) -> str:
    base = os.path.basename(name)
    return re.sub(r"[^A-Za-z0-9._-]", "_", base)


def load_profile_text() -> tuple[str, str]:
    """Aktif YAML profil dosyasını yükler ve insan-okur sistem talimatına dönüştürür."""
    for candidate in PROFILE_CANDIDATES:
        p = Path(candidate)
        if p.exists() and p.is_file():
            raw = p.read_text(encoding="utf-8")
            try:
                parsed = yaml.safe_load(raw)
                formatted = yaml.dump(parsed, allow_unicode=True, sort_keys=False)
                return formatted, candidate
            except Exception:
                return raw, candidate
    fallback = (
        "Endüstriyel bakım ve otomasyon arıza kayıtları için sıfır halüsinasyon ve zorunlu "
        "kaynak alıntısı ilkesiyle çalışan kök neden analizi asistanısın."
    )
    return fallback, "varsayilan_profil"


def load_meta_list() -> list[dict]:
    if not os.path.exists(META_FILE):
        return []
    try:
        with open(META_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict) and item.get("file_name")]
    except Exception:
        pass
    return []


def save_meta_list(meta_list: list[dict]) -> None:
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta_list, f, ensure_ascii=False, indent=2)


def load_feedback_scores() -> dict[str, int]:
    if not os.path.exists(FEEDBACK_FILE):
        return {}
    try:
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): int(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def add_plus_one_feedback(key: str, note: str) -> int:
    """Yalnızca seçilen çözüme +1 puan ekler; diğer kayıtları değiştirmez."""
    scores = load_feedback_scores()
    scores[key] = scores.get(key, 0) + 1
    with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2)

    approved_list = st.session_state.get("plus_one_solutions", [])
    approved_list.append({"key": key, "note": note, "score": scores[key]})
    st.session_state.plus_one_solutions = approved_list[-20:]
    return scores[key]


def get_api_key() -> str | None:
    try:
        if "GEMINI_API_KEY" in st.secrets and st.secrets["GEMINI_API_KEY"]:
            return str(st.secrets["GEMINI_API_KEY"]).strip()
    except Exception:
        pass
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    return env_key or None


def _upload_to_gemini(client: genai.Client, local_path: str, file_name: str):
    uploaded = client.files.upload(file=local_path)
    for _ in range(15):
        state = getattr(getattr(uploaded, "state", None), "name", "")
        if state != "PROCESSING":
            break
        time.sleep(0.5)
        uploaded = client.files.get(name=uploaded.name)
    return {
        "file_name": file_name,
        "local_path": local_path,
        "gemini_name": uploaded.name,
        "uploaded_at": time.time(),
    }, uploaded


def ensure_remote_files_ready(client: genai.Client) -> list:
    """Tüm kayıtlı dosyaların Gemini File API üzerinde hazır olmasını sağlar (48 saat yenilemesi dahil)."""
    if "files_meta" not in st.session_state:
        st.session_state.files_meta = load_meta_list()
    if "remote_files" not in st.session_state:
        st.session_state.remote_files = {}

    updated_meta = []
    ready_handles = []
    meta_changed = False

    for item in st.session_state.files_meta:
        fname = item["file_name"]
        lpath = item.get("local_path") or os.path.join(UPLOAD_DIR, _safe_filename(fname))
        gname = item.get("gemini_name")

        if not os.path.exists(lpath):
            meta_changed = True
            continue

        handle = st.session_state.remote_files.get(fname)
        if handle is None and gname:
            try:
                fetched = client.files.get(name=gname)
                state = getattr(getattr(fetched, "state", None), "name", "")
                if state != "FAILED":
                    handle = fetched
                    st.session_state.remote_files[fname] = handle
            except Exception:
                handle = None

        if handle is None:
            new_item, new_handle = _upload_to_gemini(client, lpath, fname)
            st.session_state.remote_files[fname] = new_handle
            updated_meta.append(new_item)
            meta_changed = True
            ready_handles.append(new_handle)
        else:
            updated_meta.append(item)
            ready_handles.append(handle)

    if meta_changed:
        st.session_state.files_meta = updated_meta
        save_meta_list(updated_meta)

    return ready_handles


def delete_single_file(client: genai.Client, file_name: str) -> None:
    """Tek bir dosyayı listeden, diskten ve Gemini File API'den kaldırır."""
    remaining_meta = []
    for item in st.session_state.get("files_meta", []):
        if item.get("file_name") == file_name:
            gname = item.get("gemini_name")
            lpath = item.get("local_path")
            if gname:
                try:
                    client.files.delete(name=gname)
                except Exception:
                    pass
            if lpath and os.path.exists(lpath):
                try:
                    os.remove(lpath)
                except Exception:
                    pass
        else:
            remaining_meta.append(item)

    st.session_state.files_meta = remaining_meta
    if "remote_files" in st.session_state:
        st.session_state.remote_files.pop(file_name, None)
    save_meta_list(remaining_meta)


def clear_all_files(client: genai.Client) -> None:
    """Aktif tüm dosyaları temizler."""
    for fname in [x.get("file_name") for x in st.session_state.get("files_meta", []) if x.get("file_name")]:
        delete_single_file(client, fname)
    st.session_state.files_meta = []
    st.session_state.remote_files = {}
    save_meta_list([])


def render_sidebar_multi_pdf(client: genai.Client) -> list:
    """Sol menüde çoklu PDF yükleme, listeleme ve tek tek silme arayüzünü çizer."""
    if "files_meta" not in st.session_state:
        st.session_state.files_meta = load_meta_list()
    if "remote_files" not in st.session_state:
        st.session_state.remote_files = {}
    if "processed_upload_sigs" not in st.session_state:
        st.session_state.processed_upload_sigs = set()

    st.sidebar.subheader("Bakım Dokümanları (Çoklu PDF)")
    uploaded_files = st.sidebar.file_uploader(
        "PDF, CSV, TXT veya XLSX dosyaları seçin",
        type=["pdf", "csv", "txt", "xlsx"],
        accept_multiple_files=True,
        key="multi_doc_uploader",
    )

    if uploaded_files:
        existing_names = {m.get("file_name") for m in st.session_state.files_meta}
        newly_added = False

        for uf in uploaded_files:
            sig = f"{uf.name}:{uf.size}"
            if uf.name in existing_names or sig in st.session_state.processed_upload_sigs:
                continue

            save_path = os.path.join(UPLOAD_DIR, _safe_filename(uf.name))
            try:
                with open(save_path, "wb") as f:
                    f.write(uf.getbuffer())

                meta_entry, handle = _upload_to_gemini(client, save_path, uf.name)
                st.session_state.files_meta.append(meta_entry)
                st.session_state.remote_files[uf.name] = handle
                st.session_state.processed_upload_sigs.add(sig)
                existing_names.add(uf.name)
                newly_added = True
            except Exception as e:
                st.sidebar.error(f"'{uf.name}' yüklenemedi: {e}")

        if newly_added:
            save_meta_list(st.session_state.files_meta)
            st.rerun()

    if st.session_state.files_meta:
        st.sidebar.caption(f"Aktif Dosya Sayısı: {len(st.session_state.files_meta)}")
        for idx, item in enumerate(list(st.session_state.files_meta)):
            fname = item["file_name"]
            col_name, col_del = st.sidebar.columns([0.82, 0.18], vertical_alignment="center")
            col_name.markdown(f"📄 `{fname}`")
            if col_del.button("🗑️", key=f"del_file_{idx}_{fname}", help=f"{fname} dosyasını kaldır"):
                delete_single_file(client, fname)
                st.session_state.processed_upload_sigs = {
                    s for s in st.session_state.processed_upload_sigs if not s.startswith(f"{fname}:")
                }
                st.rerun()

        if st.sidebar.button("Tüm Dosyaları Temizle", use_container_width=True):
            clear_all_files(client)
            st.session_state.processed_upload_sigs.clear()
            st.rerun()
    else:
        st.sidebar.info("Henüz aktif doküman yok.")

    return ensure_remote_files_ready(client)


def build_mode_payload(calisma_modu: str, prompt: str) -> tuple[str, str]:
    """Mod B (sade ve kanıtlı saha çözümü) ve Mod A kurallarını üretir."""
    plus_one_items = st.session_state.get("plus_one_solutions", [])
    plus_one_ctx = ""
    if plus_one_items:
        lines = [f"- (+1 Onaylı | {x.get('key', '')}): {x.get('note', '')}" for x in plus_one_items[-10:]]
        plus_one_ctx = (
            "\n\nSAHADA DOĞRULANMIŞ (+1) ÇÖZÜMLER (Eşleşirse 1. sırada önceliklendir):\n"
            + "\n".join(lines)
        )

    if "Mod B" in calisma_modu:
        mod_kurali = """
KESİN TALİMAT — SADECE MOD B (SADE VE KANITLI SAHA ÇÖZÜM MODU):
1. Profildeki uzun rapor, 6M Fishbone, Pareto ve çok katmanlı 5 Whys şablonlarını DEVRE DIŞI BIRAK. Sadece bu talimattaki kısa formatı uygula.
2. Giriş/kapanış cümlesi, genel yorum veya sorulmayan ekipmanlardan bahis KESİNLİKLE YASAKTIR.
3. Dokümanda doğrudan geçmeyen hiçbir tamir adımı, parça değişimi veya ayar önerisi UYDURMA.
4. En fazla 5 çözüm adımı yaz; her adım maksimum 1-2 kısa cümle olsun ve aynı çözümü veren tekrar kayıtları tek maddede birleştir.
5. Öncelik sırası: (a) +1 geri bildirim skoru olan doğrulanmış çözümler, (b) geçmişte kalıcı çözüm sağlamış kayıtlar, (c) geçici müdahaleler (mutlaka 'Geçici' uyarısıyla).
6. Birden fazla doküman bağlıysa kaynak satırında dosya adını da belirt.

YANIT FORMATI (SADECE BU 2 BAŞLIĞI KULLAN):

**1. Kanıtlı Çözüm Adımları**
Her adımı şu şablonda ver:
1. **[Kısa ve net işlem]** *(Kalıcı / Geçici / +1 Onaylı)* — Tek cümlelik uygulama detayı.
   > Kaynak: [Dosya | Sayfa X | İş Emri No: Y | Tarih: Z] — "dokümandan en fazla 15 kelimelik birebir alıntı"

*(Eğer dokümanlarda bu arızayla eşleşen kayıt yoksa yalnızca: "Yüklenen raporda bu arızaya ait doğrulanmış kayıt bulunmamaktadır." yaz.)*

**2. Kök Neden & Eksik Kontrol (Sadece Gerekirse)**
* **Muhtemel Kök Neden:** [Kayıt Kanıtı] veya [Varsayım] etiketiyle tek satırlık özet.
* **[Saha Doğrulama Sorusu]:** Rapordaki bilginin yetmediği noktada en fazla 2-3 kısa kontrol sorusu.
""" + plus_one_ctx
        user_payload = f"[AKTİF MOD: MOD B — SADE VE KANITLI ÇÖZÜM]\nArıza: {prompt}"
    else:
        mod_kurali = """
KESİN TALİMAT — MOD A (TOPLU RAPOR / PARETO ANALİZİ):
1. Boş veya yalnızca 'yapıldı / ok / tamamlandı / kontrol edildi' gibi anlamsız iş emirlerini analiz kümelerine dahil etme; sayılarını, yüzdelerini ve duruş sürelerini '1. Veri Özeti ve Güvenilirlik' bölümünde ayrıca raporla.
2. Duruş sürelerine göre Pareto (80/20) ve kronik arıza (Bad Actor) önceliklendirmesi yap; her bulgunun altına birebir kaynak alıntısı ekle.
3. JSON çıktısı üretme; yalnızca Türkçe insan-okur rapor sun.
""" + plus_one_ctx
        user_payload = f"[AKTİF MOD: MOD A — TOPLU RAPOR / PARETO ANALİZİ]\nİstek: {prompt}"

    return mod_kurali, user_payload


def ask_gemini_with_all_pdfs(
    client: genai.Client,
    model_name: str,
    system_instruction: str,
    user_payload: str,
    active_file_handles: list,
):
    """Tüm aktif PDF/dokümanları tek sorguda modele gönderir."""
    contents = []
    if active_file_handles:
        contents.extend(active_file_handles)
    contents.append(user_payload)

    return client.models.generate_content_stream(
        model=model_name,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.1,
        ),
    )


# ==============================================================================
# 3. ANA UYGULAMA AKIŞI
# ==============================================================================
st.markdown(CARBON_COBALT_CSS, unsafe_allow_html=True)

api_key = get_api_key()
if not api_key:
    st.error("Devam etmek için Streamlit Secrets veya ortam değişkenine `GEMINI_API_KEY` ekleyin.")
    st.stop()

client = genai.Client(api_key=api_key)
base_profile_text, active_profile_name = load_profile_text()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "plus_one_solutions" not in st.session_state:
    st.session_state.plus_one_solutions = []

# Sol Menü: Model, Mod Seçimi (Mod B üstte, Mod A altta) ve Çoklu PDF Yöneticisi
st.sidebar.title("⚡ Otomasyon RAG")
st.sidebar.caption(f"Profil: `{active_profile_name}`")

selected_model = st.sidebar.selectbox(
    "Model Seçimi",
    options=["gemini-2.5-flash", "gemini-2.5-pro"],
    index=0,
)

calisma_modu = st.sidebar.radio(
    "Çalışma Modu",
    [
        "🔧 Mod B — Saha Arıza Çözümü (Varsayılan)",
        "📊 Mod A — Toplu Rapor / Pareto Analizi",
    ],
    index=0,
)

if "Mod B" in calisma_modu:
    st.sidebar.caption("Sahadaki tek bir arızayı geçmiş kayıtlarla eşleştirir ve sade/kanıtlı çözüm sunar.")
    input_placeholder = "Sahadaki arızayı yazın (ör. Fotoswitch I 1.7 kurmuyor) veya !help yazın"
else:
    st.sidebar.caption("Yüklenen tüm raporları tarar; boş iş emirlerini eler, Pareto (80/20) ve kronik arıza çıkarır.")
    input_placeholder = "Toplu analiz komutu yazın (ör. Pareto ve kronik arıza analizi çıkar) veya !help yazın"

active_file_handles = render_sidebar_multi_pdf(client)

if st.sidebar.button("Sohbeti Temizle", use_container_width=True):
    st.session_state.messages = []
    st.rerun()

# Ana Ekran Başlığı ve Telemetri Özet Şeridi
st.markdown(
    """
    <div class="cobalt-banner">
        <p class="cobalt-title">⚡ Otomasyon RAG — Saha & Kök Neden Asistanı</p>
        <p class="cobalt-sub">Carbon & Cobalt Pulse Telemetri Arayüzü · Sıfır Halüsinasyon · Zorunlu Kaynak Alıntısı</p>
    </div>
    """,
    unsafe_allow_html=True,
)

active_mode_short = "MOD B (Saha Çözümü)" if "Mod B" in calisma_modu else "MOD A (Pareto / Rapor)"
active_doc_count = len(st.session_state.get("files_meta", []))
plus_one_total = sum(load_feedback_scores().values())

k1, k2, k3 = st.columns(3)
with k1:
    st.markdown(
        f'<div class="cobalt-kpi"><span class="cobalt-kpi-label">Aktif Çalışma Modu</span><span class="cobalt-kpi-val">{active_mode_short}</span></div>',
        unsafe_allow_html=True,
    )
with k2:
    st.markdown(
        f'<div class="cobalt-kpi"><span class="cobalt-kpi-label">Bağlı Doküman Sayısı</span><span class="cobalt-kpi-val">{active_doc_count} Dosya</span></div>',
        unsafe_allow_html=True,
    )
with k3:
    st.markdown(
        f'<div class="cobalt-kpi"><span class="cobalt-kpi-label">Doğrulanmış +1 Çözüm</span><span class="cobalt-kpi-val">{plus_one_total} Onay</span></div>',
        unsafe_allow_html=True,
    )

# Geçmiş Mesajları ve +1 Geri Bildirim Butonlarını Çiz
for msg_idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and not msg.get("is_help"):
            fb_key = f"msg_{msg_idx}"
            scores = load_feedback_scores()
            current_score = scores.get(fb_key, 0)
            c1, c2 = st.columns([0.22, 0.78])
            if c1.button(f"👍 +1 ({current_score})", key=f"plus1_btn_{msg_idx}"):
                snippet = " ".join(msg["content"].splitlines()[:4])[:220]
                new_score = add_plus_one_feedback(fb_key, snippet)
                st.toast(f"Çözüm +1 olarak kaydedildi (Toplam: {new_score}).")
                st.rerun()
            if current_score > 0:
                c2.caption(f"Sahada doğrulanmış çözüm (+1 skoru: {current_score})")

# Kullanıcı Girdisi ve Yanıt Üretimi
prompt = st.chat_input(input_placeholder)
if prompt:
    clean_prompt = prompt.strip()
    st.session_state.messages.append({"role": "user", "content": clean_prompt})
    with st.chat_message("user"):
        st.markdown(clean_prompt)

    if clean_prompt.lower() == "!help":
        st.session_state.messages.append({"role": "assistant", "content": HELP_TEXT, "is_help": True})
        with st.chat_message("assistant"):
            st.markdown(HELP_TEXT)
        st.stop()

    mod_kurali, user_payload = build_mode_payload(calisma_modu, clean_prompt)
    combined_system_instruction = f"{base_profile_text}\n\n{mod_kurali}"

    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_response = ""
        try:
            stream = ask_gemini_with_all_pdfs(
                client=client,
                model_name=selected_model,
                system_instruction=combined_system_instruction,
                user_payload=user_payload,
                active_file_handles=active_file_handles,
            )
            for chunk in stream:
                part = getattr(chunk, "text", "") or ""
                if part:
                    full_response += part
                    placeholder.markdown(full_response)
            if not full_response.strip():
                full_response = "Yüklenen raporda bu arızaya ait doğrulanmış kayıt bulunmamaktadır."
                placeholder.markdown(full_response)
        except Exception as e:
            full_response = f"Yanıt üretilirken hata oluştu: {e}"
            placeholder.error(full_response)

    st.session_state.messages.append({"role": "assistant", "content": full_response, "is_help": False})
    st.rerun()
