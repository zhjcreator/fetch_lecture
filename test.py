from hashlib import md5


import time
fingerprint = md5(str(time.time()).encode()).hexdigest()
print(fingerprint)
