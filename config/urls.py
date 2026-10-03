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
    path('logout/', LogoutView.as_view(next_page='home'), name='logout'),
    path('profile/', views.profile_view, name='profile'),

    # Khóa học
    path('courses/', views.course_list_view, name='course_list'),

    # Bài thi & Chấm điểm (Khớp đúng tên hàm trong views.py)
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

    # Công cụ chạy thử code
    path("api/run/", views.run_code, name="run_code"),
    path("compiler/", views.compiler_test, name="compiler_test"),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )