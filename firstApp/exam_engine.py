import copy
import random


def _normalize_question(question, index):
    """
    Chuẩn hóa một câu hỏi từ Exam.question_data
    thành format dùng thống nhất cho StudentExam.
    """

    question = copy.deepcopy(question)

    question["index"] = index

    question_type = str(
        question.get("type", "")
    ).upper()

    question["type"] = question_type
    question["title"] = str(
        question.get("title")
        or question.get("content")
        or question.get("question")
        or ""
    )

    question_score = question.get("score")
    if question_score in (None, ""):
        if question_type == "CODE":
            question_score = sum(
                float(testcase.get("score", 1) or 0)
                for testcase in question.get("test_cases", [])
            )
        else:
            question_score = 1
    question["score"] = float(question_score)

    return question


def build_student_paper(exam):
    """
    Tạo một mã đề hoàn chỉnh cho một sinh viên.

    Nguồn duy nhất:
        Exam.question_data

    Kết quả:
        {
            "paper_code": "...",
            "questions": [...]
        }
    """

    raw_questions = exam.question_data or []

    if not isinstance(raw_questions, list):
        raise ValueError(
            "Dữ liệu câu hỏi của bài thi không hợp lệ."
        )

    if not raw_questions:
        raise ValueError(
            "Bài thi chưa có câu hỏi."
        )

    questions = [
        _normalize_question(
            question,
            index + 1
        )
        for index, question in enumerate(raw_questions)
    ]

    # ---------------------------------------------------------
    # SHUFFLE CÂU HỎI
    # ---------------------------------------------------------

    random.shuffle(questions)

    # ---------------------------------------------------------
    # SHUFFLE ĐÁP ÁN
    # ---------------------------------------------------------

    for question in questions:

        question_type = question.get("type")

        # =====================================================
        # MCQ
        # =====================================================

        if question_type == "MCQ":

            choices = question.get(
                "choices",
                []
            )

            choices = copy.deepcopy(choices)

            if len(choices) != 4:
                raise ValueError(
                    f"Câu {question['index']} MCQ "
                    f"phải có đúng 4 đáp án."
                )

            correct_answer = question.get("correct_answer")
            correct_choice = next(
                (
                    choice
                    for choice in choices
                    if choice.get("is_correct")
                    or choice.get("correct")
                    or (
                        correct_answer is not None
                        and str(choice.get("label", "")) == str(correct_answer)
                    )
                    or (
                        correct_answer is not None
                        and str(choice.get("id", "")) == str(correct_answer)
                    )
                    or (
                        correct_answer is not None
                        and str(choice.get("text", "")) == str(correct_answer)
                    )
                ),
                None,
            )

            if correct_choice is None:
                raise ValueError(
                    f"Câu {question['index']} MCQ chưa xác định được đáp án đúng."
                )

            random.shuffle(choices)

            for choice_index, choice in enumerate(choices, start=1):
                choice["index"] = choice_index
                choice["display_letter"] = chr(64 + choice_index)
                if choice is correct_choice:
                    question["_correct_choice_index"] = choice_index

            question["choices"] = choices

        # =====================================================
        # DRAG
        # =====================================================

        elif question_type == "DRAG":

            items = question.get(
                "items",
                []
            )

            items = copy.deepcopy(items)

            if not items:
                raise ValueError(
                    f"Câu {question['index']} DRAG "
                    f"chưa có đáp án."
                )

            # Lưu đáp án đúng trước khi shuffle
            correct_answers = []

            for item in items:

                correct_answers.append(
                    str(
                        item.get(
                            "text",
                            ""
                        )
                    ).strip()
                )

            question["_correct_answers"] = (
                correct_answers
            )

            random.shuffle(items)

            # Không cần gửi correct_order
            # ra frontend.
            for item in items:
                item.pop(
                    "correct_order",
                    None
                )

            question["items"] = items

        # =====================================================
        # SORT
        # =====================================================

        elif question_type == "SORT":

            items = question.get(
                "items",
                []
            )

            items = copy.deepcopy(items)

            if not items:
                raise ValueError(
                    f"Câu {question['index']} SORT "
                    f"chưa có item."
                )

            correct_order = []

            for item in items:

                correct_order.append(
                    str(
                        item.get(
                            "text",
                            ""
                        )
                    )
                )

            question["_correct_order"] = (
                correct_order
            )

            random.shuffle(items)

            for item in items:
                item.pop(
                    "correct_order",
                    None
                )

            question["items"] = items

        # =====================================================
        # CODE
        # =====================================================

        elif question_type == "CODE":

            test_cases = question.get(
                "test_cases",
                []
            )

            if not test_cases:
                raise ValueError(
                    f"Câu {question['index']} CODE "
                    f"chưa có Test Case."
                )

            question["test_cases"] = (
                copy.deepcopy(test_cases)
            )

        else:

            raise ValueError(
                f"Câu {question['index']} "
                f"có loại câu hỏi không hợp lệ: "
                f"{question_type}"
            )

    # ---------------------------------------------------------
    # MÃ ĐỀ
    # ---------------------------------------------------------

    paper_codes = list(
        exam.paper_codes or []
    )

    if paper_codes:
        paper_code = random.choice(
            paper_codes
        )
    else:
        paper_code = str(
            random.randint(
                1000,
                9999
            )
        )

    return {
        "paper_code": paper_code,
        "questions": questions,
    }


def build_student_snapshot(exam):
    """
    Tạo snapshot để lưu cố định vào StudentExam.
    """

    paper = build_student_paper(exam)

    return paper


# =============================================================
# BACKWARD COMPATIBILITY
# =============================================================

def generate_exam(exam):
    """
    Hàm tương thích với code cũ.

    Từ bây giờ không đọc QuestionBank.
    """

    return build_student_paper(exam)


def get_student_exam_questions(student_exam):
    """
    Lấy câu hỏi từ snapshot.
    Không generate lại khi refresh.
    """

    snapshot = (
        student_exam.question_snapshot
        or []
    )

    if isinstance(snapshot, dict):

        return snapshot.get(
            "questions",
            []
        )

    return snapshot


def sync_exam_questions(exam):
    """
    Exam Builder mới sử dụng question_data.

    Hàm này giữ lại để admin.py cũ
    không bị lỗi.

    Không đồng bộ sang QuestionBank nữa.
    """

    return 0