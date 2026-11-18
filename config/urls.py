# """
# URL configuration for config project.
#
# The `urlpatterns` list routes URLs to views. For more information please see:
#     https://docs.djangoproject.com/en/5.2/topics/http/urls/
# Examples:
# Function views
#     1. Add an import:  from my_app import views
#     2. Add a URL to urlpatterns:  path('', views.home, name='home')
# Class-based views
#     1. Add an import:  from other_app.views import Home
#     2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
# Including another URLconf
#     1. Import the includes() function: from django.urls import includes, path
#     2. Add a URL to urlpatterns:  path('blog/', includes('blog.urls'))
# """
# from django.contrib import admin
# from django.contrib.auth.views import LogoutView
# from django.urls import path
# from firstApp import views
#
# from django.conf import settings
# from django.conf.urls.static import static
#
# urlpatterns = [
#     path('admin/', admin.site.urls),
#     path("", views.index, name="home"),
#     # URL cho chức năng quét QR
#     path("login/", views.qr_login_page, name="qr_login_page"),
#     path("api/verify-qr/", views.verify_qr_login, name="verify_qr_login"),
#     path('logout/', LogoutView.as_view(next_page='home'), name='logout'), # <-- Thêm đường dẫn đăng xuất
#     path('profile/', views.profile_view, name='profile'),
#     path('courses/', views.course_list_view, name='course_list'),
#     path('exam/<int:exam_id>/', views.take_exam_view, name='take_exam'),
#     path("api/run/",views.run_code,name="run_code"),
#     path("compiler/",views.compiler_test,name="compiler_test"),
# ]
# if settings.DEBUG:
#     urlpatterns += static(
#         settings.MEDIA_URL,
#         document_root=settings.MEDIA_ROOT
#     )

"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the includes() function: from django.urls import includes, path
    2. Add a URL to urlpatterns:  path('blog/', includes('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import path
from firstApp import views

from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", views.index, name="home"),

    # URL cho chức năng quét QR và tài khoản
    path("login/", views.qr_login_page, name="qr_login_page"),
    path("api/verify-qr/", views.verify_qr_login, name="verify_qr_login"),
    path("api/verify-face/",views.verify_face_login,name="verify_face_login",),
    path('logout/', LogoutView.as_view(next_page='home'), name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path("api/register-face/",views.register_face,name="register_face",),
    # Đăng ký và kích hoạt TOTP
    path("api/totp/setup/",views.totp_setup,name="totp_setup",),
    path("api/totp/confirm/",views.totp_confirm,name="totp_confirm",),
    path("api/verify-totp/",views.verify_totp_login,name="verify_totp_login",),
    # Khóa học
    path('courses/', views.course_list_view, name='course_list'),

    # Bài thi và Chấm điểm (Khớp đúng tên hàm trong views.py)
    path('exams/', views.exam_list_view, name='exam_list'),
    path('exam/<int:exam_id>/', views.take_exam_view, name='take_exam'),
    path('exams/submit/<int:student_exam_id>/', views.submit_exam, name='submit_exam'),
    path('exams/autosave/<int:student_exam_id>/', views.autosave_exam, name='autosave_exam'),
    path('api/proctor/frame/<int:student_exam_id>/', views.proctor_exam_frame, name='proctor_exam_frame'),
    path('api/cv/presence/', views.report_computer_presence, name='report_computer_presence'),
    path('exams/result/<int:student_exam_id>/', views.exam_result_view, name='exam_result'),
    path('exams/results/', views.exam_result_list_view, name='exam_result_list'),

    # Giao diện quản lý của Giảng viên
    path('teacher/exams/<int:exam_id>/submissions/', views.teacher_exam_submissions, name='teacher_exam_submissions'),
    path('teacher/exams/<int:exam_id>/report/', views.lecturer_exam_report, name='teacher_exam_report'),
    path('teacher/exams/<int:exam_id>/report.pdf', views.teacher_exam_pdf, name='teacher_exam_pdf'),
    path('teacher/submissions/<int:student_exam_id>/', views.teacher_view_student_detail, name='teacher_view_student_detail'),
    path('teacher/results/', views.teacher_results_view, name='teacher_results'),
    path('teacher/computers/<int:computer_id>/reopen/', views.reopen_exam_computer, name='reopen_exam_computer'),
    path('teacher/proctor-events/<int:event_id>/review/', views.review_proctor_event, name='review_proctor_event'),
    path('teacher/student-exams/<int:student_exam_id>/allow/',views.teacher_allow_student_exam,name='teacher_allow_student_exam',),
    path('teacher/student-exams/<int:student_exam_id>/terminate/',views.teacher_terminate_student_exam,name='teacher_terminate_student_exam',),
    path('exams/status/<int:student_exam_id>/',views.student_exam_status,name='student_exam_status',),
    path('exams/proctor/violation/<int:student_exam_id>/',views.report_proctor_violation, name='report_proctor_violation',),
    path("teacher/face-attendance/",views.face_attendance_view,name="face_attendance",),
    path("api/teacher/face-attendance/<int:exam_id>/",views.verify_face_attendance,name="verify_face_attendance",),
    path("teacher/face-attendance/<int:exam_id>/",views.face_attendance_exam_view,name="face_attendance_exam",),
    path("exams/screen-share/<int:student_exam_id>/start/",views.start_screen_sharing,name="start_screen_sharing",),
    path("exams/screen-share/<int:student_exam_id>/stop/",views.stop_screen_sharing,name="stop_screen_sharing",),

    path("teacher/monitor/",views.teacher_monitor_view,name="teacher_monitor",),
    path("teacher/monitor/data/",views.teacher_monitor_data,name="teacher_monitor_data",),

    # Quản lý phiên bản đề thi
    path("teacher/exams/<int:exam_id>/papers/",views.teacher_exam_papers, name="teacher_exam_papers",),
    path("teacher/exams/<int:exam_id>/papers/create/",views.teacher_create_exam_paper,name="teacher_create_exam_paper",),
    path("teacher/exams/<int:exam_id>/papers/<int:paper_id>/edit/",views.teacher_edit_exam_paper,name="teacher_edit_exam_paper",),
    path("teacher/exams/<int:exam_id>/papers/<int:paper_id>/copy/",views.teacher_copy_exam_paper, name="teacher_copy_exam_paper",),
    path("teacher/exams/<int:exam_id>/papers/<int:paper_id>/delete/",views.teacher_delete_exam_paper,name="teacher_delete_exam_paper",),
    path("teacher/exams/<int:exam_id>/assignments/",views.teacher_exam_assignments,name="teacher_exam_assignments",),
    path("teacher/exams/<int:exam_id>/assignments/<int:assignment_id>/edit/",views.teacher_edit_exam_assignment,name="teacher_edit_exam_assignment",),
    path("teacher/exams/<int:exam_id>/assignments/<int:assignment_id>/delete/",views.teacher_delete_exam_assignment, name="teacher_delete_exam_assignment",),
    # Công cụ chạy thử code
    path("api/run/", views.run_code, name="run_code"),
    path("compiler/", views.compiler_test, name="compiler_test"),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )