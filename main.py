from fastapi import FastAPI, Request, Query, Body
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from collections import defaultdict
from typing import Optional
from sqlalchemy import func
import requests
import json
import urllib3
import pandas as pd  # Excel okuma için

from veritabani import Okuma, SessionLocal, init_db
from analiz_fonksiyonlar import (
    personel_karsilastirma_analizi,
    default_karakter_karsilastirma,
    hesapla_puan,
    kullanici_okuma_performansi_karsilastir,
    manuel_default_hesapla,
    BOLGE_KATSAYILARI,
)

# Bölge ortalamalarını JSON dosyasından yükle
with open("bolge_ortalamalari.json", "r", encoding="utf-8") as f:
    bolge_ortalamalari = json.load(f)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
init_db()
print("Veritabanı tabloları oluşturuldu.")

app = FastAPI()
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# BASE_API_URL = "https://........"

# ------------------ EXCEL'DEN VERİ ÇEKME ------------------
import pandas as pd

def excelden_veri_cek():
    try:
        df = pd.read_excel("readings_sahte.xlsx")
        # TARIH sütunu format dönüşümü (gerekirse)
        def tarih_donustur(t):
            try:
                # Pandas otomatik çevirir ama Türkçe için yardımcı olalım:
                # '13-Haziran-2025' gibi bir tarihi '%d-%B-%Y' ile tanır.
                # Fakat %B Türkçe için locale ister. Alternatif: elle çevirelim.
                ay_map = {
                    "Ocak": "01", "Şubat": "02", "Mart": "03", "Nisan": "04",
                    "Mayıs": "05", "Haziran": "06", "Temmuz": "07", "Ağustos": "08",
                    "Eylül": "09", "Ekim": "10", "Kasım": "11", "Aralık": "12"
                }
                if isinstance(t, str) and '-' in t:
                    parcalar = t.split('-')
                    if len(parcalar) == 3 and parcalar[1] in ay_map:
                        return f"{parcalar[2]}-{ay_map[parcalar[1]]}-{int(parcalar[0]):02d}"
                return t  # Eğer uygun formatta değilse dokunma
            except:
                return t

        if "TARIH" in df.columns:
            df["TARIH"] = df["TARIH"].apply(tarih_donustur)

        return df.to_dict(orient="records")
    except Exception as e:
        print(f"Excel okuma hatası: {e}")
        return []


# ------------------ UTILITY ------------------
class UrlRequest(BaseModel):
    api_url: str

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
                   .replace("Ü", "U")
                   .replace(" ", ""))

# ------------------ ENDPOINTLER ------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/katsayilarbolge")
def katsayilarbolge_getir():
    return JSONResponse(content=BOLGE_KATSAYILARI)

@app.get("/kullanicilar")
def kullanicilar(
    ilkTarih: Optional[str] = Query(None),
    sonTarih: Optional[str] = Query(None),
    ilce: Optional[str] = Query(None)
):
    bugun = datetime.now().strftime("%Y-%m-%d")
    # --- EXCEL'den veri çek ---
    veriler = excelden_veri_cek()
    
    # --- API ile çekmek isteyenler için, aşağıdaki satırların başındaki # işaretini kaldırabilir ---
    # params = {
    #     "ilkTarih": ilkTarih or bugun,
    #     "sonTarih": sonTarih or bugun,
    # }
    # try:
    #     response = requests.get(BASE_API_URL, params=params, verify=False)
    #     response.raise_for_status()
    #     veriler = response.json()
    # except Exception as e:
    #     return {"HATA": f"Dış API'den kullanıcı verisi alınamadı: {e}"}

    # İlçe filtresi (normalize)
    if ilce:
        ilce_norm = normalize_ilce_adi(ilce)
        veriler = [v for v in veriler if normalize_ilce_adi(v.get("ILCE", "")) == ilce_norm]

    kullanici_adlari = list({v.get("KULLANICI_ADI") for v in veriler if v.get("KULLANICI_ADI")})
    if not kullanici_adlari:
        return {"HATA": "Belirtilen kriterlere uyan kullanıcı adı bulunamadı."}
    return {"kullanicilar": sorted(kullanici_adlari)}

@app.get("/analiz")
def analiz(
    tip: str = Query(default="", description="Analiz tipi: default, karsilastirma, defter"),
    kullanici_adi: str = "",
    defter_id: Optional[str] = Query(None),
    okuma_suresi: Optional[float] = Query(None),
    ilkTarih: Optional[str] = Query(None),
    sonTarih: Optional[str] = Query(None),
    ilce: Optional[str] = Query(None),
    normal_okuma_min: int = 0,
    bolge: Optional[str] = Query(None)
):
    bugun = datetime.now().strftime("%Y-%m-%d")
    # --- EXCEL'den veri çek ---
    veriler = excelden_veri_cek()
    # --- API ile çekmek isteyenler için ---
    # params = {
    #     "ilkTarih": ilkTarih or bugun,
    #     "sonTarih": sonTarih or bugun,
    # }
    # try:
    #     response = requests.get(BASE_API_URL, params=params, verify=False)
    #     response.raise_for_status()
    #     veriler = response.json()
    # except Exception as e:
    #     return {"HATA": f"Dış API'den veri çekilemedi: {str(e)}"}

    if not veriler:
        return {"analiz_sonucu": [], "kullanicilar": []}

    # Tarih filtresi (isteğe bağlı, eğer Excel dosyan tüm tarihleri içeriyorsa)
    if ilkTarih:
        veriler = [v for v in veriler if v.get("TARIH", "") >= ilkTarih]
    if sonTarih:
        veriler = [v for v in veriler if v.get("TARIH", "") <= sonTarih]

    # İlçe filtre
    if ilce:
        ilce_norm = normalize_ilce_adi(ilce)
        veriler = [v for v in veriler if normalize_ilce_adi(v.get("ILCE", "")) == ilce_norm]

    # Min. normal okuma filtresi
    filtrelenmis_veriler = [v for v in veriler if (v.get("NORMAL_OKUMA") or 0) >= normal_okuma_min]
    gun_sayisi = len(set([v["TARIH"] for v in filtrelenmis_veriler if "TARIH" in v]))

    if tip == "default":
        if kullanici_adi:
            kullanici_verileri = [
                v for v in filtrelenmis_veriler
                if (v.get("KULLANICI_ADI") or "").lower() == kullanici_adi.lower()
            ]
            if not kullanici_verileri:
                return {"analiz_sonucu": [], "HATA": f"'{kullanici_adi}' için veri bulunamadı."}
            analiz_sonuc = default_karakter_karsilastirma(kullanici_verileri)
            return {"analiz_sonucu": analiz_sonuc}
        return {"analiz_sonucu": []}

    # Personel karşılaştırma
    analiz_sonuc = personel_karsilastirma_analizi(
        filtrelenmis_veriler, gun_sayisi, BOLGE_KATSAYILARI
    )
    analiz_sonuc.sort(key=lambda x: x["PUAN"], reverse=True)

    # Excel kullanırken kullanıcı adlarını da çekmek için:
    kullanici_listesi = sorted({v.get("KULLANICI_ADI") for v in veriler if v.get("KULLANICI_ADI")})

    return {
        "analiz_sonucu": analiz_sonuc,
        "kullanicilar": kullanici_listesi
    }

# Aşağıdaki endpointlerde büyük değişiklik yok, ister veritabanını ister Excel'i kullanabilirsin
@app.get("/filtre-alanlari")
def filtre_alanlari():
    session = SessionLocal()
    try:
        ilceler = session.query(Okuma.ilce).distinct().all()
        kullanicilar = session.query(Okuma.kullanici_adi).distinct().all()
        ilce_list = sorted(set(i[0] for i in ilceler if i[0]))
        kullanici_list = sorted(set(k[0] for k in kullanicilar if k[0]))
        return {
            "ilceler": ilce_list,
            "kullanicilar": kullanici_list,
        }
    finally:
        session.close()

@app.get("/ortalama-okuma")
def ortalama_okuma():
    session = SessionLocal()
    try:
        rows = session.query(
            Okuma.bolge,
            func.avg(Okuma.toplam_okuma),
            func.avg(Okuma.normal_okuma)
        ).group_by(Okuma.bolge).all()
        return {
            row[0]: {
                "ortalama_toplam_okuma": round(row[1] or 0, 2),
                "ortalama_normal_okuma": round(row[2] or 0, 2)
            } for row in rows if row[0]
        }
    finally:
        session.close()

class ManuelDefaultInput(BaseModel):
    defter_sayisi: int
    toplam_sure_dakika: float
    toplam_okuma: int
    normal_okuma: int

@app.post("/default-hesapla")
def default_hesapla(data: ManuelDefaultInput = Body(...)):
    sonuc = manuel_default_hesapla(
        data.defter_sayisi,
        data.toplam_sure_dakika,
        data.toplam_okuma,
        data.normal_okuma
    )
    return sonuc

@app.exception_handler(Exception)
async def all_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"message": f"Internal server error: {exc}"}
    )

@app.get("/guncelle-bolge-ortalamalari")
def guncelle_bolge_ortalamalari():
    session = SessionLocal()
    try:
        rows = session.query(
            Okuma.bolge,
            func.avg(Okuma.toplam_okuma),
            func.avg(Okuma.normal_okuma)
        ).group_by(Okuma.bolge).all()
        data = {
            row[0]: {
                "ortalama_toplam_okuma": round(row[1] or 0, 2),
                "ortalama_normal_okuma": round(row[2] or 0, 2)
            } for row in rows if row[0]
        }
        with open("bolge_ortalamalari.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {"status": "ok", "adet": len(data)}
    finally:
        session.close()

@app.get("/test-okuma-kayitlari")
def test_okuma_kayitlari():
    session = SessionLocal()
    try:
        kayitlar = session.query(Okuma).limit(5).all()
        return [
            {
                "bolge": k.bolge,
                "toplam_okuma": k.toplam_okuma,
                "normal_okuma": k.normal_okuma,
                "ad_soyad": k.ad_soyad,
                "tarih": str(k.tarih),
            }
            for k in kayitlar
        ]
    finally:
        session.close()
