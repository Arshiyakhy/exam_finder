from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from sqlalchemy import (create_engine,
                        Column,
                        Integer,
                        String,
                        ForeignKey,
                        UniqueConstraint,
                        select,
                        Boolean,)
from sqlalchemy.orm import declarative_base, Session

# Database setup
DATABASE_URL = "sqlite:///./school.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Base = declarative_base()

# Table definitions


class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)


class Course(Base):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, default="")
    credits = Column(Integer, default=3)


class Enrollment(Base):
    __tablename__ = "enrollments"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="uq_student_course"),
    )


Base.metadata.create_all(bind=engine)
# Pydantic schemas


class StudentCreate(BaseModel):
    name: str


class StudentOut(BaseModel):
    id: int
    name: str


class CourseCreate(BaseModel):
    title: str


class CourseOut(BaseModel):
    id: int
    title: str


class EnrollRequest(BaseModel):
    student_id: int
    course_id: int


class StudentWithCourses(BaseModel):
    id: int
    name: str
    courses: List[CourseOut]


# FastAPI app
app = FastAPI()


@app.get("/")
def read_root():
    return {"message": "Welcome to the School Management System API"}
# ---- Students CRUD ----


@app.post("/students", response_model=StudentOut)
def create_student(payload: StudentCreate):
    with Session(engine) as session:
        student = Student(name=payload.name)
        session.add(student)
        session.commit()
        session.refresh(student)
        return student


@app.get("/students", response_model=List[StudentOut])
def list_students():
    with Session(engine) as session:
        students = session.scalars(select(Student)).all()
        return students


@app.get("/students/{student_id}", response_model=StudentOut)
def get_student(student_id: int):
    with Session(engine) as session:
        student = session.get(Student, student_id)
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")
        return student


@app.delete("/students/{student_id}")
def delete_student(student_id: int):
    with Session(engine) as session:
        student = session.get(Student, student_id)
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")
        session.delete(student)
        session.commit()
        return {"deleted": student_id}

# ---- Courses CRUD (simple) ----


@app.post("/courses", response_model=CourseOut)
def create_course(payload: CourseCreate):
    with Session(engine) as session:
        course = Course(title=payload.title)
        session.add(course)
        session.commit()
        session.refresh(course)
        return course


@app.get("/courses", response_model=List[CourseOut])
def list_courses():
    with Session(engine) as session:
        courses = session.scalars(select(Course)).all()
        return courses
# ---- Enrollments ----


@app.post("/enroll")
def enroll(req: EnrollRequest):
    with Session(engine) as session:
        student = session.get(Student, req.student_id)
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        course = session.get(Course, req.course_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

        enrollment = Enrollment(
            student_id=req.student_id, course_id=req.course_id)
        session.add(enrollment)
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise HTTPException(
                status_code=400, detail="Already enrolled (or invalid)")

        return {"enrolled": True, "student_id": req.student_id, "course_id": req.course_id}


@app.get("/students/{student_id}/courses", response_model=StudentWithCourses)
def get_student_courses(student_id: int):
    with Session(engine) as session:
        student = session.get(Student, student_id)
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")

        stmt = (
            select(Course)
            .join(Enrollment, Enrollment.course_id == Course.id)
            .where(Enrollment.student_id == student_id)
        )
        courses = session.scalars(stmt).all()

        return StudentWithCourses(
            id=student.id,
            name=student.name,
            courses=[CourseOut(id=c.id, title=c.title) for c in courses]
        )
