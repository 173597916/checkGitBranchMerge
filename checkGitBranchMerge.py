import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk
from git import Repo, exc
from git.exc import GitCommandError
import re
import threading
import queue
import datetime
from tkcalendar import Calendar, DateEntry
import time
import os

# 设置环境变量 GIT_PYTHON_TRACE 为 full
os.environ["GIT_PYTHON_TRACE"] = "full"

# 设置编码为 utf-8
os.environ["PYTHONIOENCODING"] = "utf-8"

options = None  # 全局变量
def check_branch_merge(repo_path, branch1, branch2, keyword, start_date, end_date, author, queue):
    repo = Repo(repo_path)
    queue.put(f"正在拉取代码...")
    repo.remotes.origin.fetch()
    repo.git.config('--global', 'core.quotepath', 'false')
    queue.put(f"拉取代码完成")
    branch1 = branch1 if branch1.startswith('origin/') else f'origin/{branch1}'
    branch2 = branch2 if branch2.startswith('origin/') else f'origin/{branch2}'
    branch1_commits = list(repo.iter_commits(branch1))
    branch2_commits = list(repo.iter_commits(branch2))

    pattern = re.compile(keyword)
    unmerged_commits = []
    merged_commits = []
    files_to_compare = set()
    #处理为时间戳比较
    start_date = time.mktime(datetime.datetime.strptime(start_date, "%Y-%m-%d").timetuple())
    #由于控件日期默认是当天0时，所以需要将结束时间加1天
    end_date = (datetime.datetime.strptime(end_date, "%Y-%m-%d") + datetime.timedelta(days=1)).timestamp()
    queue.put(f"'{branch1}' 分支中包含关键字 '{keyword}' 的提交:")
    # 遍历分支 branch1 的提交记录
    for commit in branch1_commits:
        # 检查提交消息中是否包含指定关键字 keyword，如果包含则将提交信息加入消息队列
        if "Merge branch" not in commit.message:
            if pattern.search(commit.message) and start_date <= time.mktime(commit.authored_datetime.timetuple()) <= end_date:
                if not author or commit.author.name == author:
                    queue.put(f"- {commit.hexsha}：{commit.message}")
                    if any(commit.authored_datetime == target_commit.authored_datetime for target_commit in branch2_commits):
                        merged_commits.append(commit)
                    else:
                        unmerged_commits.append(commit)
                        commit_diff_files = repo.git.show('--pretty=', '--name-only', commit.hexsha).split('\n')
                        # 将每个提交中的文件差异信息添加到一个集合 files_to_compare
                        files_to_compare.update(commit_diff_files)


    if merged_commits:
        queue.put("--------------------------------------------------------------------------------------------------------------------------------------------")
        queue.put(f"以下包含关键字 '{keyword}' 的提交已从 '{branch1}' 合并到 '{branch2}':")
        for commit in merged_commits:
            queue.put(f"- {commit.hexsha}：{commit.message}")

    all_files_same = True
    queue.put("--------------------------------------------------------------------------------------------------------------------------------------------")
    queue.put("文件差异检测结果：")
    different_files = []

    for file in files_to_compare:
        if file:
            try:
                diff = repo.git.diff(f"{branch1}:{file}", f"{branch2}:{file}", '--ignore-space-at-eol', '-w', '--ignore-cr-at-eol')
                if diff:
                    all_files_same = False
                    different_files.append(file)
                else:
                    pass
            except GitCommandError as e:
                queue.put(f"  - 无法比较文件 '{file}' 的差异, 该文件可能为新增或删除文件: {e.stderr}")

    if different_files:
        queue.put("--------------------------------------------------------------------------------------------------------------------------------------------")
        queue.put("以下是存在差异文件：")
        for file in different_files:
            queue.put(f"  -{file}")
        queue.put("文件存在差异并不意味着是本次提交未同步代码造成，也可能是新需求，请人工检测")
    else:
        queue.put("暂无差异文件")
    if all_files_same:
        queue.put("--------------------------------------------------------------------------------------------------------------------------------------------")
        queue.put(f"所有包含关键字 '{keyword}' 的提交中修改的文件，在 '{branch1}' 和 '{branch2}' 中内容相同，可能已通过其它方式手工合并。")
        queue.put("所有提交均已同步")
    elif unmerged_commits:
        queue.put("--------------------------------------------------------------------------------------------------------------------------------------------")
        queue.put(f"请检查以下包含关键字 '{keyword}' 的提交，可能未从 '{branch1}' 合并到 '{branch2}':")
        for commit in unmerged_commits:
            queue.put(f"- {commit.hexsha}：{commit.message}")
def browse_folder():
    global options
    folder_selected = filedialog.askdirectory()
    repo_path_entry.delete(0, tk.END)
    repo_path_entry.insert(0, folder_selected)
    
    options = get_remote_branches(folder_selected)
    branch2_entry['values'] = options
    selected_option.set(options[0] if options else "")

def run_check_branch_merge():
    repo_path = repo_path_entry.get()
    branch1 = branch1_entry.get()
    branch2 = selected_option.get()
    keyword = keyword_entry.get()
    start_date = start_date_entry.get()
    end_date = end_date_entry.get()
    author = author_entry.get()
    output_text.delete(1.0, tk.END)
    try:
        if author:
            if author not in get_all_authors(repo_path):
                queue.put(f"作者 '{author}' 不存在")
            else:
                threading.Thread(target=check_branch_merge, args=(repo_path, branch1, branch2, keyword, start_date, end_date, author, queue)).start()
        else:
            threading.Thread(target=check_branch_merge, args=(repo_path, branch1, branch2, keyword, start_date, end_date, author, queue)).start()
    except Exception as e:
        queue.put(str(e))



def update_output_text():
    while not queue.empty():
        message = queue.get()
        output_text.insert(tk.END, message + "\n")
    root.after(100, update_output_text)

def on_submit():
    run_check_branch_merge()

def on_select(value):
    print(f'选择了: {value}')

def update_options(event):
    value = event.widget.get()
    menu = list(event.widget['values'])
    menu.clear()
    for option in options:
        if value.lower() in option.lower():
            menu.append(option)
    event.widget['values'] = tuple(menu)

# 获取远程分支列表
def get_remote_branches(repo_path):
    repo = Repo(repo_path)
    remote_branches = [f.name for f in repo.remotes.origin.refs]
    return remote_branches

# 获取所有提交作者
def get_all_authors(repo_path):
    repo = Repo(repo_path)
    all_authors = set()
    for commit in repo.iter_commits():
        all_authors.add(commit.author.name)
    return list(all_authors)

root = tk.Tk()
root.title("Check Git Branch Merge")

queue = queue.Queue()

tk.Label(root, text="项目路径:").grid(row=0, column=0, sticky="w")
repo_path_entry = tk.Entry(root, width=200)
repo_path_entry.grid(row=0, column=1)
tk.Button(root, text="请选择...", command=browse_folder).grid(row=0, column=2)

tk.Label(root, text="源分支:").grid(row=1, column=0, sticky="w")
branch1_entry = tk.Entry(root)
branch1_entry.grid(row=1, column=1, columnspan=2, sticky="ew")

tk.Label(root, text="目标分支:").grid(row=2, column=0, sticky="w")
selected_option = tk.StringVar(root)
selected_option.set("")
# 更改代码中的 Combobox 为 ttk.Combobox
branch2_entry = ttk.Combobox(root, textvariable=selected_option)
branch2_entry['values'] = options
branch2_entry.bind("<KeyRelease>", update_options)
branch2_entry.grid(row=2, column=1, sticky="w")
branch2_entry.config(width=30)  # 根据需要设置适当的宽度值

tk.Label(root, text="提交关键字:").grid(row=3, column=0, sticky="w")
keyword_entry = tk.Entry(root)
keyword_entry.grid(row=3, column=1, columnspan=2, sticky="ew")

# 获取当前日期
current_date = datetime.datetime.now()
# 计算一个月前的日期
one_month_ago = current_date - datetime.timedelta(days=30)
# 格式化日期为 "%Y-%m-%d" 格式
start_date_default = one_month_ago.strftime("%Y-%m-%d")
end_date_default = current_date.strftime("%Y-%m-%d")


# print(end_date_default, 'end_date_default')
date_frame = tk.Frame(root)
date_frame.grid(row=4, column=0, columnspan=3, sticky="w")
tk.Label(date_frame, text="开始日期:").pack(side="left", padx=6)
start_date_entry = DateEntry(date_frame, date_pattern='yyyy-mm-dd')
start_date_entry.pack(side="left")
tk.Label(date_frame, text="结束日期:").pack(side="left", padx=6)
end_date_entry = DateEntry(date_frame, date_pattern='yyyy-mm-dd')
end_date_entry.pack(side="left")
start_date_entry.set_date(one_month_ago)
end_date_entry.set_date(current_date)

tk.Label(root, text="提交人:").grid(row=5, column=0, sticky="w")
author_entry = tk.Entry(root)
author_entry.grid(row=5, column=1, columnspan=2, sticky="ew")


submit_button = tk.Button(root, text="检查合并", command=on_submit)
submit_button.grid(row=6, column=0, columnspan=3)

output_text = scrolledtext.ScrolledText(root, height=50)
output_text.grid(row=10, column=0, columnspan=3, sticky="ew")


update_output_text()

root.mainloop()
