import webview


def custom_logic(window):
    window.evaluate_js('alert("Nice one brother")')


window = webview.create_window('Woah dude!', 'pages/index.html')
webview.start(custom_logic, window)
