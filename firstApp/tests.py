from datetime import date, timedelta
from html.parser import HTMLParser
import json
import shutil
import subprocess
from tempfile import TemporaryDirectory
from unittest.mock import patch
import base64
from io import BytesIO
from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.templatetags.static import static
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .exam_engine import build_student_paper
from .models import (
    AcademicTerm,
    Course,
    CourseOffering,
    Enrollment,
    Exam,
    ExamComputer,
    ExamSession,
    FaceProfile,
    ProctorEvent,
    StudentAnswer,
    StudentExam,
    TeachingAssignment,
)


class AcademicStructureTests(TestCase):
    """
    Kiểm tra cấu trúc học vụ:
    Course -> AcademicTerm -> CourseOffering
    CourseOffering -> TeachingAssignment / Enrollment
    """

    @classmethod
    def setUpClass(cls):
        cls.media_directory = TemporaryDirectory()

        cls.settings_override = override_settings(
            MEDIA_ROOT=cls.media_directory.name
        )
        cls.settings_override.enable()

        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()

        cls.settings_override.disable()
        cls.media_directory.cleanup()

    def setUp(self):
        self.course = Course.objects.create(
            code="NMLT101",
            name="Nhập môn lập trình",
            faculty="CNTT",
        )

        self.term = AcademicTerm.objects.create(
            academic_year="2026-2027",
            semester_number=1,
            start_date=date(2026, 9, 1),
            end_date=date(2027, 1, 31),
        )

    # ==========================================================
    # HELPER
    # ==========================================================

    def create_profile(self, username, role):
        """
        Signal của UserProfile tự tạo profile khi tạo User.
        Sau đó test chỉ đổi role.
        """

        user = User.objects.create_user(
            username=username,
            password="safe-test-password",
        )

        profile = user.userprofile
        profile.role = role
        profile.save()

        user.refresh_from_db()

        return profile

    def create_exam(self, offering):
        return Exam.objects.create(
            course=self.course,
            offering=offering,
            title="Kiểm tra giữa kỳ",
            duration_minutes=60,
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=2),
        )

    def create_active_offering(self, group_code="NMLT-TEST", session_number=1):
        return CourseOffering.objects.create(
            course=self.course,
            term=self.term,
            group_code=group_code,
            session_number=session_number,
            classroom="P.101",
        )

    # ==========================================================
    # 1. ACADEMIC TERM
    # ==========================================================

    def test_term_rejects_end_date_before_start_date(self):
        term = AcademicTerm(
            academic_year="2027-2028",
            semester_number=1,
            start_date=date(2027, 9, 1),
            end_date=date(2027, 8, 31),
        )

        with self.assertRaises(ValidationError):
            term.full_clean()

    # ==========================================================
    # 2. COURSE OFFERING
    # ==========================================================

    def test_offering_supports_multiple_lecturers_and_mixed_class_students(self):
        lecturer_one = self.create_profile(
            "lecturer-one",
            "lecturer",
        )

        lecturer_two = self.create_profile(
            "lecturer-two",
            "lecturer",
        )

        student_one = self.create_profile(
            "student-one",
            "student",
        )

        student_two = self.create_profile(
            "student-two",
            "student",
        )

        offering = self.create_active_offering(
            group_code="NMLT-CA2",
            session_number=2,
        )

        TeachingAssignment.objects.create(
            course_offering=offering,
            lecturer=lecturer_one,
        )

        TeachingAssignment.objects.create(
            course_offering=offering,
            lecturer=lecturer_two,
        )

        Enrollment.objects.create(
            course_offering=offering,
            student=student_one,
        )

        Enrollment.objects.create(
            course_offering=offering,
            student=student_two,
        )

        self.assertCountEqual(
            [
                assignment.lecturer
                for assignment in offering.teaching_assignments.all()
            ],
            (
                lecturer_one,
                lecturer_two,
            ),
        )

        self.assertCountEqual(
            [
                enrollment.student
                for enrollment in offering.enrollments.all()
            ],
            (
                student_one,
                student_two,
            ),
        )

    # ==========================================================
    # 3. LECTURER ADMIN PERMISSION
    # ==========================================================

    def test_lecturer_role_receives_full_django_admin_permissions(self):
        lecturer = self.create_profile(
            "lecturer-admin",
            "lecturer",
        )

        lecturer.user.refresh_from_db()

        self.assertTrue(lecturer.user.is_staff)

        self.assertTrue(
            lecturer.user.has_perm("auth.view_user")
        )

        self.assertTrue(
            lecturer.user.has_perm("firstApp.add_academicterm")
        )

        client = Client()
        client.force_login(lecturer.user)

        response = client.get(
            reverse(
                "admin:firstApp_academicterm_changelist"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

    # ==========================================================
    # 4. STUDENT CANNOT ENTER ANOTHER OFFERING
    # ==========================================================

    def test_student_cannot_open_exam_for_another_offering(self):
        enrolled_student = self.create_profile(
            "enrolled-student",
            "student",
        )

        other_student = self.create_profile(
            "other-student",
            "student",
        )

        offering = self.create_active_offering(
            group_code="NMLT-CA1",
            session_number=1,
        )

        Enrollment.objects.create(
            course_offering=offering,
            student=enrolled_student,
        )

        exam = self.create_exam(offering)

        exam.start_time = timezone.now() - timedelta(minutes=5)
        exam.end_time = timezone.now() + timedelta(hours=1)

        exam.save(
            update_fields=[
                "start_time",
                "end_time",
            ]
        )

        client = Client()
        client.force_login(other_student.user)

        response = client.get(
            reverse(
                "take_exam",
                args=(exam.pk,),
            )
        )

        self.assertRedirects(
            response,
            reverse("course_list"),
        )

    # ==========================================================
    # 5. EXAM LIST IS ROLE / ENROLLMENT SCOPED
    # ==========================================================

    def test_student_sees_only_assigned_offering_exams(self):
        enrolled_student = self.create_profile(
            "exam-student",
            "student",
        )

        other_student = self.create_profile(
            "unassigned-student",
            "student",
        )

        offering = self.create_active_offering(
            group_code="NMLT-CA3",
            session_number=3,
        )

        Enrollment.objects.create(
            course_offering=offering,
            student=enrolled_student,
        )

        exam = self.create_exam(offering)

        client = Client()

        client.force_login(enrolled_student.user)

        response = client.get(
            reverse("exam_list")
        )

        self.assertContains(
            response,
            exam.title,
        )

        client.force_login(other_student.user)

        response = client.get(
            reverse("exam_list")
        )

        self.assertNotContains(
            response,
            exam.title,
        )

    # ==========================================================
    # 6. HOME DASHBOARD
    # ==========================================================

    def test_home_dashboard_uses_role_scoped_courses_and_exams(self):
        student = self.create_profile(
            "dashboard-student",
            "student",
        )

        lecturer = self.create_profile(
            "dashboard-lecturer",
            "lecturer",
        )

        other_student = self.create_profile(
            "dashboard-outsider",
            "student",
        )

        offering = self.create_active_offering(
            group_code="NMLT-DASH",
            session_number=1,
        )

        Enrollment.objects.create(
            course_offering=offering,
            student=student,
        )

        TeachingAssignment.objects.create(
            course_offering=offering,
            lecturer=lecturer,
        )

        exam = Exam.objects.create(
            course=self.course,
            offering=offering,
            title="Đề thi dashboard",
            duration_minutes=60,
            start_time=timezone.now() + timedelta(hours=1),
            end_time=timezone.now() + timedelta(hours=2),
        )

        client = Client()

        client.force_login(student.user)

        student_home = client.get(
            reverse("home")
        )

        self.assertContains(
            student_home,
            exam.title,
        )

        self.assertContains(
            student_home,
            "Khóa học",
        )

        client.force_login(lecturer.user)

        lecturer_home = client.get(
            reverse("home")
        )

        self.assertContains(
            lecturer_home,
            exam.title,
        )

        self.assertContains(
            lecturer_home,
            "Lớp phụ trách",
        )

        client.force_login(other_student.user)

        outsider_home = client.get(
            reverse("home")
        )

        self.assertNotContains(
            outsider_home,
            exam.title,
        )

    # ==========================================================
    # 7. EXAM BUILDER - JSON ARCHITECTURE
    # ==========================================================

    def test_exam_builder_post_persists_json_question_data(self):
        admin_profile = self.create_profile(
            "exam-builder-admin",
            "admin",
        )

        offering = self.create_active_offering(
            group_code="NMLT-BUILDER",
            session_number=1,
        )

        now = timezone.now()

        question_data = [
            {
                "type": "MCQ",
                "content": "Chọn đáp án đúng",
                "score": 1,
                "choices": [
                    {
                        "label": "A",
                        "text": "Đúng",
                    },
                    {
                        "label": "B",
                        "text": "Sai 1",
                    },
                    {
                        "label": "C",
                        "text": "Sai 2",
                    },
                    {
                        "label": "D",
                        "text": "Sai 3",
                    },
                ],
                "correct_answer": "A",
            },
            {
                "type": "DRAG",
                "content": "Điền khuyết",
                "score": 1,
                "code_template": "int result = [[1]];",
                "items": [
                    {
                        "text": "42",
                        "correct_order": 1,
                    }
                ],
            },
            {
                "type": "SORT",
                "content": "Sắp xếp lệnh",
                "score": 1,
                "items": [
                    {
                        "text": "int value = 1;",
                        "correct_order": 1,
                    },
                    {
                        "text": "return value;",
                        "correct_order": 2,
                    },
                ],
            },
            {
                "type": "CODE",
                "content": "Viết chương trình",
                "score": 2,
                "language": "cpp",
                "starter_code": "int main() {}",
                "test_cases": [
                    {
                        "input_data": "",
                        "expected_output": "42",
                        "score": 2,
                    }
                ],
            },
        ]

        client = Client()
        client.force_login(admin_profile.user)

        response = client.post(
            reverse(
                "admin:firstApp_exam_builder_create"
            ),
            {
                "title": "Đề tích hợp 4 dạng",
                "course": self.course.pk,
                "offering": offering.pk,
                "duration_minutes": 45,
                "start_time": (
                    now - timedelta(minutes=5)
                ).strftime("%Y-%m-%dT%H:%M"),
                "end_time": (
                    now + timedelta(hours=1)
                ).strftime("%Y-%m-%dT%H:%M"),
                "number_of_papers": 3,
                "question_data": json.dumps(
                    question_data,
                    ensure_ascii=False,
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        exam = Exam.objects.get(
            title="Đề tích hợp 4 dạng"
        )

        self.assertEqual(
            len(exam.question_data),
            4,
        )

        self.assertEqual(
            {
                question["type"]
                for question in exam.question_data
            },
            {
                "MCQ",
                "DRAG",
                "SORT",
                "CODE",
            },
        )

        self.assertEqual(
            len(exam.paper_codes),
            3,
        )

        drag_question = next(
            question
            for question in exam.question_data
            if question["type"] == "DRAG"
        )

        self.assertEqual(
            drag_question["code_template"],
            "int result = [[1]];",
        )

        code_question = next(
            question
            for question in exam.question_data
            if question["type"] == "CODE"
        )

        self.assertEqual(
            len(code_question["test_cases"]),
            1,
        )

    # ==========================================================
    # 8. JSON PAPER BUILDER
    # ==========================================================

    def test_snapshot_builder_normalizes_and_shuffles_mcq(self):
        exam = Exam(
            question_data=[
                {
                    "type": "MCQ",
                    "content": "Chọn đáp án đúng",
                    "score": 3,
                    "choices": [
                        {
                            "label": "A",
                            "text": "Sai",
                        },
                        {
                            "label": "B",
                            "text": "Đúng",
                        },
                        {
                            "label": "C",
                            "text": "Sai nữa",
                        },
                        {
                            "label": "D",
                            "text": "Cũng sai",
                        },
                    ],
                    "correct_answer": "B",
                }
            ],
            paper_codes=["MCQ-01"],
        )

        paper = build_student_paper(exam)

        self.assertEqual(
            paper["paper_code"],
            "MCQ-01",
        )

        self.assertEqual(
            len(paper["questions"]),
            1,
        )

        question = paper["questions"][0]

        self.assertEqual(
            question["index"],
            1,
        )

        self.assertEqual(
            question["type"],
            "MCQ",
        )

        self.assertEqual(
            len(question["choices"]),
            4,
        )

        self.assertCountEqual(
            [
                choice["text"]
                for choice in question["choices"]
            ],
            [
                "Sai",
                "Đúng",
                "Sai nữa",
                "Cũng sai",
            ],
        )

        self.assertIn(
            "Đúng",
            [
                choice["text"]
                for choice in question["choices"]
            ],
        )

    # ==========================================================
    # 9. TAKE EXAM CREATES ONE SNAPSHOT
    # ==========================================================

    def test_saved_exam_creates_student_snapshot_once(self):
        student = self.create_profile(
            "snapshot-student",
            "student",
        )

        offering = self.create_active_offering(
            group_code="NMLT-SNAPSHOT",
            session_number=1,
        )

        Enrollment.objects.create(
            course_offering=offering,
            student=student,
        )

        exam = Exam.objects.create(
            course=self.course,
            offering=offering,
            title="Kiểm tra snapshot",
            duration_minutes=60,
            start_time=timezone.now() - timedelta(minutes=5),
            end_time=timezone.now() + timedelta(hours=1),
            paper_codes=["SNAP-01"],
            question_data=[
                {
                    "type": "MCQ",
                    "content": "2 + 2 bằng bao nhiêu?",
                    "score": 1,
                    "choices": [
                        {
                            "label": "A",
                            "text": "3",
                        },
                        {
                            "label": "B",
                            "text": "4",
                        },
                        {
                            "label": "C",
                            "text": "5",
                        },
                        {
                            "label": "D",
                            "text": "6",
                        },
                    ],
                    "correct_answer": "B",
                }
            ],
        )

        client = Client()
        client.force_login(student.user)

        response = client.get(
            reverse(
                "take_exam",
                args=(exam.pk,),
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        attempt = StudentExam.objects.get(
            student=student.user,
            exam=exam,
        )

        self.assertEqual(
            attempt.exam_code,
            "SNAP-01",
        )

        self.assertTrue(
            attempt.question_snapshot
        )

        snapshot = attempt.question_snapshot

        self.assertIn(
            "questions",
            snapshot,
        )

        self.assertEqual(
            len(snapshot["questions"]),
            1,
        )

        first_index = snapshot["questions"][0]["index"]

        refreshed_response = client.get(
            reverse(
                "take_exam",
                args=(exam.pk,),
            )
        )

        self.assertEqual(
            refreshed_response.status_code,
            200,
        )

        attempt.refresh_from_db()

        self.assertEqual(
            attempt.question_snapshot["questions"][0]["index"],
            first_index,
        )

        self.assertEqual(
            StudentExam.objects.filter(
                student=student.user,
                exam=exam,
            ).count(),
            1,
        )

    # ==========================================================
    # 10. MCQ CORRECT ANSWER
    # ==========================================================

    def test_mcq_correct_answer_is_graded_from_snapshot(self):
        student = self.create_profile(
            "mcq-correct-student",
            "student",
        )

        offering = self.create_active_offering(
            group_code="NMLT-MCQ-CORRECT",
            session_number=1,
        )

        Enrollment.objects.create(
            course_offering=offering,
            student=student,
        )

        exam = Exam.objects.create(
            course=self.course,
            offering=offering,
            title="MCQ đúng",
            duration_minutes=60,
            start_time=timezone.now() - timedelta(minutes=5),
            end_time=timezone.now() + timedelta(hours=1),
            question_data=[
                {
                    "type": "MCQ",
                    "content": "Hai nhân hai bằng bao nhiêu?",
                    "score": 3,
                    "choices": [
                        {
                            "label": "A",
                            "text": "3",
                        },
                        {
                            "label": "B",
                            "text": "4",
                        },
                        {
                            "label": "C",
                            "text": "5",
                        },
                        {
                            "label": "D",
                            "text": "6",
                        },
                    ],
                    "correct_answer": "B",
                }
            ],
        )

        client = Client()
        client.force_login(student.user)

        page = client.get(
            reverse(
                "take_exam",
                args=(exam.pk,),
            )
        )

        self.assertEqual(
            page.status_code,
            200,
        )

        attempt = StudentExam.objects.get(
            student=student.user,
            exam=exam,
        )

        question = attempt.question_snapshot["questions"][0]

        correct_text = next(
            choice["text"]
            for choice in question["choices"]
            if choice.get("label") == "B"
        )

        response = client.post(
            reverse(
                "submit_exam",
                args=(attempt.pk,),
            ),
            {
                f"question_{question['index']}":
                    correct_text,
            },
        )

        self.assertRedirects(
            response,
            reverse(
                "exam_result",
                args=(attempt.pk,),
            ),
        )

        attempt.refresh_from_db()

        self.assertTrue(
            attempt.is_submitted
        )

        self.assertEqual(
            attempt.score,
            3,
        )

        answer = StudentAnswer.objects.get(
            student_exam=attempt,
            question_index=question["index"],
        )

        self.assertTrue(
            answer.is_correct
        )

        self.assertEqual(
            answer.answer_text,
            "4",
        )

        self.assertEqual(
            answer.question_type,
            "MCQ",
        )

    # ==========================================================
    # 11. MCQ WRONG ANSWER
    # ==========================================================

    def test_mcq_wrong_answer_receives_zero_score(self):
        student = self.create_profile(
            "mcq-wrong-student",
            "student",
        )

        offering = self.create_active_offering(
            group_code="NMLT-MCQ-WRONG",
            session_number=1,
        )

        Enrollment.objects.create(
            course_offering=offering,
            student=student,
        )

        exam = Exam.objects.create(
            course=self.course,
            offering=offering,
            title="MCQ sai",
            duration_minutes=60,
            start_time=timezone.now() - timedelta(minutes=5),
            end_time=timezone.now() + timedelta(hours=1),
            question_data=[
                {
                    "type": "MCQ",
                    "content": "Hai nhân hai bằng bao nhiêu?",
                    "score": 3,
                    "choices": [
                        {
                            "label": "A",
                            "text": "3",
                        },
                        {
                            "label": "B",
                            "text": "4",
                        },
                        {
                            "label": "C",
                            "text": "5",
                        },
                        {
                            "label": "D",
                            "text": "6",
                        },
                    ],
                    "correct_answer": "B",
                }
            ],
        )

        client = Client()
        client.force_login(student.user)

        client.get(
            reverse(
                "take_exam",
                args=(exam.pk,),
            )
        )

        attempt = StudentExam.objects.get(
            student=student.user,
            exam=exam,
        )

        question = attempt.question_snapshot["questions"][0]

        wrong_text = next(
            choice["text"]
            for choice in question["choices"]
            if choice.get("label") != "B"
        )

        response = client.post(
            reverse(
                "submit_exam",
                args=(attempt.pk,),
            ),
            {
                f"question_{question['index']}":
                    wrong_text,
            },
        )

        self.assertRedirects(
            response,
            reverse(
                "exam_result",
                args=(attempt.pk,),
            ),
        )

        attempt.refresh_from_db()

        self.assertEqual(
            attempt.score,
            0,
        )

        answer = attempt.answers.get(
            question_index=question["index"]
        )

        self.assertFalse(
            answer.is_correct
        )

    # ==========================================================
    # 12. DRAG
    # ==========================================================

    def test_drag_grading_uses_snapshot_answer_order(self):
        student = self.create_profile(
            "drag-student",
            "student",
        )

        offering = self.create_active_offering(
            group_code="NMLT-DRAG",
            session_number=1,
        )

        Enrollment.objects.create(
            course_offering=offering,
            student=student,
        )

        exam = Exam.objects.create(
            course=self.course,
            offering=offering,
            title="DRAG snapshot",
            duration_minutes=60,
            start_time=timezone.now() - timedelta(minutes=5),
            end_time=timezone.now() + timedelta(hours=1),
            question_data=[
                {
                    "type": "DRAG",
                    "content": "Điền hai phần",
                    "score": 2,
                    "code_template": "[[1]] then [[2]]",
                    "items": [
                        {
                            "text": "first",
                            "correct_order": 1,
                        },
                        {
                            "text": "second",
                            "correct_order": 2,
                        },
                    ],
                }
            ],
        )

        client = Client()
        client.force_login(student.user)

        page = client.get(
            reverse(
                "take_exam",
                args=(exam.pk,),
            )
        )

        self.assertEqual(
            page.status_code,
            200,
        )

        attempt = StudentExam.objects.get(
            student=student.user,
            exam=exam,
        )

        question = attempt.question_snapshot["questions"][0]

        self.assertEqual(
            question["type"],
            "DRAG",
        )

        self.assertIn(
            "_correct_answers",
            question,
        )

        response = client.post(
            reverse(
                "submit_exam",
                args=(attempt.pk,),
            ),
            {
                f"sorted_ids_{question['index']}":
                    json.dumps(
                        question["_correct_answers"]
                    ),
            },
        )

        self.assertRedirects(
            response,
            reverse(
                "exam_result",
                args=(attempt.pk,),
            ),
        )

        attempt.refresh_from_db()

        self.assertEqual(
            attempt.score,
            2,
        )

        answer = attempt.answers.get(
            question_index=question["index"]
        )

        self.assertTrue(
            answer.is_correct
        )

    # ==========================================================
    # 13. SORT
    # ==========================================================

    def test_sort_grading_uses_snapshot_correct_order(self):
        student = self.create_profile(
            "sort-student",
            "student",
        )

        offering = self.create_active_offering(
            group_code="NMLT-SORT",
            session_number=1,
        )

        Enrollment.objects.create(
            course_offering=offering,
            student=student,
        )

        exam = Exam.objects.create(
            course=self.course,
            offering=offering,
            title="SORT snapshot",
            duration_minutes=60,
            start_time=timezone.now() - timedelta(minutes=5),
            end_time=timezone.now() + timedelta(hours=1),
            question_data=[
                {
                    "type": "SORT",
                    "content": "Sắp xếp hai dòng",
                    "score": 2,
                    "items": [
                        {
                            "text": "int value = 1;",
                            "correct_order": 1,
                        },
                        {
                            "text": "return value;",
                            "correct_order": 2,
                        },
                    ],
                }
            ],
        )

        client = Client()
        client.force_login(student.user)

        client.get(
            reverse(
                "take_exam",
                args=(exam.pk,),
            )
        )

        attempt = StudentExam.objects.get(
            student=student.user,
            exam=exam,
        )

        question = attempt.question_snapshot["questions"][0]

        self.assertIn(
            "_correct_order",
            question,
        )

        response = client.post(
            reverse(
                "submit_exam",
                args=(attempt.pk,),
            ),
            {
                f"sorted_ids_{question['index']}":
                    json.dumps(
                        question["_correct_order"]
                    ),
            },
        )

        self.assertRedirects(
            response,
            reverse(
                "exam_result",
                args=(attempt.pk,),
            ),
        )

        attempt.refresh_from_db()

        self.assertEqual(
            attempt.score,
            2,
        )

        answer = attempt.answers.get(
            question_index=question["index"]
        )

        self.assertTrue(
            answer.is_correct
        )

    # ==========================================================
    # 14. DRAG + SORT + CODE
    # ==========================================================

    def test_drag_sort_and_code_answers_are_graded_from_snapshot(self):
        student = self.create_profile(
            "mixed-question-student",
            "student",
        )

        offering = self.create_active_offering(
            group_code="NMLT-MIXED",
            session_number=1,
        )

        Enrollment.objects.create(
            course_offering=offering,
            student=student,
        )

        exam = Exam.objects.create(
            course=self.course,
            offering=offering,
            title="Kiểm tra câu hỏi đa dạng",
            duration_minutes=60,
            start_time=timezone.now() - timedelta(minutes=5),
            end_time=timezone.now() + timedelta(hours=1),
            question_data=[
                {
                    "type": "DRAG",
                    "content": "Điền hai phần",
                    "score": 1,
                    "code_template": "[[1]] then [[2]]",
                    "items": [
                        {
                            "text": "int",
                            "correct_order": 1,
                        },
                        {
                            "text": "return 1;",
                            "correct_order": 2,
                        },
                    ],
                },
                {
                    "type": "SORT",
                    "content": "Sắp xếp hai dòng",
                    "score": 1,
                    "items": [
                        {
                            "text": "int value = 1;",
                            "correct_order": 1,
                        },
                        {
                            "text": "return value;",
                            "correct_order": 2,
                        },
                    ],
                },
                {
                    "type": "CODE",
                    "content": "In kết quả",
                    "score": 2,
                    "language": "cpp",
                    "starter_code": "",
                    "test_cases": [
                        {
                            "input_data": "",
                            "expected_output": "ok",
                            "score": 2,
                        }
                    ],
                },
            ],
        )

        client = Client()
        client.force_login(student.user)

        client.get(
            reverse(
                "take_exam",
                args=(exam.pk,),
            )
        )

        attempt = StudentExam.objects.get(
            student=student.user,
            exam=exam,
        )

        questions = attempt.question_snapshot["questions"]

        drag_question = next(
            question
            for question in questions
            if question["type"] == "DRAG"
        )

        sort_question = next(
            question
            for question in questions
            if question["type"] == "SORT"
        )

        code_question = next(
            question
            for question in questions
            if question["type"] == "CODE"
        )

        with patch(
            "firstApp.views.run_cpp",
            return_value={
                "status": "Success",
                "stdout": "ok",
                "stderr": "",
            },
        ):
            response = client.post(
                reverse(
                    "submit_exam",
                    args=(attempt.pk,),
                ),
                {
                    f"sorted_ids_{drag_question['index']}":
                        json.dumps(
                            drag_question["_correct_answers"]
                        ),

                    f"sorted_ids_{sort_question['index']}":
                        json.dumps(
                            sort_question["_correct_order"]
                        ),

                    f"code_answer_{code_question['index']}":
                        "int main() {}",
                },
            )

        self.assertRedirects(
            response,
            reverse(
                "exam_result",
                args=(attempt.pk,),
            ),
        )

        attempt.refresh_from_db()

        self.assertEqual(
            attempt.score,
            4,
        )

        self.assertEqual(
            attempt.answers.count(),
            3,
        )

        self.assertTrue(
            attempt.answers.get(
                question_index=drag_question["index"]
            ).is_correct
        )

        self.assertTrue(
            attempt.answers.get(
                question_index=sort_question["index"]
            ).is_correct
        )

        code_answer = attempt.answers.get(
            question_index=code_question["index"]
        )

        self.assertEqual(
            code_answer.score,
            2,
        )

    # ==========================================================
    # 15. RESULT / HISTORY
    # ==========================================================

    def test_saved_exam_can_be_submitted_and_reviewed(self):
        student = self.create_profile(
            "workflow-student",
            "student",
        )

        offering = self.create_active_offering(
            group_code="NMLT-WORKFLOW",
            session_number=1,
        )

        Enrollment.objects.create(
            course_offering=offering,
            student=student,
        )

        exam = Exam.objects.create(
            course=self.course,
            offering=offering,
            title="Kiểm tra luồng thi",
            duration_minutes=60,
            start_time=timezone.now() - timedelta(minutes=5),
            end_time=timezone.now() + timedelta(hours=1),
            question_data=[
                {
                    "type": "MCQ",
                    "content": "2 + 2 bằng bao nhiêu?",
                    "score": 1,
                    "choices": [
                        {
                            "label": "A",
                            "text": "3",
                        },
                        {
                            "label": "B",
                            "text": "4",
                        },
                        {
                            "label": "C",
                            "text": "5",
                        },
                        {
                            "label": "D",
                            "text": "6",
                        },
                    ],
                    "correct_answer": "B",
                }
            ],
        )

        client = Client()
        client.force_login(student.user)

        exam_page = client.get(
            reverse(
                "take_exam",
                args=(exam.pk,),
            )
        )

        self.assertEqual(
            exam_page.status_code,
            200,
        )

        attempt = StudentExam.objects.get(
            student=student.user,
            exam=exam,
        )

        question = attempt.question_snapshot["questions"][0]

        correct_text = next(
            choice["text"]
            for choice in question["choices"]
            if choice.get("label") == "B"
        )

        submit_page = client.post(
            reverse(
                "submit_exam",
                args=(attempt.pk,),
            ),
            {
                f"question_{question['index']}":
                    correct_text,
            },
        )

        self.assertRedirects(
            submit_page,
            reverse(
                "exam_result",
                args=(attempt.pk,),
            ),
        )

        attempt.refresh_from_db()

        self.assertTrue(
            attempt.is_submitted
        )

        result_page = client.get(
            reverse(
                "exam_result",
                args=(attempt.pk,),
            )
        )

        self.assertEqual(
            result_page.status_code,
            200,
        )

        history_page = client.get(
            reverse(
                "exam_result_list"
            )
        )

        self.assertEqual(
            history_page.status_code,
            200,
        )

        self.assertContains(
            history_page,
            exam.title,
        )

    # ==========================================================
    # 16. PUBLIC EXAM PAGE MUST NOT EXPOSE ANSWERS
    # ==========================================================

    def test_take_exam_page_does_not_expose_internal_correct_answer_keys(self):
        student = self.create_profile(
            "security-student",
            "student",
        )

        offering = self.create_active_offering(
            group_code="NMLT-SECURITY",
            session_number=1,
        )

        Enrollment.objects.create(
            course_offering=offering,
            student=student,
        )

        exam = Exam.objects.create(
            course=self.course,
            offering=offering,
            title="Kiểm tra bảo mật",
            duration_minutes=60,
            start_time=timezone.now() - timedelta(minutes=5),
            end_time=timezone.now() + timedelta(hours=1),
            question_data=[
                {
                    "type": "DRAG",
                    "content": "Câu kéo thả",
                    "score": 1,
                    "code_template": "[[1]]",
                    "items": [
                        {
                            "text": "42",
                            "correct_order": 1,
                        }
                    ],
                },
                {
                    "type": "SORT",
                    "content": "Câu sắp xếp",
                    "score": 1,
                    "items": [
                        {
                            "text": "line 1",
                            "correct_order": 1,
                        },
                        {
                            "text": "line 2",
                            "correct_order": 2,
                        },
                    ],
                },
                {
                    "type": "MCQ",
                    "content": "Câu trắc nghiệm",
                    "score": 1,
                    "choices": [
                        {
                            "label": "A",
                            "text": "Đúng",
                        },
                        {
                            "label": "B",
                            "text": "Sai",
                        },
                        {
                            "label": "C",
                            "text": "Sai 2",
                        },
                        {
                            "label": "D",
                            "text": "Sai 3",
                        },
                    ],
                    "correct_answer": "A",
                },
            ],
        )

        client = Client()
        client.force_login(student.user)

        response = client.get(
            reverse(
                "take_exam",
                args=(exam.pk,),
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        rendered_html = response.content.decode()

        self.assertNotIn(
            "_correct_answers",
            rendered_html,
        )

        self.assertNotIn(
            "_correct_order",
            rendered_html,
        )

        self.assertNotIn(
            "correct_answer",
            rendered_html,
        )

        self.assertNotIn(
            "correct_order",
            rendered_html,
        )

    # ==========================================================
    # 17. EXAM CSS
    # ==========================================================

    def test_take_exam_stylesheet_is_loaded_from_document_head(self):
        student = self.create_profile(
            "exam-css-student",
            "student",
        )

        offering = self.create_active_offering(
            group_code="NMLT-CSS",
            session_number=1,
        )

        Enrollment.objects.create(
            course_offering=offering,
            student=student,
        )

        exam = Exam.objects.create(
            course=self.course,
            offering=offering,
            title="Kiểm tra stylesheet",
            duration_minutes=60,
            start_time=timezone.now() - timedelta(minutes=5),
            end_time=timezone.now() + timedelta(hours=1),
            question_data=[
                {
                    "type": "MCQ",
                    "content": "CSS route check",
                    "score": 1,
                    "choices": [
                        {
                            "label": "A",
                            "text": "A",
                        },
                        {
                            "label": "B",
                            "text": "B",
                        },
                        {
                            "label": "C",
                            "text": "C",
                        },
                        {
                            "label": "D",
                            "text": "D",
                        },
                    ],
                    "correct_answer": "A",
                }
            ],
        )

        client = Client()
        client.force_login(student.user)

        response = client.get(
            reverse(
                "take_exam",
                args=(exam.pk,),
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        css_url = static(
            "css/exam_vscode.css"
        )

        self.assertIsNotNone(
            finders.find(
                "css/exam_vscode.css"
            )
        )

        rendered_html = response.content.decode()

        self.assertIn(
            css_url,
            rendered_html,
        )

        self.assertLess(
            rendered_html.index(css_url),
            rendered_html.index("<body"),
        )

        node_executable = shutil.which("node")

        if not node_executable:
            self.skipTest(
                "Node.js is required to syntax-check inline exam scripts."
            )

        class InlineScriptCollector(HTMLParser):
            def __init__(self):
                super().__init__()

                self.inline_scripts = []
                self.current_script = None

            def handle_starttag(
                self,
                tag,
                attrs,
            ):
                if (
                    tag == "script"
                    and not dict(attrs).get("src")
                ):
                    self.current_script = []

            def handle_endtag(self, tag):
                if (
                    tag == "script"
                    and self.current_script is not None
                ):
                    self.inline_scripts.append(
                        "".join(
                            self.current_script
                        )
                    )

                    self.current_script = None

            def handle_data(self, data):
                if self.current_script is not None:
                    self.current_script.append(data)

        script_collector = InlineScriptCollector()

        script_collector.feed(
            rendered_html
        )

        self.assertTrue(
            script_collector.inline_scripts
        )

        for script in script_collector.inline_scripts:
            subprocess.run(
                [
                    node_executable,
                    "--check",
                    "-",
                ],
                input=script,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )

    # ==========================================================
    # 18. EXAM COMPUTER -> STABLE PAPER CODE
    # ==========================================================

    def test_assigned_exam_computer_determines_stable_paper_code(self):
        student = self.create_profile(
            "assigned-pc-student",
            "student",
        )

        offering = self.create_active_offering(
            group_code="NMLT-PC",
            session_number=1,
        )

        Enrollment.objects.create(
            course_offering=offering,
            student=student,
        )

        exam = Exam.objects.create(
            course=self.course,
            offering=offering,
            title="Mã đề theo máy",
            duration_minutes=60,
            start_time=timezone.now() - timedelta(minutes=5),
            end_time=timezone.now() + timedelta(hours=1),
            paper_codes=[
                "PAPER-A",
                "PAPER-B",
                "PAPER-C",
            ],
            question_data=[
                {
                    "type": "MCQ",
                    "content": "Câu kiểm tra",
                    "score": 1,
                    "choices": [
                        {
                            "label": "A",
                            "text": "A",
                        },
                        {
                            "label": "B",
                            "text": "B",
                        },
                        {
                            "label": "C",
                            "text": "C",
                        },
                        {
                            "label": "D",
                            "text": "D",
                        },
                    ],
                    "correct_answer": "A",
                }
            ],
        )

        session = ExamSession.objects.create(
            exam=exam,
            offering=offering,
            room="P.201",
            start_time=exam.start_time,
            end_time=exam.end_time,
            status="ongoing",
        )

        computer = ExamComputer.objects.create(
            exam_session=session,
            computer_number=2,
            student=student,
            status="assigned",
        )

        client = Client()
        client.force_login(student.user)

        response = client.get(
            reverse(
                "take_exam",
                args=(exam.pk,),
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        attempt = StudentExam.objects.get(
            student=student.user,
            exam=exam,
        )

        self.assertEqual(
            attempt.exam_computer,
            computer,
        )

        self.assertEqual(
            attempt.exam_code,
            "PAPER-B",
        )

    # ==========================================================
    # 19. TEACHER REPORT
    # ==========================================================

    def test_teacher_report_lists_enrolled_students_and_downloads_pdf(self):
        teacher = self.create_profile(
            "report-admin",
            "admin",
        )

        student = self.create_profile(
            "report-student",
            "student",
        )

        offering = self.create_active_offering(
            group_code="NMLT-REPORT",
            session_number=1,
        )

        Enrollment.objects.create(
            course_offering=offering,
            student=student,
        )

        exam = Exam.objects.create(
            course=self.course,
            offering=offering,
            title="Báo cáo kiểm tra",
            duration_minutes=60,
            start_time=timezone.now() - timedelta(minutes=5),
            end_time=timezone.now() + timedelta(hours=1),
        )

        client = Client()
        client.force_login(teacher.user)

        report_page = client.get(
            reverse(
                "teacher_exam_report",
                args=(exam.pk,),
            )
        )

        self.assertEqual(
            report_page.status_code,
            200,
        )

        self.assertContains(
            report_page,
            "report-student",
        )

        self.assertContains(
            report_page,
            "Chưa có lượt thi",
        )

        pdf_response = client.get(
            reverse(
                "teacher_exam_pdf",
                args=(exam.pk,),
            )
        )

        self.assertEqual(
            pdf_response.status_code,
            200,
        )

        self.assertEqual(
            pdf_response["Content-Type"],
            "application/pdf",
        )

        self.assertTrue(
            pdf_response.content.startswith(
                b"%PDF"
            )
        )

    def test_unassigned_lecturer_cannot_download_exam_pdf(self):
        lecturer = self.create_profile(
            "unassigned-pdf-lecturer",
            "lecturer",
        )

        offering = self.create_active_offering(
            group_code="NMLT-PDF-PRIVATE",
            session_number=1,
        )

        # Cố ý không tạo TeachingAssignment
        # cho lecturer đối với offering này.
        exam = self.create_exam(offering)

        client = Client()
        client.force_login(lecturer.user)

        response = client.get(
            reverse(
                "teacher_exam_pdf",
                args=(exam.pk,),
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    # ==========================================================
    # 20. TEACHER RESULTS ONLY ASSIGNED CLASSES
    # ==========================================================

    def test_teacher_results_index_only_lists_assigned_classes(self):
        lecturer = self.create_profile(
            "results-lecturer",
            "lecturer",
        )

        other_lecturer = self.create_profile(
            "other-results-lecturer",
            "lecturer",
        )

        assigned_offering = self.create_active_offering(
            group_code="NMLT-ASSIGNED",
            session_number=1,
        )

        other_offering = self.create_active_offering(
            group_code="NMLT-OTHER",
            session_number=2,
        )

        TeachingAssignment.objects.create(
            course_offering=assigned_offering,
            lecturer=lecturer,
        )

        TeachingAssignment.objects.create(
            course_offering=other_offering,
            lecturer=other_lecturer,
        )

        assigned_exam = self.create_exam(
            assigned_offering
        )

        other_exam = Exam.objects.create(
            course=self.course,
            offering=other_offering,
            title="Đề lớp khác",
            duration_minutes=60,
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=2),
        )

        client = Client()
        client.force_login(lecturer.user)

        response = client.get(
            reverse(
                "teacher_results"
            )
        )

        self.assertContains(
            response,
            assigned_exam.title,
        )

        self.assertNotContains(
            response,
            other_exam.title,
        )

    # ==========================================================
    # 21. PROCTOR WARNING
    # ==========================================================

    def test_third_proctor_warning_stops_exam_and_grades_autosaved_answers(self):
        student = self.create_profile(
            "proctor-student",
            "student",
        )

        offering = self.create_active_offering(
            group_code="NMLT-PROCTOR",
            session_number=1,
        )

        Enrollment.objects.create(
            course_offering=offering,
            student=student,
        )

        exam = Exam.objects.create(
            course=self.course,
            offering=offering,
            title="Giám sát thi",
            duration_minutes=60,
            start_time=timezone.now() - timedelta(minutes=5),
            end_time=timezone.now() + timedelta(hours=1),
            question_data=[
                {
                    "type": "MCQ",
                    "content": "Câu tự lưu",
                    "score": 2,
                    "choices": [
                        {
                            "label": "A",
                            "text": "Đúng",
                        },
                        {
                            "label": "B",
                            "text": "Sai 1",
                        },
                        {
                            "label": "C",
                            "text": "Sai 2",
                        },
                        {
                            "label": "D",
                            "text": "Sai 3",
                        },
                    ],
                    "correct_answer": "A",
                }
            ],
        )

        client = Client()
        client.force_login(student.user)

        client.get(
            reverse(
                "take_exam",
                args=(exam.pk,),
            )
        )

        attempt = StudentExam.objects.get(
            student=student.user,
            exam=exam,
        )

        question = attempt.question_snapshot["questions"][0]

        correct_text = next(
            choice["text"]
            for choice in question["choices"]
            if choice.get("label") == "A"
        )

        autosave_response = client.post(
            reverse(
                "autosave_exam",
                args=(attempt.pk,),
            ),
            {
                f"question_{question['index']}":
                    correct_text,
            },
        )

        self.assertEqual(
            autosave_response.status_code,
            200,
        )

        attempt.warning_count = 2
        attempt.active_gesture = "looking_left"
        attempt.gesture_started_at = (
            timezone.now()
            - timedelta(seconds=31)
        )
        attempt.gesture_warned = False

        attempt.save(
            update_fields=[
                "warning_count",
                "active_gesture",
                "gesture_started_at",
                "gesture_warned",
            ]
        )

        frame = SimpleUploadedFile(
            "frame.jpg",
            b"frame-bytes",
            content_type="image/jpeg",
        )

        with patch(
            "firstApp.views.classify_frame",
            return_value=(
                "looking_left",
                0.91,
            ),
        ):
            response = client.post(
                reverse(
                    "proctor_exam_frame",
                    args=(attempt.pk,),
                ),
                {
                    "frame": frame
                },
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTrue(
            response.json()["terminated"]
        )

        attempt.refresh_from_db()

        self.assertTrue(
            attempt.is_submitted
        )

        self.assertTrue(
            attempt.is_terminated
        )

        self.assertEqual(
            attempt.warning_count,
            3,
        )

        self.assertEqual(
            attempt.score,
            2,
        )

        event = ProctorEvent.objects.get(
            student_exam=attempt
        )

        self.assertEqual(
            event.event_type,
            "looking_left",
        )

        self.assertTrue(
            event.evidence_image
        )

    # ==========================================================
    # 22. ATTENDANCE COMMAND
    # ==========================================================

    def test_attendance_command_requires_live_camera_and_20_minute_grace(self):
        student = self.create_profile(
            "attendance-student",
            "student",
        )

        offering = self.create_active_offering(
            group_code="NMLT-ATTENDANCE",
            session_number=1,
        )

        exam = Exam.objects.create(
            course=self.course,
            offering=offering,
            title="Điểm danh",
            duration_minutes=60,
            start_time=timezone.now() - timedelta(hours=1),
            end_time=timezone.now() + timedelta(hours=1),
        )

        session = ExamSession.objects.create(
            exam=exam,
            offering=offering,
            room="P.202",
            start_time=timezone.now() - timedelta(minutes=21),
            end_time=timezone.now() + timedelta(hours=1),
            status="ongoing",
        )

        computer = ExamComputer.objects.create(
            exam_session=session,
            computer_number=1,
            student=student,
            status="assigned",
            camera_last_seen_at=timezone.now(),
        )

        call_command(
            "check_exam_attendance",
            stdout=None,
        )

        computer.refresh_from_db()

        attempt = StudentExam.objects.get(
            student=student.user,
            exam=exam,
        )

        self.assertEqual(
            computer.status,
            "absent",
        )

        self.assertTrue(
            attempt.is_submitted
        )

        self.assertEqual(
            attempt.score,
            0,
        )

        self.assertEqual(
            attempt.exam_computer,
            computer,
        )

    # ==========================================================
    # 23. CAMERA PRESENCE
    # ==========================================================

    def test_camera_presence_endpoint_requires_ingest_token_and_updates_heartbeat(self):
        student = self.create_profile(
            "camera-presence-student",
            "student",
        )

        offering = self.create_active_offering(
            group_code="NMLT-CAMERA",
            session_number=1,
        )

        exam = Exam.objects.create(
            course=self.course,
            offering=offering,
            title="Ca thi camera",
            duration_minutes=60,
            start_time=timezone.now() - timedelta(minutes=5),
            end_time=timezone.now() + timedelta(hours=1),
        )

        session = ExamSession.objects.create(
            exam=exam,
            offering=offering,
            room="P.203",
            start_time=exam.start_time,
            end_time=exam.end_time,
        )

        computer = ExamComputer.objects.create(
            exam_session=session,
            computer_number=4,
            student=student,
            status="assigned",
        )

        client = Client()

        denied = client.post(
            reverse(
                "report_computer_presence"
            ),
            data=json.dumps(
                {
                    "computer_id": computer.pk,
                    "person_present": True,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(
            denied.status_code,
            503,
        )

        with override_settings(
            CV_INGEST_TOKEN="room-camera-secret"
        ):
            response = client.post(
                reverse(
                    "report_computer_presence"
                ),
                data=json.dumps(
                    {
                        "computer_id": computer.pk,
                        "person_present": True,
                    }
                ),
                content_type="application/json",
                HTTP_X_CV_TOKEN="room-camera-secret",
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        computer.refresh_from_db()

        self.assertIsNotNone(
            computer.camera_last_seen_at
        )

        self.assertIsNotNone(
            computer.presence_last_seen_at
        )

    # ==========================================================
    # 24. LECTURER CAN REOPEN ABSENT COMPUTER
    # ==========================================================

    def test_lecturer_can_reopen_only_assigned_absent_computer(self):
        lecturer = self.create_profile(
            "reopen-lecturer",
            "lecturer",
        )

        student = self.create_profile(
            "reopen-student",
            "student",
        )

        offering = self.create_active_offering(
            group_code="NMLT-REOPEN",
            session_number=1,
        )

        TeachingAssignment.objects.create(
            course_offering=offering,
            lecturer=lecturer,
        )

        exam = Exam.objects.create(
            course=self.course,
            offering=offering,
            title="Xem xét vắng",
            duration_minutes=60,
            start_time=timezone.now() - timedelta(minutes=5),
            end_time=timezone.now() + timedelta(hours=1),
        )

        session = ExamSession.objects.create(
            exam=exam,
            offering=offering,
            room="P.204",
            start_time=exam.start_time,
            end_time=exam.end_time,
        )

        computer = ExamComputer.objects.create(
            exam_session=session,
            computer_number=7,
            student=student,
            status="absent",
        )

        client = Client()
        client.force_login(lecturer.user)

        response = client.post(
            reverse(
                "reopen_exam_computer",
                args=(computer.pk,),
            )
        )

        self.assertRedirects(
            response,
            reverse(
                "teacher_exam_report",
                args=(exam.pk,),
            ),
        )

        computer.refresh_from_db()

        self.assertEqual(
            computer.status,
            "assigned",
        )

        self.assertEqual(
            computer.absence_reviewed_by,
            lecturer.user,
        )
class StudentExamProctoringControlTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(
            code="KTLT101",
            name="Kỹ thuật lập trình",
            faculty="CNTT",
        )

        self.term = AcademicTerm.objects.create(
            academic_year="2026-2027",
            semester_number=1,
            start_date=date(2026, 9, 1),
            end_date=date(2027, 1, 31),
        )

        self.offering = CourseOffering.objects.create(
            course=self.course,
            term=self.term,
            group_code="KTLT-CA1",
            session_number=1,
            classroom="P.101",
        )

        self.lecturer = User.objects.create_user(
            username="lecturer-control",
            password="test-password",
        )

        lecturer_profile = self.lecturer.userprofile
        lecturer_profile.role = "lecturer"
        lecturer_profile.save()

        TeachingAssignment.objects.create(
            course_offering=self.offering,
            lecturer=lecturer_profile,
        )

        self.student = User.objects.create_user(
            username="student-control",
            password="test-password",
        )

        student_profile = self.student.userprofile
        student_profile.role = "student"
        student_profile.save()

        Enrollment.objects.create(
            course_offering=self.offering,
            student=student_profile,
        )

        self.exam = Exam.objects.create(
            course=self.course,
            offering=self.offering,
            title="Bài kiểm tra Proctoring",
            start_time=timezone.now() - timedelta(minutes=10),
            end_time=timezone.now() + timedelta(hours=1),
        )

        self.student_exam = StudentExam.objects.create(
            student=self.student,
            exam=self.exam,
            warning_count=3,
            is_locked=True,
            lock_reason="Đã đạt 3 lần cảnh báo.",
            locked_at=timezone.now(),
        )

    def test_lecturer_can_allow_locked_student_exam(self):
        self.client.force_login(self.lecturer)

        response = self.client.post(
            reverse(
                "teacher_allow_student_exam",
                args=(self.student_exam.pk,),
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )
        self.assertEqual(
            response.url,
            reverse("teacher_monitor"),
        )
        self.student_exam.refresh_from_db()

        self.assertFalse(
            self.student_exam.is_locked
        )

        self.assertEqual(
            self.student_exam.warning_count,
            0,
        )

        self.assertEqual(
            self.student_exam.unlock_count,
            1,
        )

    def test_lecturer_can_terminate_locked_student_exam(self):
        self.client.force_login(self.lecturer)

        response = self.client.post(
            reverse(
                "teacher_terminate_student_exam",
                args=(self.student_exam.pk,),
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )
        self.assertEqual(
            response.url,
            reverse("teacher_monitor"),
        )
        self.student_exam.refresh_from_db()

        self.assertTrue(
            self.student_exam.is_submitted
        )

        self.assertTrue(
            self.student_exam.is_terminated
        )

    def test_student_cannot_allow_student_exam(self):
        self.client.force_login(self.student)

        response = self.client.post(
            reverse(
                "teacher_allow_student_exam",
                args=(self.student_exam.pk,),
            )
        )

        self.assertIn(
            response.status_code,
            (302, 403),
        )

        self.student_exam.refresh_from_db()

        self.assertTrue(
            self.student_exam.is_locked
        )

    def test_student_exam_status_owner_can_read(self):
        self.student_exam.is_locked = True
        self.student_exam.warning_count = 3
        self.student_exam.save(
            update_fields=[
                "is_locked",
                "warning_count",
            ]
        )

        self.client.force_login(self.student_exam.student)

        response = self.client.get(
            reverse(
                "student_exam_status",
                args=[self.student_exam.id],
            )
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertTrue(data["success"])
        self.assertTrue(data["is_locked"])
        self.assertEqual(data["warning_count"], 3)
        self.assertFalse(data["is_submitted"])
        self.assertFalse(data["is_terminated"])

    def test_student_exam_status_other_student_cannot_read(self):
        other_student = User.objects.create_user(
            username="other_student",
            password="test123",
        )

        self.client.force_login(other_student)

        response = self.client.get(
            reverse(
                "student_exam_status",
                args=[self.student_exam.id],
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_student_can_start_screen_sharing_when_unlocked(self):
        self.student_exam.is_locked = False
        self.student_exam.save(update_fields=["is_locked"])

        self.client.force_login(self.student)

        response = self.client.post(
            reverse(
                "start_screen_sharing",
                args=[self.student_exam.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

        self.student_exam.refresh_from_db()
        self.assertTrue(self.student_exam.is_screen_sharing)

        self.assertEqual(
            ProctorEvent.objects.filter(
                student_exam=self.student_exam,
                event_type="screen_share_started",
            ).count(),
            1,
        )

    def test_student_cannot_start_screen_sharing_when_locked(self):
        self.client.force_login(self.student)

        response = self.client.post(
            reverse(
                "start_screen_sharing",
                args=[self.student_exam.pk],
            )
        )

        self.assertEqual(response.status_code, 423)
        self.assertEqual(
            response.json()["code"],
            "exam_locked",
        )

        self.student_exam.refresh_from_db()
        self.assertFalse(self.student_exam.is_screen_sharing)

    def test_other_student_cannot_start_screen_sharing(self):
        other_student = User.objects.create_user(
            username="other-screen-student",
            password="test-password",
        )

        self.client.force_login(other_student)

        response = self.client.post(
            reverse(
                "start_screen_sharing",
                args=[self.student_exam.pk],
            )
        )

        self.assertEqual(response.status_code, 404)

        self.student_exam.refresh_from_db()
        self.assertFalse(self.student_exam.is_screen_sharing)

    def test_start_screen_sharing_is_idempotent(self):
        self.student_exam.is_locked = False
        self.student_exam.save(update_fields=["is_locked"])

        self.client.force_login(self.student)

        url = reverse(
            "start_screen_sharing",
            args=[self.student_exam.pk],
        )

        first_response = self.client.post(url)
        second_response = self.client.post(url)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)

        self.assertEqual(
            ProctorEvent.objects.filter(
                student_exam=self.student_exam,
                event_type="screen_share_started",
            ).count(),
            1,
        )

    def test_student_cannot_start_screen_sharing_after_submission(self):
        self.student_exam.is_locked = False
        self.student_exam.is_submitted = True
        self.student_exam.save(
            update_fields=["is_locked", "is_submitted"]
        )

        self.client.force_login(self.student)

        response = self.client.post(
            reverse(
                "start_screen_sharing",
                args=[self.student_exam.pk],
            )
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["code"],
            "exam_submitted",
        )

    def test_student_cannot_start_screen_sharing_after_termination(self):
        self.student_exam.is_locked = False
        self.student_exam.is_terminated = True
        self.student_exam.save(
            update_fields=["is_locked", "is_terminated"]
        )

        self.client.force_login(self.student)

        response = self.client.post(
            reverse(
                "start_screen_sharing",
                args=[self.student_exam.pk],
            )
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["code"],
            "exam_terminated",
        )

    def test_other_student_cannot_stop_screen_sharing(self):
        self.student_exam.is_screen_sharing = True
        self.student_exam.save(
            update_fields=["is_screen_sharing"]
        )

        other_student = User.objects.create_user(
            username="other-stop-screen-student",
            password="test-password",
        )

        self.client.force_login(other_student)

        response = self.client.post(
            reverse(
                "stop_screen_sharing",
                args=[self.student_exam.pk],
            )
        )

        self.assertEqual(response.status_code, 404)

        self.student_exam.refresh_from_db()
        self.assertTrue(self.student_exam.is_screen_sharing)

    def test_stopping_already_stopped_screen_sharing_does_not_duplicate_event(self):
        self.student_exam.is_screen_sharing = False
        self.student_exam.save(
            update_fields=["is_screen_sharing"]
        )

        self.client.force_login(self.student)

        response = self.client.post(
            reverse(
                "stop_screen_sharing",
                args=[self.student_exam.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertFalse(response.json()["is_screen_sharing"])

        self.assertEqual(
            ProctorEvent.objects.filter(
                student_exam=self.student_exam,
                event_type="screen_share_stopped",
            ).count(),
            0,
        )


    @patch("firstApp.views.run_cpp")
    def test_run_code_rejects_locked_exam_before_compilation(
        self,
        mock_run_cpp,
    ):
        self.student_exam.is_locked = True
        self.student_exam.is_submitted = False
        self.student_exam.is_terminated = False
        self.student_exam.save(
            update_fields=[
                "is_locked",
                "is_submitted",
                "is_terminated",
            ]
        )

        self.client.force_login(self.student)

        response = self.client.post(
            reverse("run_code"),
            data=json.dumps({
                "student_exam_id": self.student_exam.pk,
                "question_id": 1,
                "code": "int main() { return 0; }",
            }),
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            423,
            response.content.decode("utf-8"),
        )
        self.assertEqual(
            response.json()["code"],
            "exam_locked",
        )

        mock_run_cpp.assert_not_called()


    @patch("firstApp.views.run_cpp")
    def test_run_code_rejects_terminated_exam_before_compilation(
        self,
        mock_run_cpp,
    ):
        self.student_exam.is_locked = False
        self.student_exam.is_submitted = False
        self.student_exam.is_terminated = True
        self.student_exam.save(
            update_fields=[
                "is_locked",
                "is_submitted",
                "is_terminated",
            ]
        )

        self.client.force_login(self.student)

        response = self.client.post(
            reverse("run_code"),
            data=json.dumps({
                "student_exam_id": self.student_exam.pk,
                "question_id": 1,
                "code": "int main() { return 0; }",
            }),
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            409,
            response.content.decode("utf-8"),
        )
        self.assertEqual(
            response.json()["code"],
            "exam_terminated",
        )

        mock_run_cpp.assert_not_called()


    @patch("firstApp.views.run_cpp")
    def test_run_code_rejects_submitted_exam_before_compilation(
        self,
        mock_run_cpp,
    ):
        self.student_exam.is_locked = False
        self.student_exam.is_submitted = True
        self.student_exam.is_terminated = False
        self.student_exam.save(
            update_fields=[
                "is_locked",
                "is_submitted",
                "is_terminated",
            ]
        )

        self.client.force_login(self.student)

        response = self.client.post(
            reverse("run_code"),
            data=json.dumps({
                "student_exam_id": self.student_exam.pk,
                "question_id": 1,
                "code": "int main() { return 0; }",
            }),
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            409,
            response.content.decode("utf-8"),
        )
        self.assertEqual(
            response.json()["code"],
            "exam_submitted",
        )
        mock_run_cpp.assert_not_called()

    @patch(
        "firstApp.views.run_cpp",
        return_value={
            "status": "Success",
            "stdout": "2",
            "stderr": "",
        },
    )
    def test_run_code_still_works_when_exam_is_active(self, mock_run_cpp):
        self.student_exam.is_locked = False
        self.student_exam.is_terminated = False
        self.student_exam.question_snapshot = {
            "questions": [
                {
                    "index": 1,
                    "type": "CODE",
                    "score": 1,
                    "test_cases": [
                        {
                            "input_data": "",
                            "expected_output": "2",
                            "score": 1,
                        }
                    ],
                }
            ]
        }
        self.student_exam.save(
            update_fields=[
                "is_locked",
                "is_terminated",
                "question_snapshot",
            ]
        )

        self.client.force_login(self.student)

        response = self.client.post(
            reverse("run_code"),
            data=json.dumps({
                "student_exam_id": self.student_exam.pk,
                "question_id": 1,
                "code": "int main() { return 0; }",
            }),
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            200,
            response.content.decode("utf-8"),
        )
        self.assertTrue(response.json()["success"])
        mock_run_cpp.assert_called_once()

    def test_autosave_rejects_locked_exam(self):
        self.client.force_login(self.student)

        response = self.client.post(
            reverse(
                "autosave_exam",
                args=[self.student_exam.pk],
            ),
            {"question_1": "A"},
        )

        self.assertEqual(response.status_code, 423)
        self.assertEqual(
            response.json()["code"],
            "exam_locked",
        )

        self.assertFalse(
            StudentAnswer.objects.filter(
                student_exam=self.student_exam,
            ).exists()
        )

    def test_autosave_rejects_terminated_exam(self):
        self.student_exam.is_locked = False
        self.student_exam.is_terminated = True
        self.student_exam.save(
            update_fields=[
                "is_locked",
                "is_terminated",
            ]
        )

        self.client.force_login(self.student)

        response = self.client.post(
            reverse(
                "autosave_exam",
                args=[self.student_exam.pk],
            ),
            {"question_1": "A"},
        )

        self.assertEqual(response.status_code, 409)

        self.assertFalse(
            StudentAnswer.objects.filter(
                student_exam=self.student_exam,
            ).exists()
        )

    def test_autosave_saves_answer_when_exam_is_active(self):
        self.student_exam.is_locked = False
        self.student_exam.is_terminated = False
        self.student_exam.question_snapshot = {
            "questions": [
                {
                    "index": 1,
                    "type": "MCQ",
                    "score": 1,
                    "choices": [
                        {"id": "A", "text": "Đáp án A"},
                        {"id": "B", "text": "Đáp án B"},
                    ],
                }
            ]
        }
        self.student_exam.save(
            update_fields=[
                "is_locked",
                "is_terminated",
                "question_snapshot",
            ]
        )

        self.client.force_login(self.student)

        response = self.client.post(
            reverse(
                "autosave_exam",
                args=[self.student_exam.pk],
            ),
            {"question_1": "A"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertEqual(response.json()["saved_count"], 1)

        answer = StudentAnswer.objects.get(
            student_exam=self.student_exam,
            question_index=1,
        )

        self.assertEqual(answer.answer_text, "A")
        self.assertEqual(answer.question_type, "MCQ")

    def test_submit_exam_does_not_submit_locked_exam(self):
        self.client.force_login(self.student)

        response = self.client.post(
            reverse(
                "submit_exam",
                args=[self.student_exam.pk],
            ),
            {},
        )

        self.assertEqual(response.status_code, 302)

        self.student_exam.refresh_from_db()

        self.assertTrue(self.student_exam.is_locked)
        self.assertFalse(self.student_exam.is_submitted)



    def test_submit_exam_does_not_grade_terminated_exam(self):
        self.student_exam.is_locked = False
        self.student_exam.is_submitted = False
        self.student_exam.is_terminated = True
        self.student_exam.save(
            update_fields=[
                "is_locked",
                "is_submitted",
                "is_terminated",
            ]
        )

        self.client.force_login(self.student)

        with patch(
            "firstApp.views._grade_student_exam"
        ) as mock_grade:
            response = self.client.post(
                reverse(
                    "submit_exam",
                    args=[self.student_exam.pk],
                ),
                {},
            )

        self.assertEqual(response.status_code, 302)

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertEqual(
            response.url,
            reverse(
                "exam_result",
                args=[self.student_exam.pk],
            ),
        )

        mock_grade.assert_not_called()

        self.student_exam.refresh_from_db()

        self.assertTrue(self.student_exam.is_terminated)
        self.assertFalse(self.student_exam.is_submitted)


    def test_submitting_exam_twice_does_not_regrade(self):
        self.student_exam.is_locked = False
        self.student_exam.question_snapshot = {
            "questions": [
                {
                    "index": 1,
                    "type": "MCQ",
                    "score": 1,
                    "correct_answer": "A",
                    "choices": [
                        {
                            "id": "A",
                            "index": 1,
                            "label": "A",
                            "text": "Đáp án A",
                        },
                        {
                            "id": "B",
                            "index": 2,
                            "label": "B",
                            "text": "Đáp án B",
                        },
                    ],
                }
            ]
        }
        self.student_exam.save(
            update_fields=[
                "is_locked",
                "question_snapshot",
            ]
        )

        self.client.force_login(self.student)

        url = reverse(
            "submit_exam",
            args=[self.student_exam.pk],
        )

        first_response = self.client.post(
            url,
            {"question_1": "A"},
        )

        self.assertEqual(first_response.status_code, 302)

        self.student_exam.refresh_from_db()

        self.assertTrue(self.student_exam.is_submitted)
        self.assertEqual(self.student_exam.score, 1.0)

        answer_count_before = StudentAnswer.objects.filter(
            student_exam=self.student_exam,
        ).count()

        score_before = self.student_exam.score

        second_response = self.client.post(
            url,
            {"question_1": "B"},
        )

        self.assertEqual(second_response.status_code, 302)
        self.assertEqual(
            second_response.url,
            reverse(
                "exam_result",
                kwargs={
                    "student_exam_id": self.student_exam.pk,
                },
            ),
        )

        self.student_exam.refresh_from_db()

        self.assertEqual(self.student_exam.score, score_before)
        self.assertEqual(
            StudentAnswer.objects.filter(
                student_exam=self.student_exam,
            ).count(),
            answer_count_before,
        )

        answer = StudentAnswer.objects.get(
            student_exam=self.student_exam,
            question_index=1,
        )

        self.assertEqual(answer.answer_text, "Đáp án A")

    def test_autosave_cannot_modify_submitted_exam(self):
        self.student_exam.is_locked = False
        self.student_exam.is_submitted = True
        self.student_exam.save(
            update_fields=[
                "is_locked",
                "is_submitted",
            ]
        )

        StudentAnswer.objects.create(
            student_exam=self.student_exam,
            question_index=1,
            question_type="MCQ",
            answer_text="A",
            answer_payload={"choice_index": "A"},
            score=1.0,
            is_correct=True,
        )

        self.client.force_login(self.student)

        response = self.client.post(
            reverse(
                "autosave_exam",
                args=[self.student_exam.pk],
            ),
            {"question_1": "B"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["code"],
            "exam_submitted",
        )
        answer = StudentAnswer.objects.get(
            student_exam=self.student_exam,
            question_index=1,
        )

        self.assertEqual(answer.answer_text, "A")
        self.assertEqual(answer.score, 1.0)
        self.assertTrue(answer.is_correct)

    def test_submit_exam_rejects_another_students_attempt(self):
        self.student_exam.is_locked = False
        self.student_exam.is_submitted = False
        self.student_exam.is_terminated = False
        self.student_exam.save(
            update_fields=[
                "is_locked",
                "is_submitted",
                "is_terminated",
            ]
        )

        other_student = User.objects.create_user(
            username="other-student-submit",
            password="test-password",
        )
        self.client.force_login(other_student)

        with patch("firstApp.views._grade_student_exam") as mock_grade:
            response = self.client.post(
                reverse(
                    "submit_exam",
                    args=[self.student_exam.pk],
                ),
                {"question_1": "A"},
            )

        self.assertEqual(response.status_code, 404)
        mock_grade.assert_not_called()

        self.student_exam.refresh_from_db()
        self.assertFalse(self.student_exam.is_submitted)

    def test_autosave_rejects_another_students_attempt(self):
        self.student_exam.is_locked = False
        self.student_exam.is_submitted = False
        self.student_exam.is_terminated = False
        self.student_exam.question_snapshot = {
            "questions": [
                {
                    "index": 1,
                    "type": "MCQ",
                    "score": 1,
                    "choices": [
                        {"id": "A", "text": "Đáp án A"},
                        {"id": "B", "text": "Đáp án B"},
                    ],
                }
            ]
        }
        self.student_exam.save(
            update_fields=[
                "is_locked",
                "is_submitted",
                "is_terminated",
                "question_snapshot",
            ]
        )

        other_student = User.objects.create_user(
            username="other-student-autosave",
            password="test-password",
        )
        self.client.force_login(other_student)

        response = self.client.post(
            reverse(
                "autosave_exam",
                args=[self.student_exam.pk],
            ),
            {"question_1": "A"},
        )

        self.assertEqual(response.status_code, 404)

        self.assertFalse(
            StudentAnswer.objects.filter(
                student_exam=self.student_exam,
            ).exists()
        )

    @patch(
        "firstApp.views.run_cpp",
        return_value={
            "status": "Success",
            "stdout": "2",
            "stderr": "",
        },
    )
    def test_run_code_rejects_another_students_attempt(
            self,
            mock_run_cpp,
    ):
        self.student_exam.is_locked = False
        self.student_exam.is_submitted = False
        self.student_exam.is_terminated = False
        self.student_exam.question_snapshot = {
            "questions": [
                {
                    "index": 1,
                    "type": "CODE",
                    "score": 1,
                    "test_cases": [
                        {
                            "input_data": "",
                            "expected_output": "2",
                            "score": 1,
                        }
                    ],
                }
            ]
        }
        self.student_exam.save(
            update_fields=[
                "is_locked",
                "is_submitted",
                "is_terminated",
                "question_snapshot",
            ]
        )

        other_student = User.objects.create_user(
            username="other-student-code",
            password="test-password",
        )
        self.client.force_login(other_student)

        response = self.client.post(
            reverse("run_code"),
            data=json.dumps({
                "student_exam_id": self.student_exam.pk,
                "question_id": 1,
                "code": "int main() { return 0; }",
            }),
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            404,
            response.content.decode("utf-8"),
        )
        mock_run_cpp.assert_not_called()

    def test_qr_login_invalid_json_returns_safe_error(self):
        response = self.client.post(
            reverse("verify_qr_login"),
            data="{",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["status"],
            "error",
        )
        self.assertEqual(
            response.json()["message"],
            "Dữ liệu đăng nhập không hợp lệ.",
        )

    def test_qr_login_valid_token_creates_session(self):
        user = User.objects.create_user(
            username="qr-student-valid",
            password="safe-test-password",
        )
        profile = user.userprofile
        profile.role = "student"
        profile.save()

        response = self.client.post(
            reverse("verify_qr_login"),
            data=json.dumps({
                "qr_token": str(profile.qr_token),
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(
            str(self.client.session["_auth_user_id"]),
            str(user.pk),
        )

    def test_qr_login_invalid_token_does_not_create_session(self):
        response = self.client.post(
            reverse("verify_qr_login"),
            data=json.dumps({
                "qr_token": "invalid-qr-token",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "error")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_qr_login_inactive_user_is_rejected(self):
        user = User.objects.create_user(
            username="qr-student-inactive",
            password="safe-test-password",
            is_active=False,
        )
        profile = user.userprofile
        profile.role = "student"
        profile.save()

        response = self.client.post(
            reverse("verify_qr_login"),
            data=json.dumps({
                "qr_token": str(profile.qr_token),
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "error")
        self.assertNotIn("_auth_user_id", self.client.session)




class FaceLoginSecurityTests(TestCase):
    """Kiểm thử các trường hợp xác thực đăng nhập khuôn mặt."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="face-student-01",
            password="safe-test-password",
        )
        self.profile = self.user.userprofile

        # Vector mẫu 512 chiều: chiều đầu tiên bằng 1.
        self.embedding = [1.0] + [0.0] * 511

        # Tạo ảnh PNG hợp lệ để kiểm thử khâu đọc ảnh.
        from PIL import Image

        image_buffer = BytesIO()
        Image.new("RGB", (160, 160), color="white").save(
            image_buffer,
            format="PNG",
        )

        encoded_image = base64.b64encode(
            image_buffer.getvalue()
        ).decode("ascii")

        self.image_data = "data:image/png;base64," + encoded_image

    def create_face_profile(
        self,
        user_profile,
        embedding=None,
        is_active=True,
    ):
        return FaceProfile.objects.create(
            user_profile=user_profile,
            embedding=embedding or self.embedding,
            model_name="Facenet512",
            detector_backend="opencv",
            is_active=is_active,
            consented_at=timezone.now(),
        )

    def post_face_login(self, consent=True):
        return self.client.post(
            reverse("verify_face_login"),
            data=json.dumps({
                "consent": consent,
                "image": self.image_data,
            }),
            content_type="application/json",
        )

    def test_login_rejects_missing_consent(self):
        response = self.post_face_login(consent=False)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_rejects_when_no_face_profile_exists(self):
        from unittest.mock import patch

        with patch(
            "deepface.DeepFace.represent",
            return_value=[{"embedding": self.embedding}],
        ):
            response = self.post_face_login()

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_rejects_inactive_face_profile(self):
        self.create_face_profile(
            self.profile,
            is_active=False,
        )

        from unittest.mock import patch

        with patch(
            "deepface.DeepFace.represent",
            return_value=[{"embedding": self.embedding}],
        ):
            response = self.post_face_login()

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_rejects_non_matching_face(self):
        different_embedding = [0.0, 1.0] + [0.0] * 510

        self.create_face_profile(
            self.profile,
            embedding=different_embedding,
        )

        from unittest.mock import patch

        with patch(
            "deepface.DeepFace.represent",
            return_value=[{"embedding": self.embedding}],
        ):
            response = self.post_face_login()

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_rejects_ambiguous_matching_faces(self):
        self.create_face_profile(self.profile)

        second_user = User.objects.create_user(
            username="face-student-02",
            password="safe-test-password",
        )

        self.create_face_profile(second_user.userprofile)

        from unittest.mock import patch

        with patch(
            "deepface.DeepFace.represent",
            return_value=[{"embedding": self.embedding}],
        ):
            response = self.post_face_login()

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_succeeds_for_matching_face(self):
        self.create_face_profile(self.profile)

        from unittest.mock import patch

        with patch(
            "deepface.DeepFace.represent",
            return_value=[{"embedding": self.embedding}],
        ):
            response = self.post_face_login()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertEqual(
            response.json()["redirect_url"],
            "/",
        )

        self.assertEqual(
            str(self.client.session["_auth_user_id"]),
            str(self.user.pk),
        )

    def setUp(self):
        from django.core.cache import cache

        cache.clear()

        self.user = User.objects.create_user(
            username="face-student-01",
            password="safe-test-password",
        )
        self.profile = self.user.userprofile
        self.embedding = [1.0] + [0.0] * 511

        from PIL import Image

        image_buffer = BytesIO()
        Image.new("RGB", (160, 160), color="white").save(
            image_buffer, format="PNG"
        )

        encoded_image = base64.b64encode(
            image_buffer.getvalue()
        ).decode("ascii")

        self.image_data = "data:image/png;base64," + encoded_image

    def test_login_rate_limit_returns_429_after_five_requests(self):
        from unittest.mock import patch

        self.create_face_profile(self.profile)

        with patch(
                "deepface.DeepFace.represent",
                return_value=[{"embedding": self.embedding}],
        ):
            responses = [
                self.post_face_login()
                for _ in range(6)
            ]

        # Năm yêu cầu đầu được xử lý bình thường.
        for response in responses[:5]:
            self.assertEqual(response.status_code, 200)

        # Yêu cầu thứ sáu vượt giới hạn 5 yêu cầu/phút.
        self.assertEqual(responses[5].status_code, 429)
        self.assertFalse(responses[5].json()["success"])

