import random
import uuid
from .models import QuestionBank

def generate_exam(exam):
    """
    Bốc ngẫu nhiên từ ngân hàng câu hỏi của môn học:
    - 3 câu MCQ
    - 3 câu DRAG
    - 2 câu SORT
    - 2 câu CODE
    Tổng cộng đúng 10 câu cho một đề thi.
    """
    base_qs = QuestionBank.objects.filter(course=exam.course)

    def get_random_subset(q_type, count):
        items = list(base_qs.filter(question_type=q_type))
        random.shuffle(items)
        return items[:count]

    # Bốc đúng số lượng yêu cầu cho từng dạng
    selected_mcq = get_random_subset("MCQ", 3)
    selected_drag = get_random_subset("DRAG", 3)
    selected_sort = get_random_subset("SORT", 2)
    selected_code = get_random_subset("CODE", 2)

    # Gộp lại và xáo trộn thứ tự các câu hỏi trong đề thi
    exam_questions = selected_mcq + selected_drag + selected_sort + selected_code
    random.shuffle(exam_questions)

    return exam_questions