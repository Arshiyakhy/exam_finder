from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, ConfigDict
from jose import JWTError, jwt
from passlib.context import CryptContext

from sqlalchemy import create_engine, Column, Integer, String, Boolean, select
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# ======================================================
# DATABASE SETUP
# ======================================================
DATABASE_URL = "sqlite:///./exams.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ======================================================
# AUTH / TOKEN SETTINGS
# ======================================================
SECRET_KEY = "CHANGE_ME_TO_A_LONG_RANDOM_SECRET"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ======================================================
# DATABASE MODELS
# ======================================================
class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)


Base.metadata.create_all(bind=engine)


# ======================================================
# PYDANTIC SCHEMAS (Pydantic v2)
# ======================================================
class StudentCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


class StudentOut(BaseModel):
    id: int
    name: str
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ======================================================
# HELPER FUNCTIONS
# ======================================================
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(*, subject: str, expires_minutes: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_student_by_email(db: Session, email: str) -> Optional[Student]:
    return db.execute(
        select(Student).where(Student.email == email)
    ).scalar_one_or_none()


def get_current_student(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Student:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    student = get_student_by_email(db, email=email)
    if student is None:
        raise credentials_exception

    return student


# ======================================================
# FASTAPI APP
# ======================================================
app = FastAPI(title="Student Exam Management System")


@app.get("/")
def read_root():
    return {"message": "Welcome to the Student Exam Management System"}


# ------------------ AUTH ROUTES ------------------
@app.post("/auth/register", response_model=StudentOut)
def register(
    payload: StudentCreate,
    db: Session = Depends(get_db),
):
    existing = get_student_by_email(db, email=payload.email)
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Email already registered",
        )

    new_student = Student(
        name=payload.name,
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
    )

    db.add(new_student)
    db.commit()
    db.refresh(new_student)

    return new_student


@app.post("/auth/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    student = get_student_by_email(db, email=form_data.username)

    if not student or not verify_password(
        form_data.password, student.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        subject=student.email,
        expires_minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
    )

    return {"access_token": access_token, "token_type": "bearer"}


# ------------------ PROTECTED ROUTES ------------------
@app.get("/me", response_model=StudentOut)
def get_current_student_info(
    current_student: Student = Depends(get_current_student),
):
    return current_student


@app.get("/me/exams")
def my_exams(
    term: str = "2026W",
    current_student: Student = Depends(get_current_student),
):
    # Temporary dummy data
    exams = [
        {
            "course": "Math 101",
            "term": term,
            "date": "2026-12-15",
            "grade": "A",
        },
        {
            "course": "History 201",
            "term": term,
            "date": "2026-12-18",
            "grade": "B+",
        },
    ]

    return {
        "student_id": current_student.id,
        "term": term,
        "exams": exams,
    }
