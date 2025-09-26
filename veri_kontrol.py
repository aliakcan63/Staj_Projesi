# hızlıca kontrol etmek için terminalde Python aç ve:
from veritabani import SessionLocal, Okuma
session = SessionLocal()
kullanicilar = session.query(Okuma.kullanici_adi).distinct().all()
print([k[0] for k in kullanicilar if k[0]])
session.close()
