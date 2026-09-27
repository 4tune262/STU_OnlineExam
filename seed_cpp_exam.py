import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from firstApp.models import Course, Exam, QuestionBank, Choice, DragItem, SortItem, TestCase


def seed_data():
    print("Đang nạp ngân hàng 40 câu hỏi chuẩn C++ (Có từ khóa nhiễu cho Drag)...")

    TestCase.objects.all().delete()
    DragItem.objects.all().delete()
    SortItem.objects.all().delete()
    Choice.objects.all().delete()
    QuestionBank.objects.all().delete()
    Exam.objects.all().delete()
    Course.objects.all().delete()

    course = Course.objects.create(
        code="CPP101",
        name="Nhập môn Lập trình C++",
        faculty="CNTT",
        description="Môn học cơ sở nền tảng về lập trình C++.",
        credit=3,
        semester=1
    )

    exam = Exam.objects.create(
        course=course,
        title="Kiểm tra Giữa kỳ Nhập môn Lập trình C++",
        duration_minutes=45,
        start_time="2026-01-01 00:00:00+00:00",
        end_time="2030-12-31 23:59:59+00:00",
        is_active=True
    )

    # ================= 10 CÂU MCQ =================
    mcq_data = [
        ("Thư viện chuẩn nào dùng để nhập/xuất cơ bản (cin, cout)?",
         [("<iostream>", True), ("<stdio.h>", False), ("<math.h>", False), ("<string>", False)]),
        ("Kết quả của biểu thức 5 % 2 trong C++ là gì?", [("1", True), ("2", False), ("2.5", False), ("0", False)]),
        ("Phạm vi của biến cục bộ bên trong một hàm là gì?",
         [("Chỉ trong khối lệnh/hàm chứa nó", True), ("Toàn bộ chương trình", False), ("Toàn bộ file", False),
          ("Trong mọi hàm", False)]),
        ("Phát biểu nào đúng về con trỏ (pointer) trong C++?",
         [("Lưu trữ địa chỉ của một biến khác", True), ("Lưu trữ trực tiếp số thực", False),
          ("Không thể thay đổi giá trị", False), ("Luôn trỏ về NULL", False)]),
        ("Độ phức tạp thời gian của tìm kiếm nhị phân là gì?",
         [("O(log n)", True), ("O(n)", False), ("O(n^2)", False), ("O(1)", False)]),
        ("Hàm nào được thực thi đầu tiên khi chạy chương trình C++?",
         [("main()", True), ("start()", True), ("init()", False), ("run()", False)]),
        ("Từ khóa nào dùng để khai báo hằng số trong C++?",
         [("const", True), ("static", False), ("define", False), ("final", False)]),
        ("Phương thức thêm phần tử vào cuối vector trong STL là gì?",
         [("push_back()", True), ("add()", False), ("append()", False), ("insert()", False)]),
        ("Cú pháp cấp phát bộ nhớ động cho 1 số nguyên là gì?",
         [("int* p = new int;", True), ("int p = malloc();", False), ("new int p;", False),
          ("int* p = alloc(int);", False)]),
        ("Toán tử nào dùng để lấy địa chỉ của một biến?", [("&", True), ("*", False), ("->", False), (".", False)])
    ]
    for title, choices in mcq_data:
        q = QuestionBank.objects.create(course=course, chapter="MCQ", title=title, question_type="MCQ",
                                        difficulty="Medium", score=1.0)
        for content, is_corr in choices:
            Choice.objects.create(question=q, content=content, is_correct=is_corr)

    # ================= 10 CÂU DRAG (Có kèm đáp án đúng và đáp án nhiễu) =================
    drag_data = [
        ("Hoàn thành câu điều kiện kiểm tra số chẵn:",
         'if (n <span class="blank-slot border px-2 py-1 bg-secondary text-white rounded" data-qid="1">[Ô 1]</span> 2 == 0)',
         [("%", 1), ("/", 0), ("+", 0), ("*", 0)]),

        ("Hoàn thành cú pháp vòng lặp for từ 0 đến n-1:",
         'for(int i = 0; <span class="blank-slot border px-2 py-1 bg-secondary text-white rounded" data-qid="1">[Ô 1]</span> n; i++)',
         [("<", 1), (">", 0), ("==", 0), (">=", 0)]),

        ("Lệnh khai báo mảng tĩnh 10 phần tử:",
         'int arr<span class="blank-slot border px-2 py-1 bg-secondary text-white rounded" data-qid="1">[Ô 1]</span>10<span class="blank-slot border px-2 py-1 bg-secondary text-white rounded" data-qid="2">[Ô 2]</span>;',
         [("[", 1), ("]", 2), ("(", 0), (")", 0), ("{", 0), ("}", 0)]),

        ("Khai báo thư viện iostream:",
         '#include <span class="blank-slot border px-2 py-1 bg-secondary text-white rounded" data-qid="1">[Ô 1]</span>',
         [("iostream", 1), ("stdio.h", 0), ("math.h", 0), ("vector", 0)]),

        ("In chuỗi ra màn hình bằng cout:",
         'cout <span class="blank-slot border px-2 py-1 bg-secondary text-white rounded" data-qid="1">[Ô 1]</span> "Hello";',
         [("<<", 1), (">>", 0), ("=", 0), ("+", 0)]),

        ("Nhập giá trị vào biến x:",
         'cin <span class="blank-slot border px-2 py-1 bg-secondary text-white rounded" data-qid="1">[Ô 1]</span> x;',
         [(">>", 1), ("<<", 0), ("=", 0), ("+", 0)]),

        ("Khai báo không gian tên std:",
         '<span class="blank-slot border px-2 py-1 bg-secondary text-white rounded" data-qid="1">[Ô 1]</span> namespace std;',
         [("using", 1), ("define", 0), ("typedef", 0), ("include", 0)]),

        ("Hủy bộ nhớ mảng động ptr:",
         '<span class="blank-slot border px-2 py-1 bg-secondary text-white rounded" data-qid="1">[Ô 1]</span><span class="blank-slot border px-2 py-1 bg-secondary text-white rounded" data-qid="2">[Ô 2]</span> ptr;',
         [("delete", 1), ("[]", 2), ("free", 0), ("new", 0)]),

        ("Cấp phát mảng động 50 phần tử int:",
         'int* p = <span class="blank-slot border px-2 py-1 bg-secondary text-white rounded" data-qid="1">[Ô 1]</span> int<span class="blank-slot border px-2 py-1 bg-secondary text-white rounded" data-qid="2">[Ô 2]</span>50<span class="blank-slot border px-2 py-1 bg-secondary text-white rounded" data-qid="3">[Ô 3]</span>;',
         [("new", 1), ("[", 2), ("]", 3), ("malloc", 0), ("(", 0), (")", 0)]),

        ("Trả về giá trị 0 cho hàm main:",
         'return <span class="blank-slot border px-2 py-1 bg-secondary text-white rounded" data-qid="1">[Ô 1]</span>;',
         [("0", 1), ("1", 0), ("NULL", 0), ("true", 0)])
    ]
    for title, tmpl, items in drag_data:
        q = QuestionBank.objects.create(course=course, chapter="DRAG", title=title, question_type="DRAG",
                                        difficulty="Medium", score=1.0, code_template=tmpl)
        for code_text, order in items:
            DragItem.objects.create(question=q, code=code_text, correct_order=order)

    # ================= 10 CÂU SORT (Sắp xếp) =================
    sort_data = [
        ("Sắp xếp cấu trúc chương trình C++ cơ bản:",
         [("#include <iostream>", 1), ("using namespace std;", 2), ("int main() {", 3), ("    return 0;", 4),
          ("}", 5)]),
        ("Sắp xếp logic tính tổng mảng 1 chiều:",
         [("int sum = 0;", 1), ("for(int i = 0; i < n; i++) {", 2), ("    sum += arr[i];", 3), ("}", 4)]),
        ("Sắp xếp hàm đổi giá trị 2 biến (Swap):",
         [("void swap(int &a, int &b) {", 1), ("    int temp = a;", 2), ("    a = b;", 3), ("    b = temp;", 4),
          ("}", 5)]),
        ("Sắp xếp logic tìm phần tử lớn nhất:", [("int max_val = arr[0];", 1), ("for(int i = 1; i < n; i++) {", 2),
                                                 ("    if(arr[i] > max_val) max_val = arr[i];", 3), ("}", 4)]),
        ("Sắp xếp thuật toán Bubble Sort:",
         [("for(int i = 0; i < n-1; i++) {", 1), ("    for(int j = 0; j < n-i-1; j++) {", 2),
          ("        if(arr[j] > arr[j+1]) swap(arr[j], arr[j+1]);", 3), ("    }", 4), ("}", 5)]),
        ("Sắp xếp hàm kiểm tra số nguyên tố:", [("bool isPrime(int n) {", 1), ("    if (n < 2) return false;", 2),
                                                ("    for(int i = 2; i*i <= n; i++) if(n%i==0) return false;", 3),
                                                ("    return true;", 4), ("}", 5)]),
        ("Sắp xếp hàm tính giai thừa:",
         [("long long fact(int n) {", 1), ("    if (n <= 1) return 1;", 2), ("    return n * fact(n - 1);", 3),
          ("}", 4)]),
        ("Sắp xếp thuật toán Linear Search:",
         [("int search(int arr[], int n, int x) {", 1), ("    for(int i = 0; i < n; i++) if(arr[i] == x) return i;", 2),
          ("    return -1;", 3), ("}", 4)]),
        ("Sắp xếp cấu trúc khai báo Class cơ bản:",
         [("class Student {", 1), ("public:", 2), ("    string name;", 3), ("    int age;", 4), ("};", 5)]),
        ("Sắp xếp vòng lặp while in từ 1 đến 5:",
         [("int i = 1;", 1), ("while (i <= 5) {", 2), ("    cout << i;", 3), ("    i++;", 4), ("}", 5)])
    ]
    for title, items in sort_data:
        q = QuestionBank.objects.create(course=course, chapter="SORT", title=title, question_type="SORT",
                                        difficulty="Medium", score=1.0)
        for code_text, order in items:
            SortItem.objects.create(question=q, code=code_text, correct_order=order)

    # ================= 10 CÂU CODE =================
    code_data = [
        ("Nhập vào n, in ra 'Even' nếu chẵn, 'Odd' nếu lẻ.",
         "#include <iostream>\nusing namespace std;\nint main() {\n    int n; cin >> n;\n    return 0;\n}",
         [("4", "Even"), ("7", "Odd")]),
        ("Nhập vào a và b, in ra tổng hai số.",
         "#include <iostream>\nusing namespace std;\nint main() {\n    int a, b; cin >> a >> b;\n    return 0;\n}",
         [("3 5", "8"), ("-2 10", "8")]),
        ("Nhập điểm trung bình, in 'Dat' nếu >= 5.0, ngược lại 'Truot'.",
         "#include <iostream>\nusing namespace std;\nint main() {\n    float s; cin >> s;\n    return 0;\n}",
         [("6.5", "Dat"), ("4.0", "Truot")]),
        ("Nhập vào n, tính và in ra n! (với n <= 10).",
         "#include <iostream>\nusing namespace std;\nint main() {\n    int n; cin >> n;\n    return 0;\n}",
         [("5", "120"), ("3", "6")]),
        ("Nhập vào 3 số nguyên, in ra số lớn nhất.",
         "#include <iostream>\nusing namespace std;\nint main() {\n    int a, b, c; cin >> a >> b >> c;\n    return 0;\n}",
         [("3 9 5", "9"), ("12 4 8", "12")]),
        ("Nhập vào số nguyên n, in ra bình phương của n.",
         "#include <iostream>\nusing namespace std;\nint main() {\n    int n; cin >> n;\n    return 0;\n}",
         [("6", "36"), ("-4", "16")]),
        ("Nhập vào bán kính r, in ra chu vi hình tròn (pi = 3.14).",
         "#include <iostream>\nusing namespace std;\nint main() {\n    double r; cin >> r;\n    return 0;\n}",
         [("2", "12.56"), ("5", "31.4")]),
        ("Nhập vào năm, kiểm tra năm nhuận (in Yes/No).",
         "#include <iostream>\nusing namespace std;\nint main() {\n    int y; cin >> y;\n    return 0;\n}",
         [("2024", "Yes"), ("2023", "No")]),
        ("Nhập vào chiều dài và rộng chữ nhật, in diện tích.",
         "#include <iostream>\nusing namespace std;\nint main() {\n    double d, r; cin >> d >> r;\n    return 0;\n}",
         [("4 5", "20"), ("2.5 4", "10")]),
        ("Nhập vào n, in ra tổng từ 1 đến n.",
         "#include <iostream>\nusing namespace std;\nint main() {\n    int n; cin >> n;\n    return 0;\n}",
         [("5", "15"), ("3", "6")])
    ]
    for title, starter, testcases in code_data:
        q = QuestionBank.objects.create(course=course, chapter="CODE", title=title, question_type="CODE",
                                        difficulty="Hard", score=1.0, starter_code=starter)
        for inp, out in testcases:
            TestCase.objects.create(question=q, input_data=inp, expected_output=out, score=0.5)

    print("Đã tạo xong ngân hàng 40 câu hỏi thành công!")


if __name__ == "__main__":
    seed_data()