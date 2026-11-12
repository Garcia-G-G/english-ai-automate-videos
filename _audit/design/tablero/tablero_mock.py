from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math, random
A="assets/branding/_mock_assets/"  # reference only: fonts in assets/fonts, Bubi in assets/branding/english-unlimited
W,H=1080,1920
INK=(28,24,18); PAPER=(254,253,251); YEL=(242,214,107); BLUE=(27,111,168); CORAL=(255,143,122); GREEN=(47,143,91)
def F(px,w="Bold"): return ImageFont.truetype(A+("Fredoka-Bold.ttf" if w=="Bold" else "Fredoka-Medium.ttf"),int(px))
def M(px,wght=800):
    f=ImageFont.truetype(A+"Manrope[wght].ttf",int(px))
    try: f.set_variation_by_axes([wght])
    except Exception: pass
    return f
EF=ImageFont.truetype(A+"NotoColorEmoji.ttf",109)
def emoji(ch,size):
    im=Image.new("RGBA",(136,128),(0,0,0,0)); ImageDraw.Draw(im).text((0,0),ch,font=EF,embedded_color=True)
    bb=im.getbbox(); im=im.crop(bb); s=size/max(im.size); return im.resize((int(im.width*s),int(im.height*s)),Image.LANCZOS)
def bg():
    c=Image.new("RGB",(W,H)); d=ImageDraw.Draw(c)
    top=(255,122,89); bot=(214,62,92)
    for y in range(H):
        t=y/H; d.line([(0,y),(W,y)],fill=tuple(int(top[i]*(1-t)+bot[i]*t) for i in range(3)))
    c=c.convert("RGBA"); ov=Image.new("RGBA",(W,H),(0,0,0,0)); o=ImageDraw.Draw(ov)
    random.seed(3)
    for _ in range(26):  # soft dots pattern
        x,y,r=random.randint(0,W),random.randint(0,H),random.randint(40,140); o.ellipse((x-r,y-r,x+r,y+r),fill=(255,255,255,14))
    for gx in range(0,W,54):
        for gy in range(0,H,54): o.ellipse((gx-2,gy-2,gx+2,gy+2),fill=(255,255,255,26))
    c.alpha_composite(ov); return c
def card(w,h,fill,rot=0,shadow=10,outline=6,r=34):
    pad=40; im=Image.new("RGBA",(w+pad*2,h+pad*2),(0,0,0,0)); d=ImageDraw.Draw(im)
    d.rounded_rectangle((pad+shadow,pad+shadow,pad+w+shadow,pad+h+shadow),r,fill=INK)
    d.rounded_rectangle((pad,pad,pad+w,pad+h),r,fill=fill,outline=INK,width=outline)
    return im,pad
def text_c(d,xy,s,f,fill,anchor="lm"): d.text(xy,s,font=f,fill=fill,anchor=anchor)
ITEMS=[("🏠","Casa","house","jáus"),("🍳","Cocina","kitchen","kíchen"),("🛏","Cama","bed","bed"),("🚪","Puerta","door","dor"),("🪟","Ventana","window","uíndou"),
       ("🪑","Silla","chair","chér"),("🛁","Baño","bathroom","báz-rum"),("🔑","Llave","key","kí"),("💡","Luz","light","láit"),("🪞","Espejo","mirror","mírror")]
def header(c):
    d=ImageDraw.Draw(c)
    t="¿CÓMO SE DICE?"; f=F(92); tw=d.textlength(t,font=f)
    x=(W-tw)/2; y=150
    hl=Image.new("RGBA",(int(tw+60),70),(0,0,0,0)); ImageDraw.Draw(hl).rounded_rectangle((0,0,tw+60,70),22,fill=YEL)
    c.alpha_composite(hl.rotate(-1.5,expand=True,resample=Image.BICUBIC),(int(x-30),y+38))
    d.text((x,y),t,font=f,fill=INK)
    chip,pad=card(470,100,PAPER,shadow=8,outline=6,r=50)
    cd=ImageDraw.Draw(chip); e=emoji("🏠",70); chip.alpha_composite(e,(pad+34,pad+15))
    cd.text((pad+120,pad+50),"LA CASA",font=F(64),fill=INK,anchor="lm")
    c.alpha_composite(chip.rotate(2,expand=True,resample=Image.BICUBIC),(int((W-560)/2),262))
def tile(i,state,timer=0.0):
    e,es,en,pr=ITEMS[i]; w,h=474,186
    fill={"blank":PAPER,"active":YEL,"done":BLUE}[state]
    im,pad=card(w,h,fill,shadow=10 if state!="active" else 14)
    d=ImageDraw.Draw(im)
    disc=Image.new("RGBA",(124,124),(0,0,0,0)); ImageDraw.Draw(disc).ellipse((0,0,123,123),fill=(255,255,255,255) if state!="done" else (255,255,255,235),outline=INK,width=5)
    im.alpha_composite(disc,(pad+22,pad+31)); em=emoji(e,78); im.alpha_composite(em,(pad+22+62-em.width//2,pad+31+62-em.height//2))
    tx=pad+168; txtc=PAPER if state=="done" else INK
    d.text((tx,pad+56),es,font=F(52),fill=txtc,anchor="lm")
    d.text((pad+w-24,pad+30),f"{i+1}",font=F(30),fill=(255,255,255,170) if state=="done" else (28,24,18,120),anchor="rm")
    if state=="done":
        avail=pad+w-24-tx; fs=56; ps=28
        while fs>36 and d.textlength(en,font=F(fs))+12+d.textlength(f"«{pr}»",font=M(ps,700))>avail:
            fs-=2; ps=max(22,ps-1)
        d.text((tx,pad+122),en,font=F(fs),fill=YEL,anchor="lm")
        d.text((tx+d.textlength(en,font=F(fs))+12,pad+126),f"«{pr}»",font=M(ps,700),fill=(255,255,255,215),anchor="lm")
    else:
        n=len(en.replace(" ","")); x=tx; y=pad+138
        step=min(40,(pad+w-30-tx)/max(1,len(en))); dash=step*0.75
        first=en[0].upper()
        for k,ch in enumerate(en):
            if ch==" ": x+=step*0.5; continue
            if k==0: d.text((x,y-12),first,font=F(44),fill=BLUE,anchor="lm")
            d.rounded_rectangle((x,y+14,x+dash,y+20),3,fill=INK if state=="active" else (28,24,18,150))
            x+=step
        if state=="active":
            d.rounded_rectangle((pad+40,pad+h-16,pad+40+(w-80)*(1-timer),pad+h-9),4,fill=CORAL)
    return im,pad
def grid(c,states,active=None,timer=0.4):
    x0,y0,gx,gy=36,430,30,212
    for i in range(10):
        col,row=i%2,i//2
        st=states[i]; im,pad=tile(i,st,timer)
        x=x0+col*(474+gx)-pad; y=y0+row*gy-pad
        if st=="active":
            im=im.resize((int(im.width*1.07),int(im.height*1.07)),Image.LANCZOS).rotate(-1.5,expand=True,resample=Image.BICUBIC)
            x-=18; y-=16
            glow=Image.new("RGBA",c.size,(0,0,0,0)); ImageDraw.Draw(glow).rounded_rectangle((x+30,y+30,x+im.width-30,y+im.height-30),40,fill=(255,240,170,120))
            c.alpha_composite(glow.filter(ImageFilter.GaussianBlur(24)))
        c.alpha_composite(im,(x,y))
def bubi(c,expr="simbolo_512.png",size=300,pos=(760,1500),flip=False):
    b=Image.open(A+expr).convert("RGBA"); s=size/max(b.size); b=b.resize((int(b.width*s),int(b.height*s)),Image.LANCZOS)
    if flip: b=b.transpose(Image.FLIP_LEFT_RIGHT)
    c.alpha_composite(b,pos)
def speech(c,txt,xy,f=F(46),fill=PAPER,rot=-4):
    d0=ImageDraw.Draw(c); tw=d0.textlength(txt,font=f)
    im,pad=card(int(tw+60),96,fill,shadow=8,outline=6,r=30); d=ImageDraw.Draw(im)
    d.text((pad+30,pad+48),txt,font=f,fill=INK,anchor="lm")
    c.alpha_composite(im.rotate(rot,expand=True,resample=Image.BICUBIC),xy)
def counter(c,n):
    im,pad=card(190,86,INK,shadow=0,outline=0,r=43); d=ImageDraw.Draw(im)
    d.text((pad+95,pad+44),f"{n}/10",font=F(54),fill=YEL,anchor="mm"); c.alpha_composite(im,(44-pad+0,1505-pad))
def frame(states,name,extra=None,n=0,expr="simbolo_512.png",say=None):
    c=bg(); header(c); grid(c,states)
    bubi(c,expr,330 if expr=="simbolo_512.png" else 280,(740 if expr=="simbolo_512.png" else 770,1470))
    if say: speech(c,say,(300,1520))
    counter(c,n) if n else None
    ImageDraw.Draw(c).text((W//2,1860),"learningroutes.com",font=F(30),fill=(255,255,255,200),anchor="mm")
    if extra:
        extra(c); bubi(c,expr,280,(770,1470))
    c.convert("RGB").save(name); return c
f0=frame(["blank"]*10,"f0.png",say="¿Cuántas sabes?")
f1=frame(["done"]*3+["active"]+["blank"]*6,"f1.png",n=3,expr="wow.png",say="¡Dilo antes que yo!")
def endcard(c):
    ov=Image.new("RGBA",(W,H),(28,24,18,120)); c.alpha_composite(ov)
    im,pad=card(820,420,PAPER,shadow=14,outline=7,r=48); d=ImageDraw.Draw(im)
    d.text((pad+410,pad+90),"¿Cuántas sabías?",font=F(64),fill=INK,anchor="mm")
    t="Escríbelo en comentarios"; tw=d.textlength(t,font=F(42)); d.text((pad+410-30,pad+200),t,font=F(42),fill=INK,anchor="mm")
    em=emoji("👇",48); im.alpha_composite(em,(int(pad+410-30+tw/2+10),pad+176))
    d.rounded_rectangle((pad+120,pad+270,pad+700,pad+360),45,fill=BLUE)
    d.text((pad+410,pad+316),"PARTE 2 MAÑANA · SUSCRÍBETE",font=F(36),fill=PAPER,anchor="mm")
    c.alpha_composite(im.rotate(-2,expand=True,resample=Image.BICUBIC),(int((W-im.width)/2),560))
f2=frame(["done"]*10,"f2.png",n=10,expr="lo_lograste.png",extra=endcard)
sheet=Image.new("RGB",(3*540+40,960),(240,236,228))
for k,f in enumerate(["f0.png","f1.png","f2.png"]):
    sheet.paste(Image.open(f).resize((540,960),Image.LANCZOS),(k*560,0))
sheet.save("sheet.png"); print("ok")
