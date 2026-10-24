-- ============================================================
-- LMS production schema (version 2) - for a NEW, empty database
-- Run with an ADMIN MySQL account (not the app account):
--     mysql -u <admin_user> -p < sql/schema.sql
-- Upgrading an existing v1 database? Use sql/migrations/001_upgrade_from_v1.sql instead.
-- ============================================================

CREATE DATABASE IF NOT EXISTS lms_database
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE lms_database;

-- ------------------------------------------------------------
-- users  (app login)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id         INT AUTO_INCREMENT PRIMARY KEY,
    username        VARCHAR(50)  NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    role            ENUM('admin', 'staff') NOT NULL DEFAULT 'staff',
    is_active       TINYINT(1)   NOT NULL DEFAULT 1,
    failed_attempts INT          NOT NULL DEFAULT 0,
    locked_until    DATETIME     NULL,
    last_login      DATETIME     NULL,
    created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_users_failed CHECK (failed_attempts >= 0)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- students
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS students (
    student_id      INT AUTO_INCREMENT PRIMARY KEY,
    first_name      VARCHAR(100) NOT NULL,
    last_name       VARCHAR(100) NOT NULL,
    email           VARCHAR(150) NOT NULL UNIQUE,
    phone           VARCHAR(20),
    enrollment_date DATE,
    status          ENUM('Active', 'Inactive') NOT NULL DEFAULT 'Active',
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_students_status (status),
    INDEX idx_students_name (last_name, first_name)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- instructors
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS instructors (
    instructor_id   INT AUTO_INCREMENT PRIMARY KEY,
    first_name      VARCHAR(100) NOT NULL,
    last_name       VARCHAR(100) NOT NULL,
    specialization  VARCHAR(150),
    email           VARCHAR(150) NOT NULL UNIQUE,
    phone           VARCHAR(20),
    status          ENUM('Active', 'Inactive') NOT NULL DEFAULT 'Active',
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_instructors_status (status)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- courses  (deleting an instructor leaves the course without one)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS courses (
    course_id       INT AUTO_INCREMENT PRIMARY KEY,
    course_name     VARCHAR(150) NOT NULL,
    description     TEXT,
    instructor_id   INT NULL,
    duration        VARCHAR(50),
    fee             DECIMAL(10,2) NOT NULL DEFAULT 0,
    status          ENUM('Active', 'Inactive') NOT NULL DEFAULT 'Active',
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_courses_instructor
        FOREIGN KEY (instructor_id) REFERENCES instructors(instructor_id)
        ON DELETE SET NULL,
    CONSTRAINT chk_courses_fee CHECK (fee >= 0),
    INDEX idx_courses_status (status)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- enrollments
-- A student or course that has enrollments can NOT be deleted (RESTRICT) - set it to
-- Inactive instead. This replaces the old ON DELETE CASCADE, which silently wiped
-- enrollments and grades together with the student.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS enrollments (
    enrollment_id   INT AUTO_INCREMENT PRIMARY KEY,
    student_id      INT NOT NULL,
    course_id       INT NOT NULL,
    enrollment_date DATE,
    status          ENUM('Enrolled', 'Completed', 'Dropped') NOT NULL DEFAULT 'Enrolled',
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_enrollments_student
        FOREIGN KEY (student_id) REFERENCES students(student_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_enrollments_course
        FOREIGN KEY (course_id) REFERENCES courses(course_id)
        ON DELETE RESTRICT,
    UNIQUE KEY uq_student_course (student_id, course_id),
    INDEX idx_enrollments_status (status)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- grades  (total_marks is DB-computed, never written by the app)
-- The exact per-component maximum (default 20 / 20 / 60) is set in .env and enforced by
-- the app; the database guarantees the hard outer limits of 0-100 per component.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS grades (
    grade_id          INT AUTO_INCREMENT PRIMARY KEY,
    enrollment_id     INT NOT NULL UNIQUE,
    assignment_marks  DECIMAL(5,2) NOT NULL DEFAULT 0,
    quiz_marks        DECIMAL(5,2) NOT NULL DEFAULT 0,
    final_exam_marks  DECIMAL(5,2) NOT NULL DEFAULT 0,
    total_marks DECIMAL(6,2) AS (assignment_marks + quiz_marks + final_exam_marks) STORED,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_grades_enrollment
        FOREIGN KEY (enrollment_id) REFERENCES enrollments(enrollment_id)
        ON DELETE CASCADE,
    CONSTRAINT chk_grades_assignment CHECK (assignment_marks BETWEEN 0 AND 100),
    CONSTRAINT chk_grades_quiz       CHECK (quiz_marks BETWEEN 0 AND 100),
    CONSTRAINT chk_grades_final      CHECK (final_exam_marks BETWEEN 0 AND 100)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- audit_log  (who did what, when - IDs only, no personal data)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    log_id      BIGINT AUTO_INCREMENT PRIMARY KEY,
    username    VARCHAR(50)  NULL,
    action      VARCHAR(30)  NOT NULL,
    entity      VARCHAR(30)  NOT NULL,
    entity_id   INT          NULL,
    details     VARCHAR(500) NULL,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_audit_created (created_at),
    INDEX idx_audit_entity (entity, entity_id)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- No default user is seeded on purpose. After running this schema, create the
-- first admin with:   python scripts/create_user.py
-- ------------------------------------------------------------
