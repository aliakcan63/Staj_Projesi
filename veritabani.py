from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./database.db"  # ya da PostgreSQL, MySQL, vs.

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Okuma(Base):
    __tablename__ = "okumalar"

    id = Column(Integer, primary_key=True, index=True)
    ad_soyad = Column(String, index=True)
    tarih = Column(DateTime)
    ilk_okuma = Column(String)
    son_okuma = Column(String)
    normal_okuma = Column(Integer)
    diger = Column(Integer)
    toplam_okuma = Column(Integer)
    defter_id = Column(String)
    ilce = Column(String, index=True)
    bolge = Column(String, index=True)
    kullanici_adi = Column(String, index=True)

def init_db():
    Base.metadata.create_all(bind=engine)
