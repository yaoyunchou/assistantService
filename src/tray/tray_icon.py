"""
系统托盘图标管理
"""
import threading
from pathlib import Path
from typing import Optional
import pystray
from PIL import Image, ImageDraw
from config import Config


class TrayIcon:
    """系统托盘图标管理"""
    
    def __init__(self, on_open=None, on_quit=None):
        """
        初始化托盘图标
        
        Args:
            on_open: 打开界面回调函数
            on_quit: 退出应用回调函数
        """
        self.on_open = on_open
        self.on_quit = on_quit
        self.icon = None
        self._thread = None
        self._running = False
    
    def _create_icon_image(self) -> Image.Image:
        """
        创建托盘图标图像
        
        Returns:
            PIL Image对象
        """
        # 创建一个简单的图标（16x16像素）
        # 如果以后有图标文件，可以从文件加载
        image = Image.new('RGB', (64, 64), color='white')
        draw = ImageDraw.Draw(image)
        
        # 绘制一个简单的快递盒子图标
        # 绘制盒子
        draw.rectangle([10, 20, 54, 54], outline='black', width=2)
        # 绘制盖子
        draw.polygon([(10, 20), (32, 10), (54, 20)], outline='black', fill='lightgray', width=2)
        # 绘制线条
        draw.line([(32, 10), (32, 54)], fill='black', width=1)
        
        return image
    
    def _load_icon_from_file(self) -> Optional[Image.Image]:
        """
        尝试从文件加载图标
        
        Returns:
            PIL Image对象，如果文件不存在返回None
        """
        # 优先使用配置的图标路径
        if Config.TRAY_ICON_PATH:
            config_path = Path(Config.TRAY_ICON_PATH)
            if config_path.exists():
                try:
                    image = Image.open(config_path)
                    # 转换为RGBA模式以支持透明度
                    if image.mode != 'RGBA':
                        image = image.convert('RGBA')
                    # 调整大小为合适的托盘图标尺寸（通常64x64或128x128）
                    if image.size[0] > 128 or image.size[1] > 128:
                        image = image.resize((128, 128), Image.Resampling.LANCZOS)
                    return image
                except Exception as e:
                    print(f"[TrayIcon] 无法加载配置的图标文件 {config_path}: {e}")
        
        # 尝试从多个可能的位置加载图标
        possible_paths = [
            Path(__file__).parent.parent / 'static' / 'images' / 'log_default.png',
            Path(__file__).parent.parent.parent / 'static' / 'images' / 'log_default.png',
            Path(__file__).parent.parent / 'static' / 'images' / 'logo_default.jpg',
            Path(__file__).parent.parent.parent / 'static' / 'images' / 'logo_default.jpg',
            Path(__file__).parent.parent / 'static' / 'images' / 'icon.png',
            Path(__file__).parent.parent.parent / 'static' / 'images' / 'icon.png',
            Path(__file__).parent.parent / 'static' / 'images' / 'icon.ico',
        ]
        
        for path in possible_paths:
            if path.exists():
                try:
                    image = Image.open(path)
                    # 转换为RGBA模式以支持透明度
                    if image.mode != 'RGBA':
                        image = image.convert('RGBA')
                    # 调整大小为合适的托盘图标尺寸
                    if image.size[0] > 128 or image.size[1] > 128:
                        image = image.resize((128, 128), Image.Resampling.LANCZOS)
                    return image
                except Exception as e:
                    print(f"[TrayIcon] 无法加载图标文件 {path}: {e}")
        
        return None
    
    def _create_menu(self) -> pystray.Menu:
        """创建托盘菜单"""
        items = [
            pystray.MenuItem('打开界面', self._on_open_clicked),
            pystray.MenuItem('退出', self._on_quit_clicked),
        ]
        return pystray.Menu(*items)
    
    def _on_open_clicked(self, icon, item):
        """打开界面菜单项点击处理"""
        if self.on_open:
            self.on_open()
        else:
            # 默认行为：使用原生窗口或浏览器
            # 注意：这里不等待服务就绪，因为服务应该已经在运行
            if Config.USE_NATIVE_WINDOW:
                try:
                    import webview
                    url = f"http://{Config.HOST}:{Config.PORT}"
                    webview.create_window(
                        title=Config.WINDOW_TITLE,
                        url=url,
                        width=Config.WINDOW_WIDTH,
                        height=Config.WINDOW_HEIGHT,
                        min_size=(Config.WINDOW_MIN_WIDTH, Config.WINDOW_MIN_HEIGHT),
                        resizable=Config.WINDOW_RESIZABLE
                    )
                    # 在后台线程中启动（非阻塞）
                    threading.Thread(target=lambda: webview.start(debug=False), daemon=True).start()
                except ImportError:
                    import webbrowser
                    url = f"http://{Config.HOST}:{Config.PORT}"
                    webbrowser.open(url)
            else:
                import webbrowser
                url = f"http://{Config.HOST}:{Config.PORT}"
                webbrowser.open(url)
    
    def _on_quit_clicked(self, icon, item):
        """退出菜单项点击处理"""
        # 先停止托盘图标，避免在退出回调中出现异常
        self.stop()
        
        # 然后调用退出回调（可能会调用 sys.exit()）
        if self.on_quit:
            self.on_quit()
    
    def _run_icon(self):
        """在后台线程中运行图标"""
        # 尝试从文件加载图标，如果失败则创建默认图标
        icon_image = self._load_icon_from_file()
        if icon_image is None:
            icon_image = self._create_icon_image()
        
        self.icon = pystray.Icon(
            Config.APP_NAME,
            icon_image,
            Config.APP_NAME,
            self._create_menu()
        )
        
        # 双击打开界面
        self.icon.on_clicked = self._on_open_clicked
        
        self._running = True
        self.icon.run()
    
    def start(self):
        """启动托盘图标"""
        if self._thread is not None and self._thread.is_alive():
            return
        
        self._thread = threading.Thread(target=self._run_icon, daemon=True)
        self._thread.start()
        print("[TrayIcon] 系统托盘图标已启动")
    
    def stop(self):
        """停止托盘图标"""
        self._running = False
        if self.icon:
            self.icon.stop()
        print("[TrayIcon] 系统托盘图标已停止")
    
    def is_running(self) -> bool:
        """检查托盘图标是否正在运行"""
        return self._running and self._thread is not None and self._thread.is_alive()
