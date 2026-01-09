import sys
import webbrowser
import subprocess
import tkinter as tk
import os
# 使用requests库下载图片
import requests
import os   
from urllib.parse import unquote

illustrator_path= r"C:\Program Files\Adobe\Adobe Illustrator 2023\Support Files\Contents\Windows\Illustrator.exe"
file_path= r"D:\Data\Downloads\1013557003.ai"
image_path= r"D:"


# 获取软件安装目录的近似位置
software_install_dir = os.path.dirname(sys.executable)
# 配置文件名称
config_file_name = "config.txt"
# 构建配置文件路径
config_file_path = os.path.join(software_install_dir, config_file_name)


def handle_jiaonei_protocol():
    # 获取通过协议传递过来的参数，在注册协议时通过 %1 传递，这里获取完整的参数列表（去掉协议本身部分）
    args = sys.argv[1:] if len(sys.argv) > 1 else []
    if args:
        # 假设参数是以键值对形式传递，例如 jiaoneicad://func=show_page&page_id=123
        param_dict = {}
        print(f"接收到的参数列表: {args}")

        for arg in args:
            # 如果参数中含有 jiaoneicad:// 则继续处理，否则跳过
            if 'jiaoneicad://' not in arg:
                continue
            # 去掉尾部的 /
            arg = arg.rstrip('/')
            # 将jiaoneicad:// 去掉
            arg = arg.replace('jiaoneicad://', '')

            # 先按&分割参数，再按=分割键值对，存入字典
            if '&' in arg:
                for item in arg.split('&'):
                    if '=' not in item:
                        continue
                    key, value = item.split('=')
                    param_dict[key] = value
           

        # 根据参数中的功能标识来执行相应功能，这里只是示例不同功能分支
        if param_dict.get('func') == 'show_page':
            filePath = param_dict.get('filePath')
            # 判断filePath是否为空字符串
            if not filePath:
                print("未传递有效的页面ID参数！")
                filePath = None
            else:
                # 获取页面ID
                filePath = unquote(filePath)
            # 这里调用具体的函数来展示对应页面，比如在GUI应用中显示某个页面等，示例代码如下：
            # imageurl = "https://www.baidu.com/img/PCtm_d9c8750bed0b3c7d089fa7d55720d6cf.png"
            # 根据imageUrl参数， 下载图片
            download_image(filePath)
            
            show_page(filePath)
        elif param_dict.get('func') == 'do_something_else':
            # 执行其他功能的代码逻辑
            do_something_else()
    else:
        # 如果没有传递参数，执行默认功能，比如打开应用程序主界面等
        open_main_interface()

def download_image(imageUrl):
    print(f"imageUrl: {imageUrl}")
    # 根据imageUrl参数， 下载图片
  
    # 根据默认配置image_path  创建保存图片的文件夹
    if(image_path == None):
        software_install_dir = os.path.dirname(sys.executable)
        # 创建保存图片的文件夹
        image_save_dir = os.path.join(software_install_dir, "images")
        os.makedirs(image_save_dir, exist_ok=True)
    else:
        image_save_dir = image_path
    # 下载图片
    response = requests.get(imageUrl)
    # 保存图片
    with open(f"images/{imageUrl.split('/')[-1]}", "wb") as f:
        f.write(response.content)
    

def show_page(input_file_path):
    print(f"input_file_path: {input_file_path}")
    # # 定义Illustrator软件的可执行文件路径，这里需要根据你实际安装的路径来填写
    # illustrator_path = r"C:\Program Files\Adobe\Adobe Illustrator 2023\Support Files\Contents\Windows\Illustrator.exe"
    # # 定义要打开的.ai文件路径
    # file_path = r"D:\Data\Downloads\test.ai"
    
    try:
        # 使用subprocess.Popen来调用命令打开Illustrator并加载文件
        # 使用全局的 illustrator_path 和 file_path 变量
        if(input_file_path == None):
            print("file_path is None")
            subprocess.Popen([illustrator_path, file_path])
            return
        else:
            print("file_path is not None")
            subprocess.Popen([illustrator_path, input_file_path])
    except FileNotFoundError:
        print("Illustrator可执行文件路径或.ai文件路径有误，请检查并重新输入。")
    # 这里可以是实际的代码逻辑，比如在图形界面中切换到对应的页面等操作

def do_something_else():
    print("执行其他功能操作")
    # 补充具体的功能实现代码
# 定义加载数据的函数（用于软件打开时读取之前保存的数据）
def load_entries():
    print("加载数据中...", config_file_path)
    if os.path.exists(config_file_path):
        print("加载数据中...", config_file_path)
        with open(config_file_path, 'r') as file:
            lines = file.readlines()
            if len(lines) >= 2:
               # 设置全局的 illustrator_path 和 file_path 变量
                global illustrator_path, file_path
                illustrator_path = lines[0].strip()
                file_path = lines[1].strip()
                print("illustrator_path",illustrator_path)
                print("file_path",file_path)
               
    else:
        data = f"C:\Program Files\Adobe\Adobe Illustrator 2023\Support Files\Contents\Windows\Illustrator.exe\nD:\Data\Downloads\\test.ai"
        print(config_file_path)
        with open(config_file_path, 'w') as file:
            file.write(data)
        print("初始化数据已保存成功！")
def open_main_interface():
    print("打开应用程序主界面")
    # 创建主窗口
    root = tk.Tk()
    root.title("表格输入示例（Tkinter）")

    # 创建用于表格布局的框架
    frame = tk.Frame(root)
    frame.pack(padx=100, pady=100)

    # 标签与输入框1
    label1 = tk.Label(frame, text="AI软件路径:")
    label1.grid(row=0, column=0, sticky=tk.W)
    entry1 = tk.Entry(frame)
    entry1.insert(0, illustrator_path)  # 设置默认值
    entry1['width'] = 100  # 设置输入框宽度为30个字符
    entry1.grid(row=0, column=1)

    # 标签与输入框2
    label2 = tk.Label(frame, text="文件路径:")
    label2.grid(row=1, column=0, sticky=tk.W)
    entry2 = tk.Entry(frame)
    entry2.insert(0, file_path)  # 设置默认值
    entry2['width'] = 100 
    entry2.grid(row=1, column=1)

    # 定义获取输入框内容的函数
    # 定义保存数据到文件的函数
    def save_entries():
        # 设置全局的 illustrator_path 和 file_path 变量，并保存到文件
        global illustrator_path, file_path
        illustrator_path = entry1.get()
        file_path = entry2.get()
        data = f"{entry1.get()}\n{entry2.get()}"
        print(data)
        print('config_file_path:',config_file_path)
        with open(config_file_path, 'w') as file:
            file.write(data)
        print("数据已保存成功！")

    # 创建按钮获取输入
    button = tk.Button(root, text="获取输入", command=save_entries)
    button.pack(pady=5)

    root.mainloop()
    # 这里可以是启动应用程序主界面的相关代码，比如创建GUI窗口等操作

if __name__ == "__main__":
    try:
        # 加载数据
        load_entries()
        # 判断是否是通过自定义协议启动应用程序
        if  len(sys.argv) > 1 and sys.argv[1].startswith('jiaoneicad://'):
            handle_jiaonei_protocol()
        else:
            # 如果不是通过自定义协议启动，执行常规的启动逻辑，比如直接打开主界面等
            open_main_interface()

    except Exception as e:
        print(f"程序出现错误: {e}")
    finally:
        input("按回车键关闭程序...")