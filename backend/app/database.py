from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
# Neon puede cerrar conexiones ociosas mientras la instancia de Render duerme.
# ``pool_pre_ping`` valida la conexión antes de usarla y evita que la primera
# operación después de un periodo de inactividad falle por un socket muerto.
_engine_kwargs = {"connect_args": connect_args, "pool_pre_ping": True}
if not DATABASE_URL.startswith("sqlite"):
    # Reciclar conexiones periódicamente reduce errores tras pausas/reanudaciones
    # de la instancia sin aumentar el número de conexiones simultáneas.
    _engine_kwargs["pool_recycle"] = 300
engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
