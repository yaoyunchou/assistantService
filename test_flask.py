"""
简单的Flask测试脚本
用于验证Flask是否正常工作
"""
from flask import Flask

app = Flask(__name__)

@app.route('/')
def index():
    return '<h1>Flask 测试成功！</h1><p>如果您看到这个页面，说明Flask正常工作。</p>'

@app.route('/hello')
def hello():
    return '<h1>Hello World!</h1>'

if __name__ == '__main__':
    print("="*60)
    print("启动测试Flask服务器...")
    print("访问地址: http://127.0.0.1:8099")
    print("按 Ctrl+C 停止")
    print("="*60)
    app.run(host='127.0.0.1', port=8099, debug=True)
