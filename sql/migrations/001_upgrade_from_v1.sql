-- ============================================================
-- Upgrade an EXISTING v1 database to v2.   RUN ONCE, with an ADMIN MySQL account:
--     mysql -u <admin_user> -p < sql/migrations/001_upgrade_from_v1.sql
-- BACK UP FIRST:   mysqldump -u <admin_user> -p lms_database > backup_before_v2.sql
--
-- Changes:
--   1. audit_log table
--   2. updated_at columns
--   3. students/courses can no longer be deleted while they have enrollments
--      (ON DELETE CASCADE -> RESTRICT)
--   4. CHECK constraints (marks 0-100, fee >= 0, failed_attempts >= 0)
--
-- Step 4 fails if existing rows already break a rule. Fix such rows first, e.g.:
--   SELECT * FROM grades WHERE assignment_marks NOT BETWEEN 0 AND 100
--      OR quiz_marks NOT BETWEEN 0 AND 100 OR final_exam_marks NOT BETWEEN 0 AND 100;
-- ============================================================

USE lms_database;

-- 1) audit trail
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

-- 2) updated_at columns
ALTER TABLE students    ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;
ALTER TABLE instructors ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;
ALTER TABLE courses     ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;
ALTER TABLE enrollments ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;
ALTER TABLE grades      ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

-- 3) no more silent cascade deletes of enrollments
ALTER TABLE enrollments
    DROP FOREIGN KEY fk_enrollments_student,
    DROP FOREIGN KEY fk_enrollments_course;
ALTER TABLE enrollments
    ADD CONSTRAINT fk_enrollments_student
        FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE RESTRICT,
    ADD CONSTRAINT fk_enrollments_course
        FOREIGN KEY (course_id) REFERENCES courses(course_id) ON DELETE RESTRICT;

-- 4) CHECK constraints (enforced by MySQL 8.0.16+)
ALTER TABLE grades
    ADD CONSTRAINT chk_grades_assignment CHECK (assignment_marks BETWEEN 0 AND 100),
    ADD CONSTRAINT chk_grades_quiz       CHECK (quiz_marks BETWEEN 0 AND 100),
    ADD CONSTRAINT chk_grades_final      CHECK (final_exam_marks BETWEEN 0 AND 100);
ALTER TABLE courses ADD CONSTRAINT chk_courses_fee CHECK (fee >= 0);
ALTER TABLE users   ADD CONSTRAINT chk_users_failed CHECK (failed_attempts >= 0);
