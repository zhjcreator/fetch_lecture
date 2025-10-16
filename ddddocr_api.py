import base64
import os
import io
import sys
from flask import Flask, request, jsonify
from PIL import Image
import ddddocr

from flask_cors import CORS # 导入 CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["https://ehall.seu.edu.cn"], "supports_credentials": True}})
# 全局 OCR 模型实例
ocr = None 
captcha_hash_table = {}

def resource_path(relative_path):
    if getattr(sys, 'frozen', False):  # 判断是否处于打包环境
        base_path = getattr(sys, '_MEIPASS', '')  # 临时解压路径
    else:
        base_path = os.path.abspath(".")
    return str(os.path.join(base_path, relative_path))

@app.route('/predict', methods=['POST'])
def predict():
    """识别上传图片文件的API端点"""
    global ocr # 访问全局 OCR 实例
    if ocr is None:
        return jsonify({"error": "OCR模型尚未加载"}), 503 # 模型未加载时返回 503
        
    try:
        # 检查请求中是否包含文件
        if 'image' not in request.files:
            return jsonify({"error": "未提供图片文件"}), 400
        
        file = request.files['image']
        
        # 检查文件是否为空
        if file.filename == '':
            return jsonify({"error": "未选择文件"}), 400
        
        # 读取图片文件
        image_bytes = file.read()
        
        # 使用ddddocr识别验证码
        result = ocr.classification(image_bytes)
        
        return jsonify({"result": result})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """健康检查端点"""
    global ocr
    return jsonify({"status": "healthy", "model_loaded": ocr is not None})

@app.route('/predict_base64', methods=['POST']) # 修正路由名称，避免与 /predict 冲突
def ocr_from_base64():
    """识别Base64编码的验证码图片的API端点"""
    global ocr
    if ocr is None:
        return jsonify({"error": "OCR模型尚未加载"}), 503 # 模型未加载时返回 503
        
    try:
        data = request.json
        
        # 1. 检查 JSON 数据是否成功解析
        if not isinstance(data, dict):
            # 这通常发生在请求体为空或 Content-Type 不正确时
            return jsonify({"error": "请求数据格式错误，请确保发送的是有效的JSON"}), 400
        
        # 客户端JS脚本发送 'img_b64'
        img_b64 = data.get('img_b64')
        
        # 2. 检查 img_b64 字段是否存在且非空
        if not img_b64:
            return jsonify({"error": "JSON中未找到img_b64字段或其值为空"}), 400

        # Base64解码为字节流
        image_bytes = base64.b64decode(img_b64)
        
        # 使用ddddocr识别验证码
        result = ocr.classification(image_bytes)
        
        return jsonify({"result": result}) # 返回 {"result": "识别结果"}
    
    except Exception as e:
        # 捕获所有其他识别或解码错误
        return jsonify({"error": f"识别过程中发生错误: {str(e)}"}), 500


if __name__ == '__main__':
    # 启动前加载模型


    # --- 1. 初始化模型 ---
    onnx_path = resource_path("model.onnx")
    charsets_path = resource_path("charsets.json")
    captcha_hash_table_path = resource_path("captcha_hash_table.csv")
    
    try:
        ocr = ddddocr.DdddOcr(import_onnx_path=onnx_path, charsets_path=charsets_path, show_ad=False)
    except Exception as e:
        print(f"FATAL ERROR: Failed to initialize ddddocr model: {e}")
        # 即使模型加载失败，服务也继续运行以提供健康检查和调试

    # --- 2. 加载哈希表 (可选) ---
    captcha_hash_table = {}
    if os.path.exists(captcha_hash_table_path):
        with open(captcha_hash_table_path) as f:
            for line in f:
                if line.strip():
                    try:
                        # 使用 split(",", 1) 确保只在第一个逗号处分割，以防标签中含有逗号
                        hash_val, label = line.strip().split(",", 1)
                        captcha_hash_table[hash_val] = label
                    except ValueError:
                        print(f"Warning: Skipping malformed line in hash table: {line.strip()}")

    # --- 3. 启动服务器 ---
    print("ddddocr API服务启动中...")
    print("API文档:")
    print("  POST /predict - 上传图片文件识别验证码")
    print("  POST /predict_base64 - 通过Base64字符串识别验证码")
    print("  GET /health - 健康检查")
    print("\n示例用法:")
    print("  curl -X POST -F 'image=@验证码图片.jpg' http://127.0.0.1:5000/predict")
    # 修正 base64 示例以匹配新的路由 /predict_base64
    print("  curl -X POST -H 'Content-Type: application/json' -d '{\"img_b64\": \"base64编码的图片数据\"}' http://127.0.0.1:5000/predict_base64") 
        
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=True)