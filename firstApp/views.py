# import json
#
#
# from django.contrib import messages
# from django.contrib.auth.decorators import login_required
# from django.shortcuts import render, redirect
# from django.http import JsonResponse
# from django.contrib.auth import login
# from .models import UserProfile
# import random
# import json
#
# from compiler.run import run_cpp
# def index(request):
#     return render(request, "index.html")
#
#
# def qr_login_page(request):
#     # Nếu user đã đăng nhập, chuyển thẳng vào trang chủ/trang thi
#     if request.user.is_authenticated:
#         return redirect('home')
#     return render(request, "login.html", {'title': 'Đăng nhập Sinh viên'})
#
#
# def verify_qr_login(request):
#     """API endpoint để frontend gửi mã QR lên kiểm tra"""
#     if request.method == 'POST':
#         try:
#             data = json.loads(request.body)
#             qr_token = data.get('qr_token')
#
#             # Tìm sinh viên có qr_token tương ứng
#             profile = UserProfile.objects.filter(qr_token=qr_token, role='student').first()
#
#             if profile:
#                 # Thực hiện login
#                 login(request, profile.user)
#                 return JsonResponse({
#                     'status': 'success',
#                     'message': 'Đăng nhập thành công!',
#                     'redirect_url': '/'  # Có thể đổi thành url trang bài thi của bạn
#                 })
#             else:
#                 return JsonResponse({
#                     'status': 'error',
#                     'message': 'Mã QR không hợp lệ hoặc tài khoản không phải là Sinh viên.'
#                 })
#         except Exception as e:
#             return JsonResponse({'status': 'error', 'message': str(e)})
#
#     return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})
#
#
# @login_required(login_url='qr_login_page')
# def profile_view(request):
#     user_profile = request.user.userprofile
#
#     if request.method == 'POST':
#         # Cập nhật thông tin cơ bản từ form
#         user_profile.phone = request.POST.get('phone', '')
#         user_profile.address = request.POST.get('address', '')
#         user_profile.birthday = request.POST.get('birthday') or None
#
#         # Nếu có tải lên avatar mới
#         if 'avatar' in request.FILES:
#             user_profile.avatar = request.FILES['avatar']
#
#         user_profile.save()
#         messages.success(request, 'Cập nhật hồ sơ thành công!')
#         return redirect('profile')
#
#     return render(request, 'profile.html', {
#         'title': 'Hồ sơ cá nhân',
#         'profile': user_profile
#     })
#
#
# from django.shortcuts import get_object_or_404
# from .models import Course, Exam
#
# @login_required(login_url='qr_login_page')
# def course_list_view(request):
#     # Lấy danh sách khóa học theo khoa của sinh viên hoặc tất cả khóa học
#     courses = Course.objects.all()
#     return render(request, 'courses.html', {
#         'title': 'Khóa học của bạn',
#         'courses': courses
#     })
#
#
# from .exam_engine import generate_exam
# import random
#
# import random
# from django.shortcuts import render, get_object_or_404, redirect
# from django.contrib.auth.decorators import login_required
# from .models import Exam, StudentExam
#
# @login_required(login_url="qr_login_page")
# def take_exam_view(request, exam_id):
#     # Lấy đề gốc theo ID hoặc cho phép chọn ngẫu nhiên trong danh sách các đề đang hoạt động
#     base_exam = get_object_or_404(Exam, id=exam_id, is_active=True)
#
#     # Lấy tất cả các mã đề khác có sẵn trong cùng course để phân bổ ngẫu nhiên cho user
#     available_exams = list(Exam.objects.filter(course=base_exam.course, is_active=True))
#     exam = random.choice(available_exams) if available_exams else base_exam
#
#     # 1. Tạo mã đề động ngẫu nhiên riêng biệt cho lần thi này (Ví dụ: CPP_4821)
#     dynamic_exam_code = f"CPP_{random.randint(1000, 9999)}"
#
#     # 2. Kiểm tra xem sinh viên đã có phiên làm bài (chưa nộp) chưa.
#     # Nếu có rồi thì giữ nguyên phiên cũ (để F5 không bị đổi đề), chưa có thì tạo mới kèm mã đề động.
#     student_exam, created = StudentExam.objects.get_or_create(
#         student=request.user,
#         exam=exam,
#         is_submitted=False,
#         defaults={'exam_code': dynamic_exam_code}
#     )
#
#     # Đảm bảo nếu bản ghi cũ chưa có exam_code thì gán luôn mã động vào
#     if not student_exam.exam_code:
#         student_exam.exam_code = dynamic_exam_code
#         student_exam.save()
#
#     # Sinh danh sách câu hỏi dựa trên cấu hình của mã đề đó (đã gọi hàm generate_exam bốc đủ 10 câu: 3 MCQ, 3 Drag, 2 Sort, 2 Code)
#     questions = generate_exam(exam)
#
#     letters = ["A", "B", "C", "D", "E", "F"]
#
#     for question in questions:
#         if question.question_type == "MCQ":
#             choices = list(question.choices.all())
#             random.shuffle(choices)
#             for i, c in enumerate(choices):
#                 c.letter = letters[i]
#             question.random_choices = choices
#
#         elif question.question_type == "DRAG":
#             drag = list(question.drag_items.all())
#             random.shuffle(drag)
#             question.random_drag = drag
#
#         elif question.question_type == "SORT":
#             sort = list(question.sort_items.all())
#             random.shuffle(sort)
#             question.random_sort = sort
#
#     return render(
#         request,
#         "take_exam.html",
#         {
#             "exam": exam,
#             "questions": questions,
#             "student_exam": student_exam,
#             "duration": exam.duration_minutes,
#             "exam_code": student_exam.exam_code  # Truyền chính xác mã đề cố định ra giao diện
#         }
#     )
# from django.views.decorators.csrf import csrf_exempt
# from django.http import JsonResponse
# from django.shortcuts import get_object_or_404
#
# from .models import (
#     QuestionBank,
#     StudentAnswer,
#     StudentExam
# )
#
# from compiler.run import run_cpp
#
# import json
#
#
# @csrf_exempt
# def run_code(request):
#
#     if request.method != "POST":
#         return JsonResponse({
#             "success": False,
#             "message": "POST only"
#         })
#
#     body = json.loads(request.body)
#
#     question_id = body.get("question_id")
#
#     code = body.get("code", "")
#
#     student_exam_id = body.get("student_exam_id")
#
#     question = get_object_or_404(
#         QuestionBank,
#         id=question_id
#     )
#
#     student_exam = get_object_or_404(
#         StudentExam,
#         id=student_exam_id
#     )
#
#     testcases = question.test_cases.all()
#
#     total_score = 0
#
#     max_score = 0
#
#     testcase_result = []
#
#     compile_error = None
#
#     runtime_error = None
#
#     for testcase in testcases:
#
#         max_score += testcase.score
#
#         result = run_cpp(
#             code,
#             testcase.input_data
#         )
#
#         if result["status"] == "Compile Error":
#
#             compile_error = result["compile_error"]
#
#             break
#
#         if result["status"] == "Runtime Error":
#
#             runtime_error = result["stderr"]
#
#             break
#
#         actual = result["stdout"].strip()
#
#         expected = testcase.expected_output.strip()
#
#         passed = actual == expected
#
#         if passed:
#
#             total_score += testcase.score
#
#         testcase_result.append({
#
#             "input": testcase.input_data,
#
#             "expected": expected,
#
#             "actual": actual,
#
#             "passed": passed
#
#         })
#
#     answer, created = StudentAnswer.objects.get_or_create(
#
#         student_exam=student_exam,
#
#         question=question
#
#     )
#
#     answer.answer_text = code
#
#     answer.score = total_score
#
#     answer.is_correct = total_score == max_score
#
#     answer.save()
#
#     return JsonResponse({
#
#         "success": True,
#
#         "compile_error": compile_error,
#
#         "runtime_error": runtime_error,
#
#         "score": total_score,
#
#         "max_score": max_score,
#
#         "testcases": testcase_result
#
#     })
#
#
# def compiler_test(request):
#
#     return render(
#
#         request,
#
#         "compiler_test.html"
#
#     )
#
#
# @login_required
# def submit_exam_view(request, student_exam_id):
#     student_exam = get_object_or_404(StudentExam, id=student_exam_id, student=request.user)
#     if student_exam.is_submitted:
#         return redirect('exam_history')
#
#     if request.method == 'POST':
#         total_score = 0.0
#         # Xử lý chấm điểm trắc nghiệm và các câu hỏi khác ở đây...
#         # ...
#
#         student_exam.is_submitted = True
#         student_exam.score = total_score
#         student_exam.save()
#         return render(request, 'exam_success.html', {'student_exam': student_exam})
#
#     return redirect('course_list')
#
#
# from django.shortcuts import get_object_or_404, redirect, render
# from django.contrib.auth.decorators import login_required, user_passes_test
#
# # Hàm kiểm tra user có phải là Giảng viên không
# def is_teacher(user):
#     return user.is_authenticated and (user.is_staff or user.groups.filter(name='GiangVien').exists())
#
# @login_required
# @user_passes_test(is_teacher, login_url='home')
# def teacher_exam_submissions(request, exam_id):
#     # Kiểm tra quyền giảng viên (ví dụ: request.user.is_staff)
#     if not request.user.is_staff:
#         return redirect('home')
#
#     exam = get_object_or_404(Exam, id=exam_id)
#     submissions = StudentExam.objects.filter(exam=exam, is_completed=True).order_by('-submitted_at')
#
#     return render(request, 'teacher_exam_submissions.html', {
#         'exam': exam,
#         'submissions': submissions
#     })
# from django.contrib.admin.views.decorators import staff_member_required
#
# @staff_member_required
# def lecturer_exam_report(request, exam_id):
#     exam = get_object_or_404(Exam, id=exam_id)
#     submissions = StudentExam.objects.filter(exam=exam, is_submitted=True)
#     context = {
#         'exam': exam,
#         'submissions': submissions,
#         'total_students': submissions.count()
#     }
#     return render(request, 'lecturer_report.html', context)
#
#
# import json
# from django.shortcuts import get_object_or_404, redirect, render
# from django.utils import timezone
# from django.contrib.auth.decorators import login_required
#
#
# # @login_required
# # def submit_exam(request, student_exam_id):
# #     student_exam = get_object_or_404(StudentExam, id=student_exam_id, student=request.user)
# #
# #     if student_exam.is_submitted:
# #         return redirect('exam_result', student_exam_id=student_exam.id)
# #
# #     total_score = 0.0
# #     questions = QuestionBank.objects.filter(exam=student_exam.exam)
# #
# #     for question in questions:
# #         is_correct = False
# #         earned_score = 0.0
# #         answer_content = ""
# #
# #         if question.question_type == "MCQ":
# #             choice_id = request.POST.get(f'question_{question.id}')
# #             if choice_id:
# #                 choice = question.choices.filter(id=choice_id).first()
# #                 answer_content = str(choice_id)
# #                 if choice and choice.is_correct:
# #                     is_correct = True
# #                     earned_score = question.score
# #
# #
# #         elif question.question_type == "SORT":
# #
# #             sorted_ids_json = request.POST.get(f'sorted_ids_{question.id}')
# #
# #             answer_content = sorted_ids_json
# #
# #             if sorted_ids_json:
# #
# #                 user_order = json.loads(sorted_ids_json)
# #
# #                 # SỬA TỪ order_index THÀNH correct_order Ở ĐÂY:
# #
# #                 correct_order = list(question.sort_items.order_by('correct_order').values_list('id', flat=True))
# #
# #                 if [int(i) for i in user_order] == correct_order:
# #                     is_correct = True
# #
# #                     earned_score = question.score
# #
# #         # SỬA TÊN TRƯỜNG Ở ĐÂY CHO KHỚP VỚI MODEL STUDENTANSWER:
# #         StudentAnswer.objects.update_or_create(
# #             student_exam=student_exam,
# #             question=question,
# #             defaults={
# #                 'answer_text': answer_content,  # Dùng answer_text thay vì answer_content
# #                 'is_correct': is_correct,
# #                 'score': earned_score  # Dùng score thay vì earned_score
# #             }
# #         )
# #         total_score += earned_score
# #
# #     student_exam.score = total_score
# #     student_exam.submitted_at = timezone.now()
# #     student_exam.is_submitted = True
# #     if hasattr(student_exam, 'is_completed'):
# #         student_exam.is_completed = True
# #
# #     student_exam.save()
# #
# #     return redirect('exam_result', student_exam_id=student_exam.id)
# @login_required
# def submit_exam(request, student_exam_id):
#     student_exam = get_object_or_404(StudentExam, id=student_exam_id, student=request.user)
#
#     if student_exam.is_submitted:
#         return redirect('exam_result', student_exam_id=student_exam.id)
#
#     total_score = 0.0
#     questions = QuestionBank.objects.filter(exam=student_exam.exam)
#
#     for question in questions:
#         is_correct = False
#         earned_score = 0.0
#         answer_content = ""
#
#         if question.question_type == "MCQ":
#             choice_id = request.POST.get(f'question_{question.id}')
#             if choice_id:
#                 choice = question.choices.filter(id=choice_id).first()
#                 if choice:
#                     answer_content = choice.content
#                     if choice.is_correct:
#                         is_correct = True
#                         earned_score = question.score
#
#         elif question.question_type in ["SORT", "DRAG"]:
#             sorted_ids_json = request.POST.get(f'sorted_ids_{question.id}')
#             if sorted_ids_json:
#                 user_order = json.loads(sorted_ids_json)
#
#                 # Lọc bỏ các giá trị null/None từ ô trống chưa điền để tránh lỗi ép kiểu
#                 cleaned_user_order = [int(i) for i in user_order if i is not None]
#
#                 sorted_texts = []
#                 for s_id in user_order:
#                     if s_id is not None:
#                         s_item = question.sort_items.filter(id=s_id).first() or question.drag_items.filter(
#                             id=s_id).first()
#                         if s_item:
#                             sorted_texts.append(s_item.code)
#                     else:
#                         sorted_texts.append("(Trống)")
#                 answer_content = "\n".join(sorted_texts)
#
#                 # So sánh thứ tự đúng
#                 correct_order = list(question.sort_items.order_by('correct_order').values_list('id', flat=True))
#                 if not correct_order:
#                     correct_order = list(question.drag_items.order_by('correct_order').values_list('id', flat=True))
#
#                 # So sánh mảng đã lọc với đáp án chuẩn
#                 if cleaned_user_order == correct_order:
#                     is_correct = True
#                     earned_score = question.score
#             else:
#                 answer_content = "Không có dữ liệu kéo thả"
#
#         elif question.question_type == "CODE":
#             answer_content = request.POST.get(f'code_answer_{question.id}', '')
#             testcases = question.testcases.all() if hasattr(question, 'testcases') else []
#             if testcases:
#                 passed_all = True
#             else:
#                 if answer_content.strip() and len(answer_content.strip()) > 20:
#                     earned_score = question.score
#                     is_correct = True
#
#         StudentAnswer.objects.update_or_create(
#             student_exam=student_exam,
#             question=question,
#             defaults={
#                 'answer_text': answer_content,
#                 'is_correct': is_correct,
#                 'score': earned_score
#             }
#         )
#         total_score += earned_score
#
#     student_exam.score = total_score
#     student_exam.submitted_at = timezone.now()
#     student_exam.is_submitted = True
#     if hasattr(student_exam, 'is_completed'):
#         student_exam.is_completed = True
#     student_exam.save()
#
#     return redirect('exam_result', student_exam_id=student_exam.id)
# @login_required
# def exam_result_view(request, student_exam_id):
#     student_exam = get_object_or_404(StudentExam, id=student_exam_id, student=request.user)
#     detail_results = student_exam.answers.all()
#
#     # SỬA TÊN FILE Ở ĐÂY TỪ 'exam_result_list.html' THÀNH 'exam_result.html'
#     return render(request, 'exam_result.html', {
#         'student_exam': student_exam,
#         'detail_results': detail_results
#     })
#
#
#
# @login_required(login_url='qr_login_page')
# def exam_list_view(request):
#     exams = Exam.objects.all()
#     return render(request, 'exam/exam_list.html', {'exams': exams})
#
# @login_required(login_url='qr_login_page')
# def exam_result_list_view(request):
#     # Đổi 'submitted_at' thành 'finished_at'
#     results = StudentExam.objects.filter(student=request.user, is_submitted=True).order_by('-finished_at')
#     return render(request, 'exam/exam_result_list.html', {'results': results})


import json
import random
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.http import Http404, JsonResponse
from django.contrib.auth import login
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from .models import UserProfile, Course, Exam, StudentExam, QuestionBank, StudentAnswer
from .exam_engine import generate_exam
from compiler.run import run_cpp


def index(request):
    return render(request, "index.html")


def qr_login_page(request):
    if request.user.is_authenticated:
        return redirect('home')
    return render(request, "login.html", {'title': 'Đăng nhập Sinh viên'})


def verify_qr_login(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            qr_token = data.get('qr_token')
            profile = UserProfile.objects.filter(qr_token=qr_token).select_related("user").first()

            if profile and profile.user.is_active:
                login(request, profile.user)
                return JsonResponse({
                    'status': 'success',
                    'message': 'Đăng nhập thành công!',
                    'redirect_url': '/'
                })
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Mã QR không hợp lệ hoặc tài khoản đã bị vô hiệu hóa.'
                })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})


@login_required(login_url='qr_login_page')
def profile_view(request):
    user_profile = request.user.userprofile

    if request.method == 'POST':
        user_profile.phone = request.POST.get('phone', '')
        user_profile.address = request.POST.get('address', '')
        user_profile.birthday = request.POST.get('birthday') or None

        if 'avatar' in request.FILES:
            user_profile.avatar = request.FILES['avatar']

        user_profile.save()
        messages.success(request, 'Cập nhật hồ sơ thành công!')
        return redirect('profile')

    return render(request, 'profile.html', {
        'title': 'Hồ sơ cá nhân',
        'profile': user_profile
    })


@login_required(login_url='qr_login_page')
def course_list_view(request):
    profile = request.user.userprofile
    courses = Course.objects.all().prefetch_related(
        "exams",
        "offerings__term",
        "offerings__lecturers__user",
    )
    if profile.role == "student":
        courses = courses.filter(
            Q(offerings__isnull=True) | Q(offerings__students=profile)
        ).distinct()

    for course in courses:
        if profile.role == "student":
            course.visible_offerings = course.offerings.filter(students=profile)
            course.visible_exams = course.exams.filter(
                Q(offering__isnull=True) | Q(offering__students=profile),
                is_active=True,
            ).distinct()
        else:
            course.visible_offerings = course.offerings.all()
            course.visible_exams = course.exams.filter(is_active=True)

    return render(request, 'courses.html', {
        'title': 'Khóa học của bạn',
        'courses': courses
    })


@login_required(login_url="qr_login_page")
def take_exam_view(request, exam_id):
    base_exam = get_object_or_404(
        Exam.objects.select_related("offering"),
        id=exam_id,
        is_active=True,
    )

    profile = request.user.userprofile
    if (
        profile.role == "student"
        and base_exam.offering_id
        and not base_exam.offering.students.filter(pk=profile.pk).exists()
    ):
        raise Http404

    available_exams_query = Exam.objects.filter(
        course=base_exam.course,
        is_active=True,
    )
    if base_exam.offering_id:
        available_exams_query = available_exams_query.filter(offering=base_exam.offering)
    else:
        available_exams_query = available_exams_query.filter(offering__isnull=True)
    available_exams = list(available_exams_query)
    exam = random.choice(available_exams) if available_exams else base_exam

    dynamic_exam_code = f"CPP_{random.randint(1000, 9999)}"

    student_exam, created = StudentExam.objects.get_or_create(
        student=request.user,
        exam=exam,
        is_submitted=False,
        defaults={'exam_code': dynamic_exam_code}
    )

    if not student_exam.exam_code:
        student_exam.exam_code = dynamic_exam_code
        student_exam.save()

    # Lấy danh sách câu hỏi chuẩn từ engine (Đảm bảo bốc đúng 3 MCQ, 3 Drag, 2 Sort, 2 Code)
    questions = generate_exam(exam)

    letters = ["A", "B", "C", "D", "E", "F"]

    for question in questions:
        if question.question_type == "MCQ":
            choices = list(question.choices.all())
            random.shuffle(choices)
            for i, c in enumerate(choices):
                c.letter = letters[i]
            question.random_choices = choices

        elif question.question_type == "DRAG":
            drag = list(question.drag_items.all())
            random.shuffle(drag)
            question.random_drag = drag

        elif question.question_type == "SORT":
            sort = list(question.sort_items.all())
            random.shuffle(sort)
            question.random_sort = sort

    return render(
        request,
        "take_exam.html",
        {
            "exam": exam,
            "questions": questions,
            "student_exam": student_exam,
            "duration": exam.duration_minutes,
            "exam_code": student_exam.exam_code
        }
    )


@csrf_exempt
def run_code(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "POST only"})

    try:
        body = json.loads(request.body)
        question_id = body.get("question_id")
        code = body.get("code", "")
        student_exam_id = body.get("student_exam_id")

        question = get_object_or_404(QuestionBank, id=question_id)
        student_exam = get_object_or_404(StudentExam, id=student_exam_id)

        testcases = question.test_cases.all()
        total_score = 0
        max_score = 0
        testcase_result = []
        compile_error = None
        runtime_error = None

        for testcase in testcases:
            max_score += testcase.score
            result = run_cpp(code, testcase.input_data)

            if result["status"] == "Compile Error":
                compile_error = result["compile_error"]
                break
            if result["status"] == "Runtime Error":
                runtime_error = result["stderr"]
                break

            actual = result["stdout"].strip()
            expected = testcase.expected_output.strip()
            passed = (actual == expected)

            if passed:
                total_score += testcase.score

            testcase_result.append({
                "input": testcase.input_data,
                "expected": expected,
                "actual": actual,
                "passed": passed
            })

        answer, created = StudentAnswer.objects.get_or_create(
            student_exam=student_exam,
            question=question
        )
        answer.answer_text = code
        answer.score = total_score
        answer.is_correct = (total_score == max_score) and (max_score > 0)
        answer.save()

        return JsonResponse({
            "success": True,
            "compile_error": compile_error,
            "runtime_error": runtime_error,
            "score": total_score,
            "max_score": max_score,
            "testcases": testcase_result
        })
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)})


def compiler_test(request):
    return render(request, "compiler_test.html")


@login_required
def submit_exam(request, student_exam_id):
    student_exam = get_object_or_404(StudentExam, id=student_exam_id, student=request.user)

    if student_exam.is_submitted:
        return redirect('exam_result', student_exam_id=student_exam.id)

    total_score = 0.0

    # Lấy đúng danh sách câu hỏi thuộc đề thi thực tế của sinh viên này
    questions = generate_exam(student_exam.exam)

    for question in questions:
        is_correct = False
        earned_score = 0.0
        answer_content = ""

        if question.question_type == "MCQ":
            # Hỗ trợ quét nhiều kiểu tên name từ form HTML
            choice_id = request.POST.get(f'question_{question.id}') or request.POST.get(
                f'q_{question.id}') or request.POST.get(f'choice_{question.id}')
            if choice_id:
                choice = question.choices.filter(id=choice_id).first()
                if choice:
                    answer_content = choice.content
                    if choice.is_correct:
                        is_correct = True
                        earned_score = question.score

        elif question.question_type in ["SORT", "DRAG"]:
            sorted_ids_json = request.POST.get(f'sorted_ids_{question.id}') or request.POST.get(f'answer_{question.id}')

            # Nếu input ẩn rỗng, thử quét trực tiếp qua các khóa name thay thế trong POST
            if not sorted_ids_json:
                for key, val in request.POST.items():
                    if str(question.id) in key and val:
                        sorted_ids_json = val
                        break

            if sorted_ids_json:
                try:
                    # Xử lý chuỗi JSON hoặc chuỗi số ngăn cách bằng dấu phẩy
                    if sorted_ids_json.strip().startswith('['):
                        user_order = json.loads(sorted_ids_json)
                    else:
                        user_order = [int(x.strip()) for x in sorted_ids_json.split(',') if x.strip().isdigit()]

                    cleaned_user_order = [int(i) for i in user_order if i is not None]

                    sorted_texts = []
                    for s_id in user_order:
                        if s_id is not None:
                            s_item = question.sort_items.filter(id=s_id).first() or question.drag_items.filter(
                                id=s_id).first()
                            if s_item:
                                sorted_texts.append(s_item.code)
                        else:
                            sorted_texts.append("(Trống)")
                    answer_content = "\n".join(sorted_texts)

                    # Lấy thứ tự chuẩn từ database
                    correct_order = list(question.sort_items.order_by('correct_order').values_list('id', flat=True))
                    if not correct_order:
                        correct_order = list(question.drag_items.order_by('correct_order').values_list('id', flat=True))

                    # So khớp kết quả của sinh viên với đáp án chuẩn
                    if cleaned_user_order and cleaned_user_order == correct_order:
                        is_correct = True
                        earned_score = question.score
                except Exception as e:
                    answer_content = f"Lỗi xử lý dữ liệu: {str(e)}"
            else:
                answer_content = "Chưa trả lời"

        elif question.question_type == "CODE":
            answer_content = request.POST.get(f'code_answer_{question.id}') or request.POST.get(
                f'code_{question.id}') or request.POST.get(f'editor_{question.id}', '')

            # Ưu tiên lấy kết quả điểm đã test qua API run_code nếu có sẵn
            existing_ans = StudentAnswer.objects.filter(student_exam=student_exam, question=question).first()
            if existing_ans and existing_ans.score > 0:
                earned_score = existing_ans.score
                is_correct = existing_ans.is_correct
                if not answer_content:
                    answer_content = existing_ans.answer_text
            else:
                # Nếu chưa chạy qua API, chấm trực tiếp qua testcase lúc submit
                testcases = question.test_cases.all()
                if testcases and answer_content:
                    q_score = 0
                    for tc in testcases:
                        res = run_cpp(answer_content, tc.input_data)
                        if res["status"] == "Success" and res["stdout"].strip() == tc.expected_output.strip():
                            q_score += tc.score
                    earned_score = q_score
                    is_correct = (q_score > 0)

        # Lưu hoặc cập nhật kết quả từng câu vào Database
        StudentAnswer.objects.update_or_create(
            student_exam=student_exam,
            question=question,
            defaults={
                'answer_text': answer_content,
                'is_correct': is_correct,
                'score': earned_score
            }
        )
        total_score += earned_score

    # Cập nhật tổng điểm bài thi
    student_exam.score = total_score
    student_exam.finished_at = timezone.now()
    student_exam.is_submitted = True
    if hasattr(student_exam, 'is_completed'):
        student_exam.is_completed = True
    student_exam.save()

    return redirect('exam_result', student_exam_id=student_exam.id)
@login_required
def exam_result_view(request, student_exam_id):
    student_exam = get_object_or_404(StudentExam, id=student_exam_id, student=request.user)
    detail_results = student_exam.answers.all()

    return render(request, 'exam_result.html', {
        'student_exam': student_exam,
        'detail_results': detail_results
    })


@login_required(login_url='qr_login_page')
def exam_list_view(request):
    exams = Exam.objects.select_related("course", "offering__term")
    profile = request.user.userprofile
    if profile.role == "student":
        exams = exams.filter(
            Q(offering__isnull=True) | Q(offering__students=profile)
        ).distinct()
    return render(request, 'exam/exam_list.html', {'exams': exams})


@login_required(login_url='qr_login_page')
def exam_result_list_view(request):
    # results = StudentExam.objects.filter(student=request.user, is_submitted=True).order_by('-submitted_at')
    results = StudentExam.objects.filter(student=request.user, is_submitted=True).order_by('-finished_at')
    return render(request, 'exam/exam_result_list.html', {'results': results})


def is_teacher(user):
    if not user.is_authenticated:
        return False
    return user.is_staff or (
        hasattr(user, "userprofile")
        and user.userprofile.role in ("admin", "lecturer")
    )


@login_required
@user_passes_test(is_teacher, login_url='home')
def teacher_exam_submissions(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    submissions = StudentExam.objects.filter(exam=exam, is_submitted=True).order_by('-submitted_at')

    return render(request, 'teacher_exam_submissions.html', {
        'exam': exam,
        'submissions': submissions
    })


@user_passes_test(is_teacher, login_url='home')
def lecturer_exam_report(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    submissions = StudentExam.objects.filter(exam=exam, is_submitted=True)
    context = {
        'exam': exam,
        'submissions': submissions,
        'total_students': submissions.count()
    }
    return render(request, 'lecturer_report.html', context)