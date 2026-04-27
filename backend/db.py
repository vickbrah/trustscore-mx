"""Modelos de base de datos. SQLite para MVP, Postgres en producción."""

import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Float, Boolean,
    ForeignKey, JSON, Text,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./trustscore.db")

# Render entrega DATABASE_URL en formato `postgres://...` pero SQLAlchemy 2.x
# requiere `postgresql://...` (o `postgresql+psycopg2://...`). Normalizamos.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,  # reconecta si la conexión Postgres se duerme
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    nombre = Column(String, nullable=False)
    empresa = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    consultas_gratis_restantes = Column(Integer, default=5)
    saldo_creditos = Column(Float, default=0.0)  # MXN
    stripe_customer_id = Column(String, nullable=True)
    suscripcion_activa = Column(String, nullable=True)  # "starter", "growth", "pro"
    creado = Column(DateTime, default=datetime.utcnow)

    api_keys = relationship("ApiKey", back_populates="user", cascade="all,delete")
    consultas = relationship("Consulta", back_populates="user", cascade="all,delete")


class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    key_prefix = Column(String, nullable=False)   # primeros 8 chars visibles
    key_hash = Column(String, nullable=False)     # hash del resto
    nombre = Column(String, default="default")
    creada = Column(DateTime, default=datetime.utcnow)
    ultima_usada = Column(DateTime, nullable=True)
    activa = Column(Boolean, default=True)

    user = relationship("User", back_populates="api_keys")


class Consulta(Base):
    __tablename__ = "consultas"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rfc_consultado = Column(String, index=True)
    nombre_consultado = Column(String, nullable=True)
    tier = Column(String, nullable=False)  # express|estandar|profesional|enterprise
    score = Column(Integer, nullable=True)
    categoria = Column(String, nullable=True)
    payload_completo = Column(JSON, nullable=True)
    costo_cobrado = Column(Float, default=0.0)
    costo_