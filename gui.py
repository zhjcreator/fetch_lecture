import webview

from api import API


api=API()
window = webview.create_window('东南大学人文素质讲座抢课', 'pages/index.html',js_api=api)
webview.start(debug=True)
# webview.start()