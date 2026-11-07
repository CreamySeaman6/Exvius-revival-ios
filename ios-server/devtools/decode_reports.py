import base64,glob,json,sys
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
K=b'FFBE2020DevsRGod'; IV=b'dZMjkk8gFDzKHlsx'
def dec(b64):
    raw=base64.b64decode(b64)
    d=Cipher(algorithms.AES(K),modes.CBC(IV)).decryptor(); p=d.update(raw)+d.finalize()
    for _ in range(2):
        n=p[-1]
        if 1<=n<=16 and p[-n:]==bytes([n])*n: p=p[:-n]
    return p.decode('utf-8','replace')
f=sys.argv[1]
raw=open(f).read().split('----- raw request -----\n',1)[1]
body=json.JSONDecoder().raw_decode(raw)[0]
row=body['a8035010'][0]
out=[]
for l in row['FPGJbL8x'].split('\n'):
    if l.strip():
        try: out.append(dec(l))
        except Exception as e: out.append(f'<undecodable {e}>')
print('\n'.join(out))
