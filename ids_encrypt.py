import js2py

context = js2py.EvalJs()

with open("./ids-encrypt.js") as f:
    js_content = f.read()


def encryptAES(data, salt):
    # 执行整段JS代码
    context.execute(js_content)
    result = context.encryptAES(data, salt)
    print("加密：", result)
    return result
