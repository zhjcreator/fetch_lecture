import webview

from api import API


api=API()
window = webview.create_window('Woah dude!', 'pages/index.html',js_api=api)
webview.start()
