from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON, ForeignKey, Boolean, event
from sqlalchemy import text as sa_text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
import sys
import logging

log = logging.getLogger(__name__)

# При запуске как .exe (PyInstaller) данные хранятся рядом с исполняемым файлом.
# При разработке — в папке data/ в корне проекта.
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_PATH = os.path.join(BASE_DIR, "data", "db.sqlite")

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)

# Включаем WAL и оптимальные прагмы при каждом подключении
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")   # ждём до 5 с при блокировке
    cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Project(Base):
    """Проект — контейнер для группы документов одного продукта."""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    product_context = Column(Text, nullable=True)       # сгенерированный или введённый вручную контекст
    context_generated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    documents = relationship("Document", back_populates="project")


class Model(Base):
    """LLM-модель, добавленная пользователем или из дефолтного конфига."""
    __tablename__ = "models"

    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    base_url = Column(String, nullable=False)
    requires_key = Column(Boolean, default=True)
    api_key = Column(Text, nullable=True)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProductGroup(Base):
    __tablename__ = "product_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    snapshots = relationship("Snapshot", back_populates="group", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    doc_type = Column(String, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    last_evaluated_at = Column(DateTime, nullable=True)
    file_path = Column(String, nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    glossary = Column(JSON, nullable=True)          # список терминов продукта, извлечённых YAKE

    instructions = relationship("Instruction", back_populates="document", cascade="all, delete-orphan")
    project = relationship("Project", back_populates="documents")


class Instruction(Base):
    __tablename__ = "instructions"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    classification = Column(String, default="non-instruction")
    page_number = Column(Integer, nullable=True)
    level = Column(Integer, nullable=True)
    section_path = Column(String, nullable=True)
    include_in_evaluation = Column(Integer, default=1)
    diff_hint = Column(Text, nullable=True)         # краткое описание изменений при замене документа

    document = relationship("Document", back_populates="instructions")
    evaluation = relationship("Evaluation", back_populates="instruction", uselist=False, cascade="all, delete-orphan")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, index=True)
    instruction_id = Column(Integer, ForeignKey("instructions.id"), nullable=False)
    criteria_results = Column(JSON, nullable=True)
    recommendations = Column(JSON, nullable=True)
    color = Column(String, nullable=True)
    evaluated_at = Column(DateTime, default=datetime.utcnow)
    model_used = Column(String, nullable=True)
    # Ложные срабатывания, выставленные пользователем вручную.
    # Формат: {"criteria": {"1.1": true, "2.3": true}, "section": false}
    # Сохраняются при повторной оценке — пользователь ставил осознанно.
    overrides = Column(JSON, nullable=True, default=dict)

    instruction = relationship("Instruction", back_populates="evaluation")


class Snapshot(Base):
    __tablename__ = "snapshots"

    id = Column(Integer, primary_key=True, index=True)
    # group_id nullable: промежуточные снимки (is_partial=True) не привязаны к группе
    group_id = Column(Integer, ForeignKey("product_groups.id"), nullable=True)
    document_id = Column(Integer, nullable=True)
    document_filename = Column(String, nullable=True)
    name = Column(String, nullable=False)
    role = Column(String, default="current")
    created_at = Column(DateTime, default=datetime.utcnow)
    data = Column(JSON, nullable=False)
    is_partial = Column(Boolean, default=False)   # промежуточный снимок (не требует группы)

    group = relationship("ProductGroup", back_populates="snapshots")


class CriteriaSet(Base):
    """Набор критериев оценки. Хранит полный Markdown-контент."""
    __tablename__ = "criteria_sets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    content = Column(Text, nullable=False)       # полный Markdown
    is_active = Column(Boolean, default=False)   # активный набор
    is_default = Column(Boolean, default=False)  # дефолтный (из criteria.md)
    created_at = Column(DateTime, default=datetime.utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _migrate_models_from_yml()
    _migrate_criteria_from_file()
    _migrate_add_project_column()
    _migrate_create_default_project()
    _migrate_add_glossary_column()
    _migrate_add_diff_hint_column()
    _migrate_snapshots_v2()


def _migrate_models_from_yml():
    """При первом запуске переносит модели из models.yml в таблицу models."""
    import yaml
    BASE = BASE_DIR
    yml_path = os.path.join(BASE, "models.yml")

    db = SessionLocal()
    try:
        if db.query(Model).count() > 0:
            return
        if not os.path.exists(yml_path):
            return
        with open(yml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        active_id = data.get("active_model", "")
        for m in data.get("models", []):
            db.add(Model(
                model_id=m["id"],
                name=m["name"],
                provider=m["provider"],
                base_url=m["base_url"],
                requires_key=m.get("requires_key", False),
                is_active=(m["id"] == active_id),
            ))
        db.commit()
    finally:
        db.close()


def _find_criteria_file() -> str:
    """Ищет criteria.md: рядом с exe → _MEIPASS → корень проекта."""
    import sys
    if getattr(sys, "frozen", False):
        candidate = os.path.join(os.path.dirname(sys.executable), "criteria.md")
        if os.path.exists(candidate):
            return candidate
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidate = os.path.join(meipass, "criteria.md")
            if os.path.exists(candidate):
                return candidate
    return os.path.join(BASE_DIR, "criteria.md")


def _migrate_criteria_from_file():
    """При первом запуске загружает criteria.md в таблицу criteria_sets."""
    db = SessionLocal()
    try:
        if db.query(CriteriaSet).count() > 0:
            return
        path = _find_criteria_file()
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        db.add(CriteriaSet(
            name="Дефолтные критерии",
            content=content,
            is_active=True,
            is_default=True,
        ))
        db.commit()
    finally:
        db.close()


def _migrate_add_project_column():
    """Добавляет project_id в таблицу documents, если колонка ещё не существует."""
    with engine.connect() as conn:
        columns = [row[1] for row in conn.execute(
            __import__("sqlalchemy").text("PRAGMA table_info(documents)")
        )]
        if "project_id" not in columns:
            conn.execute(__import__("sqlalchemy").text(
                "ALTER TABLE documents ADD COLUMN project_id INTEGER REFERENCES projects(id)"
            ))
            conn.commit()
            log.info("Миграция: добавлена колонка project_id в documents")


def _migrate_create_default_project():
    """
    При первом появлении таблицы projects создаёт проект «По умолчанию»
    и переносит все существующие документы без проекта в него.
    """
    db = SessionLocal()
    try:
        if db.query(Project).count() > 0:
            return  # проекты уже существуют

        # Создаём проект по умолчанию только если есть документы без проекта
        orphan_docs = db.query(Document).filter(Document.project_id == None).all()
        if not orphan_docs:
            return

        default_project = Project(name="По умолчанию")
        db.add(default_project)
        db.flush()

        for doc in orphan_docs:
            doc.project_id = default_project.id

        db.commit()
        log.info(f"Миграция: создан проект «По умолчанию», перенесено документов: {len(orphan_docs)}")
    finally:
        db.close()


def _migrate_add_glossary_column():
    """Добавляет колонку glossary в таблицу documents, если её ещё нет."""
    with engine.connect() as conn:
        columns = [row[1] for row in conn.execute(
            __import__("sqlalchemy").text("PRAGMA table_info(documents)")
        )]
        if "glossary" not in columns:
            conn.execute(__import__("sqlalchemy").text(
                "ALTER TABLE documents ADD COLUMN glossary JSON"
            ))
            conn.commit()
            log.info("Миграция: добавлена колонка glossary в documents")


def _migrate_add_diff_hint_column():
    """Добавляет колонку diff_hint в таблицу instructions, если её ещё нет."""
    with engine.connect() as conn:
        columns = [row[1] for row in conn.execute(
            __import__("sqlalchemy").text("PRAGMA table_info(instructions)")
        )]
        if "diff_hint" not in columns:
            conn.execute(__import__("sqlalchemy").text(
                "ALTER TABLE instructions ADD COLUMN diff_hint TEXT"
            ))
            conn.commit()
            log.info("Миграция: добавлена колонка diff_hint в instructions")


def _migrate_snapshots_v2():
    """
    Обновляет таблицу snapshots:
    - group_id становится nullable (промежуточные снимки не требуют продуктовой группы)
    - добавляет колонку is_partial BOOLEAN DEFAULT 0
    Пересоздаёт таблицу, т.к. SQLite не поддерживает ALTER COLUMN.
    """
    with engine.connect() as conn:
        cols_info = list(conn.execute(sa_text("PRAGMA table_info(snapshots)")))
        col_names = [row[1] for row in cols_info]
        col_notnull = {row[1]: row[3] for row in cols_info}  # name → notnull (1 = NOT NULL)

        needs_migration = (
            "is_partial" not in col_names
            or col_notnull.get("group_id", 0) == 1  # group_id был NOT NULL
        )
        if not needs_migration:
            return

        # Создаём новую таблицу с нужной схемой
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS snapshots_new (
                id       INTEGER NOT NULL PRIMARY KEY,
                group_id INTEGER REFERENCES product_groups(id),
                document_id       INTEGER,
                document_filename VARCHAR,
                name     VARCHAR NOT NULL,
                role     VARCHAR,
                created_at DATETIME,
                data     JSON NOT NULL,
                is_partial BOOLEAN DEFAULT 0
            )
        """))

        # Копируем данные — is_partial добавляем как 0 если колонки ещё не было
        if "is_partial" in col_names:
            conn.execute(sa_text(
                "INSERT INTO snapshots_new "
                "SELECT id, group_id, document_id, document_filename, "
                "name, role, created_at, data, is_partial FROM snapshots"
            ))
        else:
            conn.execute(sa_text(
                "INSERT INTO snapshots_new "
                "SELECT id, group_id, document_id, document_filename, "
                "name, role, created_at, data, 0 FROM snapshots"
            ))

        conn.execute(sa_text("DROP TABLE snapshots"))
        conn.execute(sa_text("ALTER TABLE snapshots_new RENAME TO snapshots"))
        conn.commit()
        log.info("Миграция: snapshots — group_id nullable, добавлена колонка is_partial")


def get_active_criteria_content() -> str:
    """Возвращает Markdown активного набора критериев."""
    db = SessionLocal()
    try:
        active = db.query(CriteriaSet).filter(CriteriaSet.is_active == True).first()
        if active:
            return active.content
        # Fallback — читаем файл напрямую
        path = _find_criteria_file()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return ""
    finally:
        db.close()
