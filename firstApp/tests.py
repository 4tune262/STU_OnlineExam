from datetime import date, timedelta
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import AcademicTerm, Course, CourseOffering, Exam


class AcademicStructureTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_directory = TemporaryDirectory()
        cls.settings_override = override_settings(MEDIA_ROOT=cls.media_directory.name)
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

    def create_profile(self, username, role):
        user = User.objects.create_user(username=username, password="safe-test-password")
        profile = user.userprofile
        profile.role = role
        profile.save()
        return profile

    def create_exam(self, offering):
        return Exam.objects.create(
            course=self.course,
            offering=offering,
            title="Kiểm tra giữa kỳ",
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=2),
        )

    def test_term_rejects_end_date_before_start_date(self):
        term = AcademicTerm(
            academic_year="2027-2028",
            semester_number=1,
            start_date=date(2027, 9, 1),
            end_date=date(2027, 8, 31),
        )

        with self.assertRaises(ValidationError):
            term.full_clean()

    def test_offering_supports_multiple_lecturers_and_mixed_class_students(self):
        lecturer_one = self.create_profile("lecturer-one", "lecturer")
        lecturer_two = self.create_profile("lecturer-two", "lecturer")
        student_one = self.create_profile("student-one", "student")
        student_two = self.create_profile("student-two", "student")
        offering = CourseOffering.objects.create(
            course=self.course,
            term=self.term,
            group_code="NMLT-CA2",
            session_number=2,
            classroom="P.206",
        )

        offering.lecturers.add(lecturer_one, lecturer_two)
        offering.students.add(student_one, student_two)

        self.assertCountEqual(
            offering.lecturers.all(),
            (lecturer_one, lecturer_two),
        )
        self.assertCountEqual(
            offering.students.all(),
            (student_one, student_two),
        )

    def test_lecturer_role_receives_full_django_admin_permissions(self):
        lecturer = self.create_profile("lecturer-admin", "lecturer")
        lecturer.user.refresh_from_db()

        self.assertTrue(lecturer.user.is_staff)
        self.assertTrue(lecturer.user.has_perm("auth.view_user"))
        self.assertTrue(lecturer.user.has_perm("firstApp.add_academicterm"))

        client = Client()
        client.force_login(lecturer.user)
        response = client.get(reverse("admin:firstApp_academicterm_changelist"))

        self.assertEqual(response.status_code, 200)

    def test_student_cannot_open_exam_for_another_offering(self):
        enrolled_student = self.create_profile("enrolled-student", "student")
        other_student = self.create_profile("other-student", "student")
        offering = CourseOffering.objects.create(
            course=self.course,
            term=self.term,
            group_code="NMLT-CA1",
            session_number=1,
        )
        offering.students.add(enrolled_student)
        exam = self.create_exam(offering)
        client = Client()
        client.force_login(other_student.user)

        response = client.get(reverse("take_exam", args=(exam.pk,)))

        self.assertEqual(response.status_code, 404)

    def test_student_sees_only_assigned_offering_exams(self):
        enrolled_student = self.create_profile("exam-student", "student")
        other_student = self.create_profile("unassigned-student", "student")
        offering = CourseOffering.objects.create(
            course=self.course,
            term=self.term,
            group_code="NMLT-CA3",
            session_number=3,
        )
        offering.students.add(enrolled_student)
        exam = self.create_exam(offering)
        client = Client()
        client.force_login(enrolled_student.user)

        response = client.get(reverse("exam_list"))
        self.assertContains(response, exam.title)

        client.force_login(other_student.user)
        response = client.get(reverse("exam_list"))
        self.assertNotContains(response, exam.title)
