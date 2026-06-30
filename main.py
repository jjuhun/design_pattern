import random
import tkinter as tk
from tkinter import messagebox
from tkinter import font as tkfont

from design_pattern import design_patterns
from fixed_choices import fixed_choices


# 글씨 크기
text_point = 10


def normalize_answer(text):
    return text.strip().replace(" 패턴", "")


def make_choices(correct_answer):
    """객관식 보기 생성: fixed_choices가 있으면 우선 사용, 없으면 랜덤 보기 생성"""
    if correct_answer in fixed_choices:
        choices = fixed_choices[correct_answer].copy()
        random.shuffle(choices)
        return choices

    choices = [correct_answer]
    all_answers = [p["answer"] for p in design_patterns]

    while len(choices) < 4:
        candidate = random.choice(all_answers)

        if candidate not in choices:
            choices.append(candidate)

    random.shuffle(choices)
    return choices


class QuizApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Design Pattern Quiz")
        self.root.geometry("900x750")
        self.root.minsize(650, 500)

        self.mode = tk.StringVar(value="choice")
        self.num_var = tk.StringVar(value="2")

        self.selected_quizzes = []
        self.all_choices = []
        self.answer_vars = []

        self.base_font = tkfont.Font(size=text_point)
        self.title_font = tkfont.Font(size=text_point + 1, weight="bold")

        self.build_ui()

    def build_ui(self):
        self.root.rowconfigure(1, weight=3)
        self.root.rowconfigure(2, weight=2)
        self.root.columnconfigure(0, weight=1)

        top_frame = tk.Frame(self.root, bg="#23384d", padx=15, pady=12)
        top_frame.grid(row=0, column=0, sticky="ew")
        top_frame.columnconfigure(0, weight=1, uniform="top")
        top_frame.columnconfigure(1, weight=1, uniform="top")

        mode_frame = tk.Frame(top_frame, bg="#6f9fd0", padx=13, pady=8)
        mode_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        mode_frame.columnconfigure(0, weight=0)
        mode_frame.columnconfigure(1, weight=1)

        for r, text, value in [
            (0, "choice", "choice"),
            (1, "subjective", "subjective"),
        ]:
            tk.Radiobutton(
                mode_frame,
                text="",
                variable=self.mode,
                value=value,
                bg="#6f9fd0",
                command=self.reset_quiz
            ).grid(row=r, column=0, sticky="ew", padx=(0, 8), pady=2)

            tk.Label(
                mode_frame,
                text=text,
                font=self.base_font,
                bg="white",
                relief="sunken",
                anchor="center"
            ).grid(row=r, column=1, sticky="ew", pady=2)

        count_frame = tk.Frame(top_frame, bg="#6f9fd0", padx=13, pady=8)
        count_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        count_frame.columnconfigure(0, weight=1, uniform="top")
        count_frame.columnconfigure(1, weight=3, uniform="top")
        count_frame.columnconfigure(2, weight=1, uniform="top")

        tk.Label(
            count_frame,
            text="문항수",
            font=self.base_font,
            bg="white",
            width=10
        ).grid(row=0, column=0, sticky="ew", padx=(0, 10))

        tk.Entry(
            count_frame,
            textvariable=self.num_var,
            font=self.base_font,
            justify="center"
        ).grid(row=0, column=1, sticky="ew", padx=(0, 10))

        tk.Button(
            count_frame,
            text="문제 생성",
            font=self.base_font,
            command=self.generate_quiz
        ).grid(row=0, column=2, sticky="ew")

        problem_frame = tk.LabelFrame(
            self.root,
            text="문제",
            font=self.title_font,
            padx=10,
            pady=10
        )
        problem_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(15, 8))
        problem_frame.rowconfigure(0, weight=1)
        problem_frame.columnconfigure(0, weight=1)

        self.problem_text = tk.Text(
            problem_frame,
            font=self.base_font,
            wrap="word"
        )
        self.problem_text.grid(row=0, column=0, sticky="nsew")

        problem_scroll = tk.Scrollbar(
            problem_frame,
            command=self.problem_text.yview
        )
        problem_scroll.grid(row=0, column=1, sticky="ns")
        self.problem_text.config(yscrollcommand=problem_scroll.set)

        answer_frame = tk.LabelFrame(
            self.root,
            text="정답 입력",
            font=self.title_font,
            padx=10,
            pady=10
        )
        answer_frame.grid(row=2, column=0, sticky="nsew", padx=15, pady=(8, 15))
        answer_frame.rowconfigure(0, weight=1)
        answer_frame.columnconfigure(0, weight=1)

        self.answer_canvas = tk.Canvas(answer_frame)
        self.answer_canvas.grid(row=0, column=0, sticky="nsew")

        answer_scroll = tk.Scrollbar(
            answer_frame,
            orient="vertical",
            command=self.answer_canvas.yview
        )
        answer_scroll.grid(row=0, column=1, sticky="ns")

        self.answer_canvas.configure(yscrollcommand=answer_scroll.set)

        self.answer_inner = tk.Frame(self.answer_canvas)
        self.answer_window = self.answer_canvas.create_window(
            (0, 0),
            window=self.answer_inner,
            anchor="nw"
        )

        self.answer_inner.bind("<Configure>", self.update_answer_scroll)
        self.answer_canvas.bind("<Configure>", self.resize_answer_inner)

        bottom_frame = tk.Frame(self.root, padx=10)
        bottom_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        bottom_frame.columnconfigure(0, weight=1)

        tk.Button(
            bottom_frame,
            text="채점",
            font=self.base_font,
            command=self.grade_quiz
        ).grid(row=0, column=0, sticky="ew")

    def update_answer_scroll(self, event=None):
        self.answer_canvas.configure(scrollregion=self.answer_canvas.bbox("all"))

    def resize_answer_inner(self, event):
        self.answer_canvas.itemconfigure(self.answer_window, width=event.width)

    def reset_quiz(self):
        self.selected_quizzes = []
        self.all_choices = []
        self.answer_vars = []

        self.problem_text.config(state="normal")
        self.problem_text.delete("1.0", tk.END)
        self.problem_text.config(state="disabled")

        for widget in self.answer_inner.winfo_children():
            widget.destroy()

    def generate_quiz(self):
        try:
            num = int(self.num_var.get())
        except ValueError:
            messagebox.showwarning("입력 오류", "문항수는 숫자로 입력하세요.")
            return

        if num <= 0:
            messagebox.showwarning("입력 오류", "문항수는 1 이상이어야 합니다.")
            return

        num = min(num, len(design_patterns))

        self.selected_quizzes = random.sample(design_patterns, num)
        self.all_choices = []
        self.answer_vars = []

        self.problem_text.config(state="normal")
        self.problem_text.delete("1.0", tk.END)

        for widget in self.answer_inner.winfo_children():
            widget.destroy()

        mode = self.mode.get()

        for idx, quiz in enumerate(self.selected_quizzes, start=1):
            self.problem_text.insert(tk.END, f"[{idx}]\n")

            selected_explanation = random.choice(
                quiz["explanations"]
            )

            self.problem_text.insert(
                tk.END,
                f"- {selected_explanation}\n"
            )

            if mode == "choice":
                choices = make_choices(quiz["answer"])
                self.all_choices.append(choices)

                self.problem_text.insert(tk.END, "\n보기\n")
                for choice_idx, choice in enumerate(choices, start=1):
                    self.problem_text.insert(tk.END, f"{choice_idx}. {choice}\n")
            else:
                self.all_choices.append([])

            self.problem_text.insert(tk.END, "\n")

            self.add_answer_input(idx, mode)

        self.problem_text.config(state="disabled")

    def add_answer_input(self, idx, mode):
        row_frame = tk.Frame(self.answer_inner, pady=4)
        row_frame.pack(fill="x", padx=5)

        tk.Label(
            row_frame,
            text=f"{idx}.",
            font=self.base_font,
            width=4,
            anchor="w"
        ).pack(side="left")

        answer_var = tk.StringVar()
        self.answer_vars.append(answer_var)

        tk.Entry(
            row_frame,
            textvariable=answer_var,
            font=self.base_font
        ).pack(side="left", fill="x", expand=True)

    def grade_quiz(self):
        if not self.selected_quizzes:
            messagebox.showwarning("채점 오류", "먼저 문제를 생성하세요.")
            return

        mode = self.mode.get()
        wrong_numbers = []
        score = 0

        for idx, quiz in enumerate(self.selected_quizzes):
            user_answer = self.answer_vars[idx].get().strip()

            if mode == "choice":
                try:
                    answer_num = int(user_answer)
                    choices = self.all_choices[idx]

                    if choices[answer_num - 1] == quiz["answer"]:
                        score += 1
                    else:
                        wrong_numbers.append(idx + 1)

                except (ValueError, IndexError):
                    wrong_numbers.append(idx + 1)

            else:
                normalized_user = normalize_answer(user_answer)
                normalized_answer = normalize_answer(quiz["answer"])

                if normalized_user == normalized_answer:
                    score += 1
                else:
                    wrong_numbers.append(idx + 1)

        if wrong_numbers:
            wrong_text = ", ".join(map(str, wrong_numbers))
            messagebox.showinfo(
                "채점 결과",
                f"점수: {score}/{len(self.selected_quizzes)}\n틀린 번호: {wrong_text}"
            )
        else:
            messagebox.showinfo(
                "채점 결과",
                f"점수: {score}/{len(self.selected_quizzes)}\n전부 정답입니다."
            )


if __name__ == "__main__":
    root = tk.Tk()
    app = QuizApp(root)
    root.mainloop()