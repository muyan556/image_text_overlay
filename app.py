import os
import json
from flask import Flask, render_template, request, jsonify, Response
from engine import VideoEngine

app = Flask(__name__)
CONFIG_PATH = "config.json"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    if request.method == 'POST':
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(request.json, f, indent=2, ensure_ascii=False)
        return jsonify({"status": "ok"})
    if not os.path.exists(CONFIG_PATH):
        return jsonify({"error": "Config not found"}), 404
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return jsonify(json.load(f))

@app.route('/api/preview', methods=['POST'])
def preview_frame():
    data = request.json
    cfg = data.get('config')
    idx = data.get('preview_index', 0)
    
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        
    engine = VideoEngine(CONFIG_PATH)
    
    def get_text(text_list, i):
        return text_list[i] if text_list and i < len(text_list) else ""
        
    t1, t2 = get_text(cfg['texts']['text1'], idx), get_text(cfg['texts']['text2'], idx)
    t3, t4 = get_text(cfg['texts']['text3'], idx), get_text(cfg['texts']['text4'], idx)
    
    # 传入实际显示的数字 (idx + 1) 给序列号渲染器
    out_path = engine.generate_image(t1, t2, t3, t4, index=idx+1, show_t3=True, preview_path="static/preview.png")
    return jsonify({"url": f"/static/preview.png?t={os.path.getmtime(out_path)}"})

@app.route('/api/build', methods=['GET'])
def build_video():
    def generate():
        def emit(event_type, data):
            msg = json.dumps(data) if isinstance(data, dict) else json.dumps({"msg": data})
            yield f"event: {event_type}\ndata: {msg}\n\n"
        try:
            engine = VideoEngine(CONFIG_PATH, emit=emit)
            engine.build_video()
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'msg': str(e)})}\n\n"
    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    for d in ["static/output", "temp"]: os.makedirs(d, exist_ok=True)
    print("🚀 Web 面板已启动! 请在浏览器访问 http://127.0.0.1:5000")
    app.run(debug=True, port=5000)