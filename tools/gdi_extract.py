import sys,struct,os
f=open(sys.argv[1],'rb'); BASE=45000
def sec(lba):
    f.seek((lba-BASE)*2352+16); return f.read(2048)
pvd=sec(BASE+16)
root=pvd[156:156+34]
out=sys.argv[2] if len(sys.argv)>2 else None
def walk(lba,size,path):
    data=b''.join(sec(lba+i) for i in range((size+2047)//2048))
    i=0
    while i<len(data):
        l=data[i]
        if l==0: i=(i//2048+1)*2048; continue
        e=data[i:i+l]; el=struct.unpack('<I',e[2:6])[0]; es=struct.unpack('<I',e[10:14])[0]
        fl=e[25]; nl=e[32]; n=e[33:33+nl]
        i+=l
        if n in (b'\0',b'\1'): continue
        n=n.decode().split(';')[0]; p=path+'/'+n
        if fl&2: walk(el,es,p)
        else:
            print(f"{el:8d} {es:10d} {p}")
            if out:
                os.makedirs(os.path.dirname(out+p),exist_ok=True)
                with open(out+p,'wb') as o:
                    rem=es;l2=el
                    while rem>0:
                        d=sec(l2); o.write(d[:min(2048,rem)]); rem-=2048; l2+=1
r=root; walk(struct.unpack('<I',r[2:6])[0],struct.unpack('<I',r[10:14])[0],'')
