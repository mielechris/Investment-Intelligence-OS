"""Static bounded LC_UUID extraction; never loads an image."""
import struct

def image_uuid(data):
    if type(data) is not bytes or not 32<=len(data)<=32_000_000:raise ValueError('IMAGE_FILE_BOUND')
    slices=[]
    if data[:4]==b'\xca\xfe\xba\xbe':
        n=struct.unpack_from('>I',data,4)[0]
        if not 1<=n<=8 or 8+20*n>len(data):raise ValueError('IMAGE_MACHO')
        for i in range(n):
            cpu,sub,off,size,align=struct.unpack_from('>IIIII',data,8+20*i)
            if align>30 or off%(1<<align) or off<8+20*n or size<32 or off+size>len(data):raise ValueError('IMAGE_MACHO')
            if any(not(off+size<=a or b<=off) for a,b,c,s in slices):raise ValueError('IMAGE_MACHO')
            slices.append((off,off+size,cpu,sub))
    elif data[:4]==b'\xcf\xfa\xed\xfe':
        cpu,sub=struct.unpack_from('<II',data,4);slices=[(0,len(data),cpu,sub)]
    else:raise ValueError('IMAGE_MACHO')
    arm=[x for x in slices if x[2]==0x100000c]
    if len(arm)!=1:raise ValueError('IMAGE_ARCH')
    off,end,cpu,sub=arm[0]
    magic,mcpu,msub,kind,n,total,flags,res=struct.unpack_from('<8I',data,off)
    if magic!=0xfeedfacf or (cpu,sub)!=(mcpu,msub) or kind not in (2,6,8) or not 1<=n<=512 or off+32+total>end:raise ValueError('IMAGE_MACHO')
    pos=off+32;stop=pos+total;uuid=None
    for i in range(n):
        if pos+8>stop:raise ValueError('IMAGE_MACHO')
        cmd,size=struct.unpack_from('<II',data,pos)
        if size<8 or size%8 or pos+size>stop:raise ValueError('IMAGE_MACHO')
        if cmd==0x1b:
            if size!=24 or uuid is not None:raise ValueError('IMAGE_UUID')
            uuid=data[pos+8:pos+24].hex()
        pos+=size
    if pos!=stop or uuid is None or uuid=='0'*32:raise ValueError('IMAGE_UUID')
    return uuid
