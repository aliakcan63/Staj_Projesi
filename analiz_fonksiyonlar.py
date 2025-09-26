import json
import math
from typing import List, Dict, Any
from datetime import datetime
from collections import defaultdict
from dateutil.parser import parse

# --- Normalizasyon Fonksiyonları ---
def normalize_ilce_adi(ilce_adi):
    if not ilce_adi:
        return ""
    return (ilce_adi.strip()
            .upper()
            .replace("İ", "I")
            .replace("Ç", "C")
            .replace("Ğ", "G")
            .replace("Ö", "O")
            .replace("Ş", "S")
            .replace("Ü", "U"))

def normalize_bolge_adi(bolge_adi):
    if not bolge_adi:
        return ""
    return (bolge_adi.strip()
            .upper()
            .replace("İ", "I")
            .replace("Ç", "C")
            .replace("Ğ", "G")
            .replace("Ö", "O")
            .replace("Ş", "S")
            .replace("Ü", "U"))

# --- Filtreleme Fonksiyonu ---
def filtrele_veri_ilce_veya_bolge(veriler, ilce=None, bolge=None):
    if ilce:
        ilce_norm = normalize_ilce_adi(ilce)
        veriler = [v for v in veriler if normalize_ilce_adi(v.get("ILCE", "")) == ilce_norm]
    if bolge:
        norm_bolge = normalize_bolge_adi(bolge)
        veriler = [v for v in veriler if v.get("BOLGE") and normalize_bolge_adi(v.get("BOLGE")) == norm_bolge]
    return veriler

# --- Düzenlilik Puanı Hesabı ---
def duzenlilik_puani(okuma_tarihleri, analiz_baslangic, analiz_bitis):
    import pandas as pd
    df = pd.DataFrame({'tarih': pd.to_datetime(okuma_tarihleri)})
    aktif_gunler = df['tarih'].dt.date.nunique()
    toplam_gun = (analiz_bitis - analiz_baslangic).days + 1
    duzenlilik = aktif_gunler / toplam_gun
    return min(duzenlilik, 1.0)

# --- Bölge Katsayılarını Yükle (JSON'dan) ---
try:
    with open("BOLGE_KATSAYI_DETAYLI.json", "r", encoding="utf-8") as f:
        katsayi_data = json.load(f)
        BOLGE_KATSAYILARI = {normalize_bolge_adi(bolge): veriler["katsayi"] for bolge, veriler in katsayi_data.items()}
except FileNotFoundError:
    BOLGE_KATSAYILARI = {}

def get_bolge_katsayi(bolge_adi):
    return BOLGE_KATSAYILARI.get(normalize_bolge_adi(bolge_adi), 1.0)

# --- Puan Hesabı ---
def hesapla_puan(
    normal_okuma: float,
    toplam_okuma: float,
    bolge_ortalama: float,
    bolge_katsayi: float = 1.0,
    aktif_gun: int = None,
    toplam_gun: int = None,
    alpha=0.65,
    beta=0.25,
    gamma=0.10
) -> dict:
    if toplam_okuma == 0 or bolge_ortalama == 0:
        puan = 0.0
    else:
        zorluk_carpani = math.log1p(bolge_katsayi)
        beklenen = bolge_ortalama * zorluk_carpani
        oran = toplam_okuma / beklenen if beklenen > 0 else 0
        verimlilik_orani = min(oran ** 0.5, 1.0)
        dogruluk_orani = normal_okuma / toplam_okuma if toplam_okuma > 0 else 0.0
        if aktif_gun is not None and toplam_gun:
            duzenlilik_orani = aktif_gun / toplam_gun
            duzenlilik_orani = min(duzenlilik_orani, 1.0)
        else:
            duzenlilik_orani = 0.5
        normalize_puan = (
            alpha * verimlilik_orani +
            beta * dogruluk_orani +
            gamma * duzenlilik_orani
        ) / (alpha + beta + gamma)
        puan = normalize_puan * 100
        puan = min(puan, 100.0)
    # Kategori ve geri bildirimler
    if puan >= 90:
        kategori = "Mükemmel"
        arti = "Verimlilik ve doğruluk çok yüksek."
        eksik = "-"
    elif puan >= 75:
        kategori = "Çok İyi"
        arti = "İyi iş çıkarıyor."
        eksik = "Performans sürdürülebilir olmalı."
    elif puan >= 60:
        kategori = "İyi"
        arti = "Ortalama üzerinde performans."
        eksik = "Daha fazla verimlilik sağlanabilir."
    elif puan >= 40:
        kategori = "Orta"
        arti = "Gelişmeye açık."
        eksik = "Verimlilik ve doğruluk artırılabilir."
    else:
        kategori = "Geliştirmeli"
        arti = "Gelişmeye açık."
        eksik = "Performans düşük, geliştirme gerekli."
    return {
        "PUAN": round(puan, 2),
        "KATEGORI": kategori,
        "ARTI_YONLER": arti,
        "EKSIK_YONLER": eksik
    }

# --- Personel Karşılaştırma Analizi ---
def personel_karsilastirma_analizi(
    veriler: list,
    gun_sayisi: int,
    bolge_ortalamalari: dict
) -> list:
    grouped = defaultdict(list)
    for v in veriler:
        grouped[v.get("AD_SOYAD", "")].append(v)
    max_okuma = 1
    for kayitlar in grouped.values():
        toplam = sum(k.get("TOPLAM_OKUMA", 0) for k in kayitlar)
        if toplam > max_okuma:
            max_okuma = toplam
    analiz_sonuc = []
    for ad_soyad, kayitlar in grouped.items():
        toplam_okuma = sum(k.get("TOPLAM_OKUMA", 0) for k in kayitlar)
        toplam_normal = sum(k.get("NORMAL_OKUMA", 0) for k in kayitlar)
        bolge = kayitlar[0].get("BOLGE", "")
        bolge_katsayi = get_bolge_katsayi(bolge)
        bolge_ort_deger = bolge_ortalamalari.get(bolge, 1)
        if isinstance(bolge_ort_deger, dict):
            bolge_ortalama = bolge_ort_deger.get("ortalama_toplam_okuma", 1)
        else:
            bolge_ortalama = bolge_ort_deger
        try:
            bolge_ortalama = float(bolge_ortalama)
        except Exception:
            bolge_ortalama = 1
        okuma_tarihleri = [k.get("TARIH") for k in kayitlar if k.get("TARIH")]
        if okuma_tarihleri:
            tarih_objs = [parse(t) for t in okuma_tarihleri]
            analiz_baslangic = min(tarih_objs).date()
            analiz_bitis = max(tarih_objs).date()
            duzenlilik = duzenlilik_puani(okuma_tarihleri, analiz_baslangic, analiz_bitis)
            aktif_gun = len(set(okuma_tarihleri))
            toplam_gun = (analiz_bitis - analiz_baslangic).days + 1
        else:
            duzenlilik = 0
            aktif_gun = 0
            toplam_gun = 1
        # Temel puan
        puan_dict = hesapla_puan(
            normal_okuma=toplam_normal,
            toplam_okuma=toplam_okuma,
            bolge_ortalama=bolge_ortalama,
            bolge_katsayi=bolge_katsayi,
            aktif_gun=aktif_gun,
            toplam_gun=toplam_gun,
        )
        puan = puan_dict["PUAN"]
        norm_factor = math.log1p(toplam_okuma) / math.log1p(max_okuma) if max_okuma > 0 else 0
        final_puan = puan * norm_factor
        GENEL_AGIRLIK = 1.0
        genel_puan = final_puan * GENEL_AGIRLIK
        analiz_sonuc.append({
            "KULLANICI_ADI": kayitlar[0].get("KULLANICI_ADI") or "-",
            "AD_SOYAD": ad_soyad,
            "BOLGE": bolge,
            "TOPLAM_OKUMA": toplam_okuma,
            "NORMAL_OKUMA": toplam_normal,
            "BOLGE_KATSAYI": bolge_katsayi,
            "PUAN": round(final_puan, 2),
            "KATEGORI": puan_dict["KATEGORI"],
            "ARTI_YONLER": puan_dict["ARTI_YONLER"],
            "EKSIK_YONLER": puan_dict["EKSIK_YONLER"],
            "DUZENLILIK_PUANI": round(duzenlilik * 100, 2),
            "GENEL_PUAN": round(genel_puan, 2),
            "AKTIF_GUN": aktif_gun,
            "PUAN_AÇIKLAMA": f"Puan log(norm) ile çarpıldı. (Norm: {round(norm_factor, 2)})"
        })
    return analiz_sonuc

def default_karakter_karsilastirma(kullanici_verileri):
    if not kullanici_verileri:
        return {}
    toplam_okuma = sum(v.get("TOPLAM_OKUMA", 0) for v in kullanici_verileri)
    toplam_normal = sum(v.get("NORMAL_OKUMA", 0) for v in kullanici_verileri)
    bolge = kullanici_verileri[0].get("BOLGE", "")
    bolge_katsayi = get_bolge_katsayi(bolge)
    okuma_tarihleri = [v.get("TARIH") for v in kullanici_verileri if v.get("TARIH")]
    if okuma_tarihleri:
        tarih_objs = [parse(t) for t in okuma_tarihleri]
        analiz_baslangic = min(tarih_objs).date()
        analiz_bitis = max(tarih_objs).date()
        aktif_gun = len(set(okuma_tarihleri))
        toplam_gun = (analiz_bitis - analiz_baslangic).days + 1
        duzenlilik = duzenlilik_puani(okuma_tarihleri, analiz_baslangic, analiz_bitis)
    else:
        aktif_gun = 0
        toplam_gun = 1
        duzenlilik = 0
    # Ortalama bul: bolge_ortalamalari'ndan ya da sabit değer
    try:
        with open("bolge_ortalamalari.json", "r", encoding="utf-8") as f:
            bolge_ortalamalari = json.load(f)
    except Exception:
        bolge_ortalamalari = {}
    bolge_ort_deger = bolge_ortalamalari.get(bolge, 1)
    if isinstance(bolge_ort_deger, dict):
        bolge_ortalama = bolge_ort_deger.get("ortalama_toplam_okuma", 1)
    else:
        bolge_ortalama = bolge_ort_deger
    try:
        bolge_ortalama = float(bolge_ortalama)
    except Exception:
        bolge_ortalama = 1
    puan_dict = hesapla_puan(
        normal_okuma=toplam_normal,
        toplam_okuma=toplam_okuma,
        bolge_ortalama=bolge_ortalama,
        bolge_katsayi=bolge_katsayi,
        aktif_gun=aktif_gun,
        toplam_gun=toplam_gun,
    )
    return {
        "KULLANICI_ADI": kullanici_verileri[0].get("KULLANICI_ADI", "-"),
        "AD_SOYAD": kullanici_verileri[0].get("AD_SOYAD", "-"),
        "BOLGE": bolge,
        "TOPLAM_OKUMA": toplam_okuma,
        "NORMAL_OKUMA": toplam_normal,
        "BOLGE_KATSAYI": bolge_katsayi,
        "PUAN": puan_dict["PUAN"],
        "KATEGORI": puan_dict["KATEGORI"],
        "ARTI_YONLER": puan_dict["ARTI_YONLER"],
        "EKSIK_YONLER": puan_dict["EKSIK_YONLER"],
        "DUZENLILIK_PUANI": round(duzenlilik * 100, 2),
        "GENEL_PUAN": puan_dict["PUAN"],
        "AKTIF_GUN": aktif_gun,
        "PUAN_AÇIKLAMA": "",
    }

def kullanici_okuma_performansi_karsilastir(defter_id: str, okuma_suresi: float) -> List[Dict[str, Any]]:
    # Dummy örnek; gerçekte sorgu yazılacak
    return [
        {
            "AD_SOYAD": "Ali Akcan",
            "KULLANICI_ADI": "ali_a",
            "PUAN": 85.5,
            "KATEGORI": "İyi",
            "ARTI_YONLER": "Hızlı ve doğru okuma",
            "EKSIK_YONLER": "Daha fazla örnek incelenmeli",
            "TOPLAM_OKUMA": 120
        },
        {
            "AD_SOYAD": "Mehmet Yılmaz",
            "KULLANICI_ADI": "mehmet_y",
            "PUAN": 75.0,
            "KATEGORI": "Orta",
            "ARTI_YONLER": "Düzenli takip",
            "EKSIK_YONLER": "Hız artırılabilir",
            "TOPLAM_OKUMA": 110
        },
    ]

def manuel_default_hesapla(defter_sayisi, toplam_sure_dakika, toplam_okuma, normal_okuma):
    if defter_sayisi == 0 or toplam_sure_dakika == 0:
        return {
            "PUAN": 0.0,
            "KATEGORI": "Geçersiz",
            "MESAJ": "Defter sayısı veya süre 0 olamaz."
        }
    okuma_hizi = toplam_okuma / toplam_sure_dakika  # okuma/dk
    dogruluk = (normal_okuma / toplam_okuma) if toplam_okuma > 0 else 0
    ham_puan = min(okuma_hizi * 30, 100)  # 30 dk üzerinden puanlama
    puan = ham_puan * (0.7 * dogruluk + 0.3)
    kategori = "Mükemmel" if puan >= 90 else "İyi" if puan >= 75 else "Orta" if puan >= 60 else "Düşük"
    return {
        "PUAN": round(puan, 2),
        "KATEGORI": kategori,
        "OKUMA_HIZI": round(okuma_hizi, 2),
        "DOĞRULUK": round(dogruluk, 2),
        "DEFTER": defter_sayisi,
        "TOPLAM_OKUMA": toplam_okuma,
        "NORMAL_OKUMA": normal_okuma,
    }

# ---- Son ----
